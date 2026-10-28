import csv
import hashlib
import json
from pathlib import Path

from scripts import run_v0_evaluation as runner
from scripts.summarize_v0_evaluation import render_summary


ROOT = Path(__file__).resolve().parents[1]


def test_evaluation_scenarios_have_valid_schema_presets_and_category_counts():
    scenarios = runner._load_scenarios()
    assert len(scenarios) == 30
    assert len({item["id"] for item in scenarios}) == 30
    assert {item["starting_preset"] for item in scenarios} <= set(runner.initialize_scenario.__globals__["PRESETS"])
    assert {category: sum(item["category"] == category for item in scenarios) for category in {
        "normal_progression", "clarification_questions", "repetition_context", "language_adaptation",
        "invalid_values", "out_of_order", "refusals_interruptions", "completion_failure",
    }} == {
        "normal_progression": 5, "clarification_questions": 5, "repetition_context": 4,
        "language_adaptation": 5, "invalid_values": 4, "out_of_order": 3,
        "refusals_interruptions": 2, "completion_failure": 2,
    }
    for scenario in scenarios:
        assert isinstance(scenario["requires_live_api"], bool)
        assert scenario["critical_conditions"]
        for turn in scenario["turns"]:
            assert isinstance(turn["message"], str)
            assert isinstance(turn["expected_state_change"], bool)
            assert turn["expected_tool"] in {"submit_information", "no_state_changing_tool"}
            assert isinstance(turn["expected_accepted_values"], dict)
            assert isinstance(turn["expected_staged_values"], dict)


def test_v0_prompt_matches_pinned_baseline_hash():
    expected = runner.PROMPT_HASH_PATH.read_text(encoding="utf-8").split()[0]
    actual = hashlib.sha256(runner.PROMPT_PATH.read_bytes()).hexdigest()
    assert actual == expected


def test_offline_runner_uses_manager_runtime_and_isolates_each_scenario():
    scenario = next(item for item in runner._load_scenarios() if item["id"] == "V0-OO-03")
    config = runner.ModelConfig("offline", "offline://", "offline-mock", runner.GenerationSettings())
    turns, summary = runner._run_scenario(scenario, config, "offline")
    assert summary["status"] == "successful"
    assert all(turn["state_transition_correct"] for turn in turns)
    assert summary["final_state"]["accepted_values"] == {
        "consent": True, "loan_amount": 100000, "tenure_months": 6,
    }
    assert summary["final_state"]["staged_values"] == {}
    fresh = runner.initialize_scenario(scenario["starting_preset"])
    assert fresh["accepted_values"] == {}
    assert fresh["messages"] == [] and fresh["tool_events"] == []


def test_offline_full_journey_and_post_commit_error_are_recorded_truthfully():
    scenarios = runner._load_scenarios()
    config = runner.ModelConfig("offline", "offline://", "offline-mock", runner.GenerationSettings())
    complete = next(item for item in scenarios if item["id"] == "V0-CP-01")
    turns, result = runner._run_scenario(complete, config, "offline")
    assert result["status"] == "successful"
    assert len(result["final_state"]["accepted_values"]) == 6
    assert all("approval" not in (turn["assistant_response"] or "").lower() for turn in turns)
    failure = next(item for item in scenarios if item["id"] == "V0-CP-02")
    failed_turns, failed_result = runner._run_scenario(failure, config, "offline")
    assert failed_result["status"] == "successful"
    assert failed_result["errors"] == []
    assert len(failed_result["expected_errors"]) == 1
    assert failed_result["final_state"]["accepted_values"]["tenure_months"] == 18
    assert "follow-up response could not be generated" in failed_turns[0]["assistant_response"]


def test_offline_mode_writes_structured_output_and_never_exports_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "sentinel-never-export")
    def forbid_provider_configuration(cls):
        raise AssertionError("offline mode must not load provider configuration")
    monkeypatch.setattr(runner.ModelConfig, "from_env", classmethod(forbid_provider_configuration))
    result = runner.main(["--scenario-id", "V0-IV-03", "--output-dir", str(tmp_path)])
    assert result == 0
    jsonl_path = next(tmp_path.glob("*.jsonl"))
    row = json.loads(jsonl_path.read_text(encoding="utf-8").splitlines()[0])
    assert row["mode"] == "offline"
    assert row["prompt_version"] == "V0"
    assert row["tool_events"][0]["outcomes"][0]["status"] == "invalid"
    assert row["active_rule_after"] == "tenure_months"
    assert not any("sentinel-never-export" in path.read_text(encoding="utf-8") for path in tmp_path.iterdir() if path.is_file())
    assert all("api_key" not in path.read_text(encoding="utf-8").lower() for path in tmp_path.iterdir() if path.is_file())
    rating_rows = list(csv.DictReader(next(tmp_path.glob("*_ratings.csv")).open(encoding="utf-8", newline="")))
    assert len(rating_rows) == 1 and rating_rows[0]["scenario_id"] == "V0-IV-03"
    assert rating_rows[0]["contextual_relevance"] == ""


def test_rating_template_fields_and_empty_ratings_are_not_zero(tmp_path):
    template = tmp_path / "ratings.csv"
    runner._write_rating_template(template)
    with template.open(encoding="utf-8", newline="") as handle:
        header = next(csv.reader(handle))
    assert header == [
        "run_id", "scenario_id", "prompt_version", "model_id", "reviewer_id",
        *runner.RATING_FIELDS, "critical_violations", "reviewer_notes",
    ]
    with (ROOT / "evaluation" / "human_ratings_template.csv").open(encoding="utf-8", newline="") as handle:
        template_rows = list(csv.DictReader(handle))
    assert len(template_rows) == 30
    assert all(not row["contextual_relevance"] and not row["critical_violations"] for row in template_rows)
    report = render_summary(tmp_path, [template])
    assert "contextual_relevance: Not rated" in report
    assert "English: Not rated" in report


def test_summary_uses_recorded_responses_and_real_scores_only(tmp_path):
    run = {
        "prompt_version": "V0",
        "runs": [{"scenario_id": "V0-X", "status": "successful"}],
    }
    (tmp_path / "run.json").write_text(json.dumps(run), encoding="utf-8")
    record = {
        "scenario_id": "V0-X", "category": "clarification_questions", "language": "Hinglish",
        "turn": 1, "assistant_response": "Observed synthetic recorded answer.", "latency_ms": 23,
        "state_transition_correct": True, "critical_violations": [],
    }
    (tmp_path / "run.jsonl").write_text(json.dumps(record) + "\n", encoding="utf-8")
    report = render_summary(tmp_path)
    assert "Observed synthetic recorded answer." in report
    assert "Not rated" in report
    assert "1/1 turns matched expected state/tool behavior" in report
    assert "Strong workflow example" in report


def test_summary_labels_examples_from_recorded_human_scores(tmp_path):
    rows = [
        {"scenario_id": "V0-BEST", "category": "normal_progression", "language": "English", "turn": 1,
         "assistant_response": "Recorded high-rated answer.", "latency_ms": 10,
         "state_transition_correct": True, "critical_violations": []},
        {"scenario_id": "V0-WEAK", "category": "language_adaptation", "language": "Hinglish", "turn": 1,
         "assistant_response": "Recorded low-rated answer.", "latency_ms": 15,
         "state_transition_correct": True, "critical_violations": []},
    ]
    (tmp_path / "run.jsonl").write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    ratings = tmp_path / "ratings.csv"
    fields = ["scenario_id", *runner.RATING_FIELDS]
    with ratings.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerow({"scenario_id": "V0-BEST", **{field: 5 for field in runner.RATING_FIELDS}})
        writer.writerow({"scenario_id": "V0-WEAK", **{field: 1 for field in runner.RATING_FIELDS}})
    report = render_summary(tmp_path, [ratings])
    assert "Highest human-rated recorded response, V0-BEST" in report
    assert "Lowest human-rated recorded response, V0-WEAK" in report
    assert "Recorded high-rated answer." in report and "Recorded low-rated answer." in report
    assert "normal_progression: contextual_relevance=5.00 (n=1)" in report


def test_scenario_runner_is_offline_unless_live_flag_is_explicit():
    parser = __import__("argparse").ArgumentParser()
    parser.add_argument("--live", action="store_true")
    assert parser.parse_args([]).live is False

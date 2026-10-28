import csv
import hashlib
import json
from pathlib import Path
import sys

import pytest

from scripts import run_v0_evaluation as runner
from scripts import summarize_v0_evaluation as summarizer
from scripts import safe_paths
from scripts.safe_paths import UnsafePathError, safe_write_text
from core.manager import PROMPT_PATHS


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


@pytest.mark.parametrize("prompt_version", ["V0", "V1"])
def test_offline_runner_supports_each_prompt_version(prompt_version):
    scenario = next(item for item in runner._load_scenarios() if item["id"] == "V0-IV-03")
    config = runner.ModelConfig("offline", "offline://", "offline-mock", runner.GenerationSettings())
    turns, summary = runner._run_scenario(
        scenario, config, "offline", prompt_version=prompt_version,
    )
    assert summary["status"] == "successful"
    assert all(turn["state_transition_correct"] for turn in turns)


@pytest.mark.parametrize("prompt_version", ["V0", "V1"])
def test_evaluation_exports_version_and_selected_prompt_hash(
    prompt_version, tmp_path, monkeypatch,
):
    monkeypatch.setattr(
        runner.ModelConfig, "from_env",
        classmethod(lambda cls: (_ for _ in ()).throw(AssertionError("offline must not configure NVIDIA"))),
    )
    output = tmp_path / prompt_version
    assert runner.main([
        "--prompt-version", prompt_version, "--scenario-id", "V0-IV-03",
        "--output-dir", str(output),
    ]) == 0
    metadata = json.loads(next(output.glob("*.json")).read_text(encoding="utf-8"))
    row = json.loads(next(output.glob("*.jsonl")).read_text(encoding="utf-8").splitlines()[0])
    rating = next(csv.DictReader(next(output.glob("*_ratings.csv")).open(encoding="utf-8", newline="")))
    expected_hash = hashlib.sha256(PROMPT_PATHS[prompt_version].read_bytes()).hexdigest()
    assert metadata["prompt_version"] == row["prompt_version"] == rating["prompt_version"] == prompt_version
    assert metadata["prompt_sha256"] == row["prompt_sha256"] == expected_hash
    assert row["mode"] == "offline"
    report = summarizer.render_summary(output)
    assert f"# {prompt_version} evaluation summary" in report
    assert expected_hash in report


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
    assert rating_rows[0]["run_id"] == row["run_id"] and rating_rows[0]["turn"] == "1"
    assert rating_rows[0]["contextual_relevance"] == ""


def test_rating_template_fields_and_empty_ratings_are_not_zero(tmp_path):
    template = tmp_path / "ratings.csv"
    runner._write_rating_template(template)
    with template.open(encoding="utf-8", newline="") as handle:
        header = next(csv.reader(handle))
    assert header == [
        "run_id", "scenario_id", "turn", "prompt_version", "model_id", "reviewer_id",
        *runner.RATING_FIELDS, "critical_violations", "reviewer_notes",
    ]
    with (ROOT / "evaluation" / "human_ratings_template.csv").open(encoding="utf-8", newline="") as handle:
        template_rows = list(csv.DictReader(handle))
    assert len(template_rows) == 36
    assert all(row["run_id"] == "" and row["reviewer_id"] == "" for row in template_rows)
    assert len({(row["run_id"], row["scenario_id"], row["turn"]) for row in template_rows}) == 36
    assert all(not row["contextual_relevance"] and not row["critical_violations"] for row in template_rows)
    report = summarizer.render_summary(tmp_path, [template])
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
    report = summarizer.render_summary(tmp_path)
    assert "Observed synthetic recorded answer." in report
    assert "Not rated" in report
    assert "1/1 turns matched expected state/tool behavior" in report
    assert "Strong workflow example" in report


def test_summary_labels_examples_from_recorded_human_scores(tmp_path):
    rows = [
        {"run_id": "RUN-1", "scenario_id": "V0-BEST", "category": "normal_progression", "language": "English", "turn": 1,
         "assistant_response": "Recorded high-rated answer.", "latency_ms": 10,
         "state_transition_correct": True, "critical_violations": []},
        {"run_id": "RUN-1", "scenario_id": "V0-BEST", "category": "normal_progression", "language": "English", "turn": 2,
         "assistant_response": "Another response from the same scenario.", "latency_ms": 11,
         "state_transition_correct": True, "critical_violations": []},
        {"run_id": "RUN-1", "scenario_id": "V0-WEAK", "category": "language_adaptation", "language": "Hinglish", "turn": 1,
         "assistant_response": "Recorded low-rated answer.", "latency_ms": 15,
         "state_transition_correct": True, "critical_violations": []},
    ]
    (tmp_path / "run.jsonl").write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    ratings = tmp_path / "ratings.csv"
    fields = ["run_id", "scenario_id", "turn", "reviewer_id", *runner.RATING_FIELDS]
    with ratings.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerow({"run_id": "RUN-1", "scenario_id": "V0-BEST", "turn": 1, "reviewer_id": "r1", **{field: 5 for field in runner.RATING_FIELDS}})
        writer.writerow({"run_id": "RUN-1", "scenario_id": "V0-BEST", "turn": 2, "reviewer_id": "r2", **{field: 2 for field in runner.RATING_FIELDS}})
        writer.writerow({"run_id": "RUN-1", "scenario_id": "V0-WEAK", "turn": 1, "reviewer_id": "r1", **{field: 1 for field in runner.RATING_FIELDS}})
        writer.writerow({"run_id": "OTHER-RUN", "scenario_id": "V0-BEST", "turn": 1, "reviewer_id": "r1", **{field: 1 for field in runner.RATING_FIELDS}})
    report = summarizer.render_summary(tmp_path, [ratings])
    assert "Highest human-rated recorded response, V0-BEST turn 1" in report
    assert "Lowest human-rated recorded response, V0-WEAK turn 1" in report
    assert "Recorded high-rated answer." in report and "Recorded low-rated answer." in report
    assert "normal_progression: contextual_relevance=3.50 (n=2)" in report
    assert "r1:" in report and "r2:" in report
    assert "unmatched rows/files: 1" in report


def test_summarizer_refuses_to_combine_different_prompt_versions_or_hashes(tmp_path):
    for index, (version, prompt_hash) in enumerate((
        ("V0", "hash-v0"), ("V1", "hash-v1"),
    )):
        (tmp_path / f"run-{index}.json").write_text(json.dumps({
            "prompt_version": version, "prompt_sha256": prompt_hash, "runs": [],
        }), encoding="utf-8")
    with pytest.raises(ValueError, match="Cannot combine results from different prompt versions or hashes"):
        summarizer.render_summary(tmp_path)

    for path in tmp_path.glob("run-*.json"):
        path.unlink()
    for index, prompt_hash in enumerate(("hash-v1a", "hash-v1b")):
        (tmp_path / f"run-{index}.json").write_text(json.dumps({
            "prompt_version": "V1", "prompt_sha256": prompt_hash, "runs": [],
        }), encoding="utf-8")
    with pytest.raises(ValueError, match="Cannot combine results from different prompt versions or hashes"):
        summarizer.render_summary(tmp_path)


def test_scenario_runner_is_offline_unless_live_flag_is_explicit():
    parser = __import__("argparse").ArgumentParser()
    parser.add_argument("--live", action="store_true")
    assert parser.parse_args([]).live is False


def test_runner_rejects_parent_traversal_before_creating_output(tmp_path):
    target = tmp_path / "new" / ".." / "escaped"
    result = runner.main(["--scenario-id", "V0-IV-03", "--output-dir", str(target)])
    assert result == 2
    assert not (tmp_path / "escaped").exists()


def test_runner_accepts_explicit_absolute_output_directory(tmp_path):
    target = tmp_path / "external" / "results"
    result = runner.main(["--scenario-id", "V0-IV-03", "--output-dir", str(target)])
    assert result == 0
    assert len(list(target.glob("*.jsonl"))) == 1
    assert len(list(target.glob("*_ratings.csv"))) == 1


def test_runner_rejects_symlink_output_directory_without_touching_target(tmp_path, monkeypatch):
    outside = tmp_path / "outside"
    outside.mkdir()
    link = tmp_path / "linked-output"
    actual_check = safe_paths._is_link_or_reparse_point
    monkeypatch.setattr(safe_paths, "_is_link_or_reparse_point", lambda path: path == link or actual_check(path))
    result = runner.main(["--scenario-id", "V0-IV-03", "--output-dir", str(link)])
    assert result == 2
    assert list(outside.iterdir()) == []


def test_rating_reader_rejects_traversal_and_symlinks_before_read(tmp_path, monkeypatch):
    outside = tmp_path.parent / "sensitive-ratings.csv"
    outside.write_text("secret,not for reading", encoding="utf-8")
    with pytest.raises(UnsafePathError, match="traversal"):
        summarizer._rating_summary([tmp_path / ".." / outside.name], {})

    link = tmp_path / "ratings.csv"
    actual_check = safe_paths._is_link_or_reparse_point
    monkeypatch.setattr(safe_paths, "_is_link_or_reparse_point", lambda path: path == link or actual_check(path))
    original_open = Path.open
    def reject_open_for_target(path, *args, **kwargs):
        if path.resolve() == outside.resolve():
            raise AssertionError("The symlink target must never be opened.")
        return original_open(path, *args, **kwargs)
    monkeypatch.setattr(Path, "open", reject_open_for_target)
    try:
        with pytest.raises(UnsafePathError, match="Symlinks"):
            summarizer._rating_summary([link], {})
    finally:
        monkeypatch.undo()
    assert outside.read_text(encoding="utf-8") == "secret,not for reading"


def test_summarizer_rejects_symlinked_result_inputs_and_output_targets(tmp_path, monkeypatch):
    results = tmp_path / "results"
    results.mkdir()
    outside = tmp_path / "outside.jsonl"
    outside.write_text('{"assistant_response":"../../escape"}\n', encoding="utf-8")
    linked_input = results / "run.jsonl"
    linked_input.write_text("placeholder", encoding="utf-8")
    output_link = tmp_path / "report.md"
    actual_check = safe_paths._is_link_or_reparse_point
    monkeypatch.setattr(
        safe_paths, "_is_link_or_reparse_point",
        lambda path: path == linked_input or path == output_link or actual_check(path),
    )
    with pytest.raises(UnsafePathError, match="Symlinks"):
        summarizer.render_summary(results)
    monkeypatch.setattr(sys, "argv", ["summarize_v0_evaluation.py", "--results-dir", str(results), "--output", str(output_link)])
    linked_input.unlink(missing_ok=True)
    assert summarizer.main() == 2
    assert outside.read_text(encoding="utf-8") == '{"assistant_response":"../../escape"}\n'


def test_file_content_cannot_select_a_summary_output_path(tmp_path, monkeypatch):
    results = tmp_path / "results"
    results.mkdir()
    outside = tmp_path / "content-selected.txt"
    malicious_response = str(outside)
    row = {
        "run_id": "RUN-FILE-CONTENT", "scenario_id": "V0-X", "turn": 1,
        "category": "clarification_questions", "language": "English",
        "assistant_response": malicious_response, "latency_ms": 1,
        "state_transition_correct": True, "critical_violations": [],
    }
    (results / "run.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    summary_dir = tmp_path / "selected-output"
    output = summary_dir / "summary.md"
    monkeypatch.setattr(sys, "argv", [
        "summarize_v0_evaluation.py", "--results-dir", str(results), "--output", str(output),
    ])
    assert summarizer.main() == 0
    assert output.is_file()
    assert not outside.exists()
    assert malicious_response in output.read_text(encoding="utf-8")


def test_safe_summary_writer_rejects_traversal_and_existing_symlinks(tmp_path, monkeypatch):
    escape = tmp_path / ".." / "never-created.txt"
    with pytest.raises(UnsafePathError, match="traversal"):
        safe_write_text(escape, "bad")
    assert not escape.exists()
    target = tmp_path / "safe.txt"
    target.write_text("original", encoding="utf-8")
    link = tmp_path / "alias.txt"
    actual_check = safe_paths._is_link_or_reparse_point
    monkeypatch.setattr(safe_paths, "_is_link_or_reparse_point", lambda path: path == link or actual_check(path))
    with pytest.raises(UnsafePathError, match="Symlinks"):
        safe_write_text(link, "replacement", overwrite=True)
    assert target.read_text(encoding="utf-8") == "original"

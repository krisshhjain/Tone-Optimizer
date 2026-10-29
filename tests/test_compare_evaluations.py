import csv
from pathlib import Path

import pytest

from scripts import compare_v0_v1_evaluation as compare
from scripts.prepare_v0_v1_review_sheet import prepare


def metadata(version, run_id):
    prompt_hash = compare.V0_HASH if version == "V0" else compare.V1_HASH
    return {
        "run_id": run_id, "prompt_version": version, "prompt_sha256": prompt_hash,
        "mode": "live", "model_id": "nemotron-test", "generation_settings": {
            "temperature": 0.2, "top_p": 0.9, "maximum_tokens": 100, "timeout_seconds": 30,
        }, "rules_sha256": "a" * 64, "git_commit_sha": "b" * 40,
        "git_worktree_dirty": False,
    }


def row(turn=1, scenario="S-01", **updates):
    base = {
        "run_id": "run", "scenario_id": scenario, "turn": turn,
        "state_transition_correct": True, "critical_violations": [],
        "assistant_response": "Observed response.", "api_error": None, "latency_ms": 100,
        "state_after": {"accepted_values": {}, "staged_values": {}}, "tool_events": [],
    }
    return {**base, **updates}


def pair():
    m0, m1 = metadata("V0", "run"), metadata("V1", "run")
    def tagged(m):
        return row(prompt_version=m["prompt_version"], prompt_sha256=m["prompt_sha256"],
                   model_id=m["model_id"], generation_settings=m["generation_settings"],
                   rules_sha256=m["rules_sha256"], git_commit_sha=m["git_commit_sha"])
    return m0, [tagged(m0)], m1, [tagged(m1)]


def test_pairs_scenario_turn_and_reports_workflow_separately():
    m0, r0, m1, r1 = pair()
    m0["mode"] = m1["mode"] = "offline"
    report, details = compare.build_comparison(m0, r0, m1, r1)
    assert details["paired_turns"] == 1
    assert details["workflow"]["V0"]["expected_transition_matches"] == 1
    assert details["quality"]["naturalness"]["v0_mean"] is None
    assert "not assessed" in report.lower()


def test_missing_turns_are_reported_not_fabricated():
    m0, r0, m1, r1 = pair()
    r1.append(row(2, prompt_version="V1", prompt_sha256=compare.V1_HASH,
                  model_id=m1["model_id"], generation_settings=m1["generation_settings"],
                  rules_sha256=m1["rules_sha256"], git_commit_sha=m1["git_commit_sha"]))
    _, details = compare.build_comparison(m0, r0, m1, r1)
    assert details["paired_turns"] == 1
    assert any("Missing V0 turns" in d for d in details["diagnostics"])


def test_duplicate_turn_is_rejected():
    m0, r0, m1, r1 = pair()
    with pytest.raises(compare.ComparisonError, match="duplicate"):
        compare.build_comparison(m0, r0 + [row()], m1, r1)


@pytest.mark.parametrize(("field", "value"), [
    ("model_id", "other-model"), ("generation_settings", {"temperature": 1}),
    ("rules_sha256", "c" * 64), ("git_commit_sha", "d" * 40),
])
def test_mismatched_controller_or_model_metadata_is_rejected(field, value):
    m0, r0, m1, r1 = pair()
    m1[field] = value
    with pytest.raises(compare.ComparisonError, match="Metadata compatibility"):
        compare.build_comparison(m0, r0, m1, r1)


def test_wrong_prompt_version_and_hash_are_rejected():
    m0, r0, m1, r1 = pair()
    m0["prompt_version"] = "V1"
    with pytest.raises(compare.ComparisonError, match="V0 is labeled"):
        compare.build_comparison(m0, r0, m1, r1)
    m0, r0, m1, r1 = pair()
    m1["prompt_sha256"] = "e" * 64
    with pytest.raises(compare.ComparisonError, match="V1 prompt hash"):
        compare.build_comparison(m0, r0, m1, r1)
    m0, r0, m1, r1 = pair()
    m0["prompt_sha256"] = "f" * 64
    with pytest.raises(compare.ComparisonError, match="V0 prompt hash"):
        compare.build_comparison(m0, r0, m1, r1)


def write_ratings(path: Path, run_id: str, reviewer: str, naturalness: str, clarity: str = ""):
    fields = ["run_id", "scenario_id", "turn", "reviewer_id", *compare.DIMENSIONS]
    rowdata = {"run_id": run_id, "scenario_id": "S-01", "turn": "1", "reviewer_id": reviewer,
               "naturalness": naturalness, "clarity": clarity}
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader(); writer.writerow(rowdata)


def test_only_complete_same_reviewer_ratings_are_paired_and_critical_flags_stay_workflow():
    m0, r0, m1, r1 = pair()
    r0[0]["critical_violations"] = ["expectation mismatch"]
    v0file = Path(__file__).with_name("_ratings_v0_test.csv")
    v1file = Path(__file__).with_name("_ratings_v1_test.csv")
    try:
        write_ratings(v0file, "run", "reviewer-a", "3", clarity="4")
        write_ratings(v1file, "run", "reviewer-a", "5")
        report, details = compare.build_comparison(m0, r0, m1, r1, [v0file], [v1file])
    finally:
        v0file.unlink(missing_ok=True)
        v1file.unlink(missing_ok=True)
    assert details["quality"]["naturalness"]["paired_difference"] == 2
    assert details["quality"]["naturalness"]["paired_n"] == 1
    assert details["quality"]["clarity"]["paired_n"] == 0
    assert details["workflow"]["V0"]["critical_violation_candidates"] == 1
    assert "mismatch candidates 1" in report


def test_unrated_live_records_remain_unrated():
    m0, r0, m1, r1 = pair()
    report, details = compare.build_comparison(m0, r0, m1, r1)
    assert details["quality"]["naturalness"]["v0_mean"] is None
    assert details["quality"]["naturalness"]["paired_difference"] is None
    assert "Not rated" in report


def test_incomplete_run_is_reported():
    m0, r0, m1, r1 = pair()
    m0["runs"] = [{"scenario_id": "S-01", "status": "failed", "turns": [{"turn": 1}]}]
    _, details = compare.build_comparison(m0, r0, m1, r1)
    assert any("incomplete/failed" in d for d in details["diagnostics"])


def test_blinded_review_sheet_preserves_responses_and_rejects_offline():
    m0, r0, m1, r1 = pair()
    m0["mode"] = m1["mode"] = "offline"
    with pytest.raises(compare.ComparisonError, match="require live"):
        prepare(m0, r0, m1, r1)
    m0, r0, m1, r1 = pair()
    sheet, key = prepare(m0, r0, m1, r1)
    assert "Observed response." in sheet
    assert "response_A" in sheet and "response_B" in sheet
    assert "version_A" in key and "version_B" in key

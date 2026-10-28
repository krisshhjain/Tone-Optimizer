"""Run fixed V0 scenarios offline with mocks, or live with an explicit opt-in."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.manager import run_manager_turn
from core.model_client import GenerationSettings, ModelConfig, ModelError
from core.rules import load_rules
from core.state import initialize_scenario

SCENARIOS_PATH = ROOT / "evaluation" / "scenarios.json"
PROMPT_PATH = ROOT / "prompts" / "v0_orchestration.md"
PROMPT_HASH_PATH = ROOT / "prompts" / "v0_baseline.sha256"
RULES_PATH = ROOT / "config" / "pl_rules.json"
RATING_FIELDS = [
    "contextual_relevance", "naturalness", "repetition", "clarity",
    "language_adaptation", "state_awareness",
]


def _completion(message: Any) -> Any:
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class OfflineClient:
    """Mock only model extraction/generation; Manager and helper remain real."""

    def __init__(self, turn: dict[str, Any]):
        self.turn = turn
        self.calls = 0
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **_kwargs: Any) -> Any:
        self.calls += 1
        if self.turn.get("offline_error") and self.calls == 1:
            raise TimeoutError("mock offline timeout")
        entries = self.turn.get("offline_entries", [])
        if entries and self.calls == 1:
            call = SimpleNamespace(
                id="offline-call-1",
                function=SimpleNamespace(
                    name="submit_information",
                    arguments=json.dumps({"entries": entries}),
                ),
            )
            return _completion(SimpleNamespace(content=None, tool_calls=[call]))
        if entries and self.calls == 2 and self.turn.get("offline_error_after_helper"):
            raise TimeoutError("mock follow-up timeout")
        return _completion(SimpleNamespace(
            content="Mocked offline response; not a Nemotron observation.", tool_calls=[],
        ))


class RequestBudget:
    """Wrap an API client and prevent requests beyond an explicit count."""

    def __init__(self, client: Any, limit: int):
        self.calls = 0
        self.limit = limit
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))
        self._create = client.chat.completions.create

    def create(self, **kwargs: Any) -> Any:
        if self.calls >= self.limit:
            raise RuntimeError("Live request limit reached")
        self.calls += 1
        return self._create(**kwargs)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_sha() -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
            capture_output=True, text=True, timeout=3,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def _git_dirty() -> bool | None:
    try:
        status = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"], cwd=ROOT,
            check=True, capture_output=True, text=True, timeout=3,
        ).stdout
        return bool(status.strip())
    except (OSError, subprocess.SubprocessError):
        return None


def _snapshot(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "accepted_values": state["accepted_values"].copy(),
        "staged_values": state["pending_values"].copy(),
    }


def _active_field(state: dict[str, Any]) -> str | None:
    values = state["accepted_values"]
    return next((rule["field"] for rule in load_rules() if rule["field"] not in values), None)


def _settings(config: ModelConfig) -> dict[str, int | float]:
    values = config.settings.as_metadata()
    return {
        "temperature": values["temperature"], "top_p": values["top_p"],
        "maximum_tokens": values["max_tokens"], "timeout_seconds": values["timeout_seconds"],
    }


def _run_scenario(
    scenario: dict[str, Any], config: ModelConfig, mode: str,
    live_client: Any = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    state = initialize_scenario(scenario["starting_preset"])
    turn_rows: list[dict[str, Any]] = []
    overall_error: list[str] = []
    expected_errors: list[str] = []
    for index, turn in enumerate(scenario["turns"], start=1):
        before = _snapshot(state)
        previous_event_count = len(state["tool_events"])
        client = OfflineClient(turn) if mode == "offline" else live_client
        started = time.perf_counter()
        result = run_manager_turn(state, turn["message"], config, client=client)
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        state = result["state"]
        after = _snapshot(state)
        events = state["tool_events"][previous_event_count:]
        expected_active = turn.get("expected_active_field")
        active_matches = _active_field(state) == expected_active
        accepted_matches = after["accepted_values"] == turn["expected_accepted_values"]
        staged_matches = after["staged_values"] == turn["expected_staged_values"]
        change_matches = (before != after) == turn["expected_state_change"]
        expected_tool = turn.get("expected_tool")
        tool_matches = (
            not any(event["tool"] == "submit_information" for event in events)
            if expected_tool == "no_state_changing_tool"
            else any(event["tool"] == expected_tool for event in events)
        )
        correctness = active_matches and accepted_matches and staged_matches and change_matches and tool_matches
        if result["error"]:
            expected_mock_error = mode == "offline" and (
                turn.get("offline_error") or turn.get("offline_error_after_helper")
            )
            (expected_errors if expected_mock_error else overall_error).append(result["error"])
        row = {
            "turn": index, "customer_message": turn["message"],
            "assistant_response": result["reply"], "state_before": before,
            "state_after": after, "active_rule_after": _active_field(state),
            "tool_events": events, "latency_ms": latency_ms,
            "api_error": result["error"],
            "critical_violations": (
                ["Unexpected deterministic state/tool transition"] if not correctness else []
            ),
            "expected": {
                "active_field": expected_active,
                "state_change": turn["expected_state_change"], "tool": expected_tool,
                "accepted_values": turn["expected_accepted_values"],
                "staged_values": turn["expected_staged_values"],
            },
            "state_transition_correct": correctness,
        }
        turn_rows.append(row)
    run_summary = {
        "scenario_id": scenario["id"], "status": "failed" if overall_error else "successful",
        "errors": overall_error, "expected_errors": expected_errors, "turn_count": len(turn_rows),
        "final_state": _snapshot(state), "final_active_field": _active_field(state),
        "turns": turn_rows,
    }
    return turn_rows, run_summary


def _write_rating_template(
    path: Path, scenarios: list[dict[str, Any]] | None = None,
    run_id: str = "", model_id: str = "",
) -> None:
    fields = ["run_id", "scenario_id", "prompt_version", "model_id", "reviewer_id", *RATING_FIELDS,
              "critical_violations", "reviewer_notes"]
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for scenario in scenarios or []:
                writer.writerow({
                    "run_id": run_id, "scenario_id": scenario["id"],
                    "prompt_version": "V0", "model_id": model_id,
                })


def _load_scenarios() -> list[dict[str, Any]]:
    scenarios = json.loads(SCENARIOS_PATH.read_text(encoding="utf-8"))
    if not isinstance(scenarios, list) or not scenarios:
        raise ValueError("Scenario file must contain a non-empty array.")
    ids = [item.get("id") for item in scenarios]
    if len(ids) != len(set(ids)):
        raise ValueError("Scenario IDs must be unique.")
    for scenario in scenarios:
        if scenario.get("starting_preset") not in {
            "Fresh application", "Tenure pending", "Monthly income pending", "Document receipt pending",
        }:
            raise ValueError(f"Unknown preset in {scenario.get('id')}.")
        if not isinstance(scenario.get("turns"), list) or not scenario["turns"]:
            raise ValueError(f"Scenario {scenario.get('id')} has no turns.")
        for turn in scenario["turns"]:
            if not all(key in turn for key in (
                "message", "expected_active_field", "expected_state_change", "expected_tool",
                "expected_accepted_values", "expected_staged_values",
            )):
                raise ValueError(f"Scenario {scenario['id']} has an incomplete turn schema.")
    return scenarios


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--scenario-id")
    selection.add_argument("--category")
    selection.add_argument("--all", action="store_true", help="run every scenario (the default)")
    parser.add_argument("--live", action="store_true", help="explicitly opt into provider requests")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "evaluation" / "results")
    parser.add_argument("--max-live-requests", type=int, default=10)
    args = parser.parse_args(argv)
    if args.max_live_requests < 1:
        parser.error("--max-live-requests must be at least 1")

    scenarios = _load_scenarios()
    expected_prompt_hash = PROMPT_HASH_PATH.read_text(encoding="utf-8").split()[0]
    actual_prompt_hash = _sha(PROMPT_PATH)
    if actual_prompt_hash != expected_prompt_hash:
        print(
            "The V0 prompt differs from the pinned baseline. Record it as a separate experiment; "
            "do not combine it with pinned V0 results.", file=sys.stderr,
        )
        return 2
    if args.scenario_id:
        scenarios = [item for item in scenarios if item["id"] == args.scenario_id]
    elif args.category:
        scenarios = [item for item in scenarios if item["category"] == args.category]
    if not scenarios:
        parser.error("No scenarios matched the requested selection")

    live_client = None
    if args.live:
        try:
            from core.model_client import _make_client
            config = ModelConfig.from_env()
            live_client = RequestBudget(_make_client(config), args.max_live_requests)
        except ModelError as exc:
            print(f"Live evaluation configuration failed: {exc}", file=sys.stderr)
            return 2
        mode = "live"
    else:
        config = ModelConfig("offline-placeholder", "offline://mock", "offline-mock", GenerationSettings())
        mode = "offline"

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    metadata = {
        "run_id": run_id, "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "mode": mode, "prompt_version": "V0", "model_id": config.model,
        "generation_settings": _settings(config), "prompt_sha256": actual_prompt_hash,
        "rules_sha256": _sha(RULES_PATH), "git_commit_sha": _git_sha(),
        "git_worktree_dirty": _git_dirty(),
    }
    all_turns: list[dict[str, Any]] = []
    summaries = []
    for scenario in scenarios:
        if args.live and not scenario["requires_live_api"] and args.scenario_id is None and args.category is None:
            # All scenarios are still run when --all is selected; this flag records expected API need only.
            pass
        turns, summary = _run_scenario(scenario, config, mode, live_client)
        summary["initial_preset"] = scenario["starting_preset"]
        summaries.append(summary)
        for turn_index, row in enumerate(turns):
            all_turns.append({
                **metadata, "scenario_id": scenario["id"], "category": scenario["category"],
                "language": scenario.get("language", "English"),
                "requires_live_api": scenario["requires_live_api"],
                "initial_preset": scenario["starting_preset"], "turn": row["turn"],
                **{key: value for key, value in row.items() if key != "turn"},
            })
    args.output_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = args.output_dir / f"{run_id}.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as handle:
        for row in all_turns:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    summary_path = args.output_dir / f"{run_id}.json"
    summary_path.write_text(json.dumps({**metadata, "runs": summaries}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _write_rating_template(
        args.output_dir / f"{run_id}_ratings.csv", scenarios, run_id, config.model,
    )
    print(f"Mode: {mode}; scenarios: {len(summaries)}; turn records: {len(all_turns)}")
    print(f"Turn data: {jsonl_path}")
    print(f"Run metadata and final states: {summary_path}")
    if live_client is not None:
        print(f"Live API requests used: {live_client.calls}/{live_client.limit}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

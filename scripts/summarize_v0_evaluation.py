"""Summarize recorded V0 runs and optional human ratings as Markdown."""

from __future__ import annotations

import argparse
import csv
import io
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.safe_paths import (
    UnsafePathError,
    checked_path,
    ensure_directory,
    safe_read_text,
    safe_write_text,
)

RATING_FIELDS = [
    "contextual_relevance", "naturalness", "repetition", "clarity",
    "language_adaptation", "state_awareness",
]


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line in safe_read_text(path).splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _rating_summary(
    paths: list[Path], recorded_turns: dict[tuple[str, str, int], dict[str, Any]],
) -> tuple[list[str], dict[str, list[int]], dict[tuple[str, str, int], float]]:
    scores: dict[str, list[int]] = defaultdict(list)
    language_scores: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    category_scores: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    turn_scores: dict[tuple[str, str, int], list[int]] = defaultdict(list)
    reviewer_scores: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    loaded = 0
    unmatched = 0
    for path in paths:
        try:
            content = safe_read_text(path, encoding="utf-8-sig")
        except FileNotFoundError:
            continue
        reader = csv.DictReader(io.StringIO(content, newline=""))
        required = {"run_id", "scenario_id", "turn", "reviewer_id"}
        if not required.issubset(reader.fieldnames or []):
            unmatched += 1
            continue
        for row in reader:
            loaded += 1
            try:
                key = (row["run_id"].strip(), row["scenario_id"].strip(), int(row["turn"]))
            except (AttributeError, TypeError, ValueError):
                unmatched += 1
                continue
            recorded = recorded_turns.get(key)
            if recorded is None:
                unmatched += 1
                continue
            language = recorded.get("language", "Unknown")
            category = recorded.get("category", "Unknown")
            reviewer = (row.get("reviewer_id") or "").strip() or "Unspecified reviewer"
            row_scores = []
            for field in RATING_FIELDS:
                value = (row.get(field) or "").strip()
                if not value:
                    continue
                try:
                    score = int(value)
                except ValueError:
                    continue
                if 1 <= score <= 5:
                    row_scores.append(score)
                    scores[field].append(score)
                    language_scores[language][field].append(score)
                    category_scores[category][field].append(score)
                    reviewer_scores[reviewer][field].append(score)
            turn_scores[key].extend(row_scores)
    lines = [f"Rating rows inspected: {loaded}; unmatched rows/files: {unmatched}."]
    for field in RATING_FIELDS:
        values = scores[field]
        lines.append(
            f"- {field}: {statistics.mean(values):.2f} (n={len(values)})" if values
            else f"- {field}: Not rated"
        )
    lines.append("Language adaptation by recorded scenario language:")
    for language in ("English", "Hindi", "Hinglish"):
        values = language_scores[language]["language_adaptation"]
        lines.append(
            f"- {language}: {statistics.mean(values):.2f} (n={len(values)})" if values
            else f"- {language}: Not rated"
        )
    lines.append("Human rubric averages by scenario category:")
    categories = {row.get("category", "Unknown") for row in recorded_turns.values()}
    for category in sorted(categories | set(category_scores)):
        dimensions = category_scores.get(category, {})
        rated = [f"{field}={statistics.mean(values):.2f} (n={len(values)})" for field, values in dimensions.items()]
        lines.append(f"- {category}: " + (", ".join(rated) if rated else "Not rated"))
    lines.append("Human rubric averages by reviewer ID:")
    for reviewer, dimensions in sorted(reviewer_scores.items()):
        rated = [f"{field}={statistics.mean(values):.2f} (n={len(values)})" for field, values in dimensions.items()]
        lines.append(f"- {reviewer}: " + ", ".join(rated))
    turn_averages = {
        key: statistics.mean(values) for key, values in turn_scores.items() if values
    }
    return lines, scores, turn_averages


def render_summary(results_dir: Path, ratings: list[Path] | None = None) -> str:
    results_root = ensure_directory(results_dir, create=False)
    turn_paths = sorted(results_root.glob("*.jsonl"))
    run_paths = sorted(path for path in results_root.glob("*.json") if path.name != "summary.json")
    turns = [row for path in turn_paths for row in _read_jsonl(path)]
    runs = [json.loads(safe_read_text(path)) for path in run_paths]
    scenario_runs = [item for run in runs for item in run.get("runs", [])]
    executed = len(scenario_runs)
    successful = sum(item.get("status") == "successful" for item in scenario_runs)
    failed = sum(item.get("status") == "failed" for item in scenario_runs)
    correct = sum(row.get("state_transition_correct") is True for row in turns)
    violation_count = sum(len(row.get("critical_violations", [])) for row in turns)
    latencies = [row["latency_ms"] for row in turns if isinstance(row.get("latency_ms"), (int, float))]
    recorded_turns = {
        (row.get("run_id", ""), row.get("scenario_id", ""), row.get("turn")): row
        for row in turns
        if isinstance(row.get("turn"), int)
    }
    rating_paths = ratings if ratings is not None else sorted(results_root.glob("*_ratings.csv"))
    rating_lines, _scores, turn_averages = _rating_summary(rating_paths, recorded_turns)

    lines = [
        "# V0 evaluation summary", "",
        f"- Scenarios executed: {executed}",
        f"- Successful scenario runs: {successful}",
        f"- Failed scenario runs: {failed}",
        f"- State-transition correctness: {correct}/{len(turns)} ({(correct / len(turns) * 100):.1f}%)" if turns
        else "- State-transition correctness: Not available (no turns recorded)",
        f"- Detected critical workflow violation candidates: {violation_count}",
        f"- Mean latency: {statistics.mean(latencies):.2f} ms" if latencies else "- Mean latency: Not available",
        f"- Median latency: {statistics.median(latencies):.2f} ms" if latencies else "- Median latency: Not available",
        "", "## Human ratings", "", *rating_lines, "",
        "Scores omit blank and invalid cells; missing ratings are not treated as zero.",
        "Critical violation candidates are deterministic expected-transition mismatches, not a complete semantic audit of model prose.",
        "", "## Category state-transition results", "",
    ]
    by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in turns:
        by_category[row.get("category", "Unknown")].append(row)
    for category, rows in sorted(by_category.items()):
        count = sum(row.get("state_transition_correct") is True for row in rows)
        lines.append(f"- {category}: {count}/{len(rows)} turns matched expected state/tool behavior")
    lines.extend(["", "## Recorded response examples", ""])
    recorded = [row for row in turns if isinstance(row.get("assistant_response"), str) and row["assistant_response"].strip()]
    if turn_averages:
        best_key = max(turn_averages, key=turn_averages.get)
        worst_key = min(turn_averages, key=turn_averages.get)
        strong = recorded_turns.get(best_key)
        weak = recorded_turns.get(worst_key)
    else:
        strong = next((row for row in recorded if row.get("state_transition_correct")), None)
        weak = next((row for row in recorded if not row.get("state_transition_correct")), None)
    if turn_averages and strong:
        key = (strong["run_id"], strong["scenario_id"], strong["turn"])
        lines.append(f"- Highest human-rated recorded response, {strong['scenario_id']} turn {strong['turn']} (mean {turn_averages[key]:.2f}/5): > {strong['assistant_response'][:300]}")
    elif strong:
        lines.append(f"- Strong workflow example, {strong['scenario_id']} turn {strong['turn']}: > {strong['assistant_response'][:300]}")
    else:
        lines.append("- Strong example: Not available in recorded runs.")
    if turn_averages and weak:
        key = (weak["run_id"], weak["scenario_id"], weak["turn"])
        lines.append(f"- Lowest human-rated recorded response, {weak['scenario_id']} turn {weak['turn']} (mean {turn_averages[key]:.2f}/5): > {weak['assistant_response'][:300]}")
    elif weak:
        lines.append(f"- Weak workflow example, {weak['scenario_id']} turn {weak['turn']}: > {weak['assistant_response'][:300]}")
    else:
        lines.append("- Weak example: No weak workflow response was flagged in these recorded runs; none was invented.")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", type=Path, default=ROOT / "evaluation" / "results")
    parser.add_argument("--ratings", type=Path, action="append", help="rating CSV; may be supplied more than once")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        results_dir = ensure_directory(args.results_dir, create=True)
        summary = render_summary(results_dir, args.ratings)
        output = checked_path(args.output) if args.output else results_dir / "summary.md"
        ensure_directory(output.parent, create=True)
        safe_write_text(output, summary, overwrite=True)
    except (UnsafePathError, OSError, csv.Error, json.JSONDecodeError) as exc:
        print(f"Could not safely summarize evaluation results: {exc}")
        return 2
    print(f"Summary written to {output}")
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

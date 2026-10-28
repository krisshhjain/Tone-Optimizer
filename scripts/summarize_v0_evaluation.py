"""Summarize recorded V0 runs and optional human ratings as Markdown."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RATING_FIELDS = [
    "contextual_relevance", "naturalness", "repetition", "clarity",
    "language_adaptation", "state_awareness",
]


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _rating_summary(
    paths: list[Path], language_by_scenario: dict[str, str], category_by_scenario: dict[str, str],
) -> tuple[list[str], dict[str, list[int]], dict[str, float]]:
    scores: dict[str, list[int]] = defaultdict(list)
    language_scores: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    category_scores: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    scenario_scores: dict[str, list[int]] = defaultdict(list)
    loaded = 0
    for path in paths:
        if not path.exists():
            continue
        with path.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                loaded += 1
                language = language_by_scenario.get(row.get("scenario_id", ""), "Unknown")
                category = category_by_scenario.get(row.get("scenario_id", ""), "Unknown")
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
                scenario_scores[row.get("scenario_id", "")].extend(row_scores)
    lines = [f"Rating rows inspected: {loaded}."]
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
    for category in sorted(set(category_by_scenario.values()) | set(category_scores)):
        dimensions = category_scores.get(category, {})
        rated = [f"{field}={statistics.mean(values):.2f} (n={len(values)})" for field, values in dimensions.items()]
        lines.append(f"- {category}: " + (", ".join(rated) if rated else "Not rated"))
    scenario_averages = {
        scenario_id: statistics.mean(values) for scenario_id, values in scenario_scores.items() if values
    }
    return lines, scores, scenario_averages


def render_summary(results_dir: Path, ratings: list[Path] | None = None) -> str:
    turn_paths = sorted(results_dir.glob("*.jsonl"))
    run_paths = sorted(path for path in results_dir.glob("*.json") if path.name != "summary.json")
    turns = [row for path in turn_paths for row in _read_jsonl(path)]
    runs = [json.loads(path.read_text(encoding="utf-8")) for path in run_paths]
    scenario_runs = [item for run in runs for item in run.get("runs", [])]
    executed = len(scenario_runs)
    successful = sum(item.get("status") == "successful" for item in scenario_runs)
    failed = sum(item.get("status") == "failed" for item in scenario_runs)
    correct = sum(row.get("state_transition_correct") is True for row in turns)
    violation_count = sum(len(row.get("critical_violations", [])) for row in turns)
    latencies = [row["latency_ms"] for row in turns if isinstance(row.get("latency_ms"), (int, float))]
    language_by_scenario = {row.get("scenario_id"): row.get("language", "Unknown") for row in turns}
    rating_paths = ratings if ratings is not None else sorted(results_dir.glob("*_ratings.csv"))
    category_by_scenario = {row.get("scenario_id"): row.get("category", "Unknown") for row in turns}
    rating_lines, _scores, scenario_averages = _rating_summary(
        rating_paths, language_by_scenario, category_by_scenario,
    )

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
    if scenario_averages:
        by_id = {row.get("scenario_id"): row for row in recorded}
        available = {key: score for key, score in scenario_averages.items() if key in by_id}
        best_id = max(available, key=available.get) if available else None
        worst_id = min(available, key=available.get) if available else None
        strong = by_id.get(best_id) if best_id else None
        weak = by_id.get(worst_id) if worst_id else None
    else:
        strong = next((row for row in recorded if row.get("state_transition_correct")), None)
        weak = next((row for row in recorded if not row.get("state_transition_correct")), None)
    if scenario_averages and strong:
        lines.append(f"- Highest human-rated recorded response, {strong['scenario_id']} turn {strong['turn']} (mean {scenario_averages[strong['scenario_id']]:.2f}/5): > {strong['assistant_response'][:300]}")
    elif strong:
        lines.append(f"- Strong workflow example, {strong['scenario_id']} turn {strong['turn']}: > {strong['assistant_response'][:300]}")
    else:
        lines.append("- Strong example: Not available in recorded runs.")
    if scenario_averages and weak:
        lines.append(f"- Lowest human-rated recorded response, {weak['scenario_id']} turn {weak['turn']} (mean {scenario_averages[weak['scenario_id']]:.2f}/5): > {weak['assistant_response'][:300]}")
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
    summary = render_summary(args.results_dir, args.ratings)
    output = args.output or args.results_dir / "summary.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(summary, encoding="utf-8")
    print(f"Summary written to {output}")
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

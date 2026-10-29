"""Compare paired V0/V1 evaluation artifacts without inventing evidence."""
from __future__ import annotations
import argparse, csv, hashlib, io, json, statistics, sys
from collections import Counter
from pathlib import Path
from typing import Any
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.safe_paths import UnsafePathError, ensure_directory, safe_read_text, safe_write_text

V0_HASH = "69e6071c19c1ed66f48893bc79b33ad9078cb9244edb8d7562b435be27f42c99"
V1_HASH = hashlib.sha256((ROOT / "prompts" / "v1_conversational.md").read_bytes()).hexdigest()
SCENARIOS_PATH = ROOT / "evaluation" / "scenarios.json"
DIMENSIONS = ("contextual_relevance", "naturalness", "repetition", "clarity", "language_adaptation", "state_awareness")

class ComparisonError(ValueError):
    pass

def _load_json(path: Path) -> Any:
    return json.loads(safe_read_text(path))

def _select_run(directory: Path, selected: str | None):
    root = ensure_directory(directory, create=False)
    paths = sorted(p for p in root.glob("*.json") if p.name != "summary.json")
    if selected:
        paths = [p for p in paths if _load_json(p).get("run_id") == selected]
    if len(paths) != 1:
        raise ComparisonError(f"Expected exactly one selected run in {root}; found {len(paths)}. Use explicit run IDs.")
    metadata = _load_json(paths[0])
    run_id = metadata.get("run_id")
    rows = [json.loads(line) for p in sorted(root.glob("*.jsonl"))
            for line in safe_read_text(p).splitlines() if line.strip()]
    rows = [r for r in rows if r.get("run_id") == run_id]
    if not rows:
        raise ComparisonError(f"No turn rows for run {run_id}.")
    return metadata, rows, sorted(root.glob("*_ratings.csv"))

def _rows(rows, version):
    out = {}
    for row in rows:
        key = row.get("scenario_id"), row.get("turn")
        if not isinstance(key[0], str) or not isinstance(key[1], int):
            raise ComparisonError("Turn records require string scenario_id and integer turn.")
        if key in out:
            raise ComparisonError(f"Ambiguous duplicate {version} record: {key}.")
        out[key] = row
    return out

def _turn_metadata(rows, metadata, label):
    for row in rows.values():
        for field in ("run_id", "prompt_version", "prompt_sha256", "model_id",
                      "generation_settings", "rules_sha256", "git_commit_sha"):
            if row.get(field) != metadata.get(field):
                raise ComparisonError(f"{label} turn/run metadata mismatch for {field}.")

def _check_metadata(a, b):
    issues = []
    for label, m, expected in (("V0", a, "V0"), ("V1", b, "V1")):
        if m.get("prompt_version") != expected:
            issues.append(f"{label} is labeled {m.get('prompt_version')!r}.")
        if not isinstance(m.get("prompt_sha256"), str) or len(m["prompt_sha256"]) != 64:
            issues.append(f"{label} prompt hash is missing/malformed.")
        if m.get("mode") not in ("offline", "live"):
            issues.append(f"{label} mode is missing.")
        if m.get("git_worktree_dirty") is not False:
            issues.append(f"{label} worktree dirty state is not clean/known.")
    if a.get("prompt_sha256") != V0_HASH:
        issues.append("V0 prompt hash differs from the pinned baseline.")
    if b.get("prompt_sha256") != V1_HASH:
        issues.append("V1 prompt hash does not match the V1 prompt in this checkout.")
    for label, field in (("model ID", "model_id"), ("settings", "generation_settings"),
                         ("rule hash", "rules_sha256"), ("controller revision", "git_commit_sha")):
        if not a.get(field) or not b.get(field) or a[field] != b[field]:
            issues.append(f"Incompatible/missing {label}: {a.get(field)!r} vs {b.get(field)!r}.")
    if a.get("mode") != b.get("mode"):
        issues.append("Cannot pair live and offline artifacts.")
    if issues:
        raise ComparisonError("Metadata compatibility checks failed:\n- " + "\n- ".join(issues))

def _ratings(paths, run_id, recorded):
    out = {}
    for path in paths:
        reader = csv.DictReader(io.StringIO(safe_read_text(path, encoding="utf-8-sig"), newline=""))
        if not {"run_id", "scenario_id", "turn", "reviewer_id", *DIMENSIONS}.issubset(reader.fieldnames or []):
            continue
        for row in reader:
            if row.get("run_id", "").strip() != run_id:
                continue
            try:
                key0 = row["scenario_id"].strip(), int(row["turn"]), row["reviewer_id"].strip()
            except (ValueError, AttributeError, TypeError):
                continue
            if not key0[2] or key0[:2] not in recorded:
                continue
            for dim in DIMENSIONS:
                val = (row.get(dim) or "").strip()
                if not val:
                    continue
                try:
                    score = int(val)
                except ValueError:
                    continue
                if score not in range(1, 6):
                    continue
                key = (*key0, dim)
                if key in out:
                    raise ComparisonError(f"Duplicate rating: {key}.")
                out[key] = score
    return out

def build_comparison(m0, rows0, m1, rows1, rating_paths0=(), rating_paths1=()):
    _check_metadata(m0, m1)
    a, b = _rows(rows0, "V0"), _rows(rows1, "V1")
    _turn_metadata(a, m0, "V0")
    _turn_metadata(b, m1, "V1")
    shared = sorted(set(a) & set(b))
    missing_a, missing_b = sorted(set(b)-set(a)), sorted(set(a)-set(b))
    diag = []
    if missing_a: diag.append(f"Missing V0 turns: {missing_a}")
    if missing_b: diag.append(f"Missing V1 turns: {missing_b}")
    scenarios_a, scenarios_b = {k[0] for k in a}, {k[0] for k in b}
    expected_scenarios = json.loads(safe_read_text(SCENARIOS_PATH))
    expected_ids = {s["id"] for s in expected_scenarios}
    if scenarios_a != expected_ids:
        diag.append(f"V0 scenario coverage vs fixed dataset: missing={sorted(expected_ids-scenarios_a)}, unexpected={sorted(scenarios_a-expected_ids)}")
    if scenarios_b != expected_ids:
        diag.append(f"V1 scenario coverage vs fixed dataset: missing={sorted(expected_ids-scenarios_b)}, unexpected={sorted(scenarios_b-expected_ids)}")
    for label, data in (("V0", a), ("V1", b)):
        expected_turn_keys = {(s["id"], i) for s in expected_scenarios for i, _ in enumerate(s["turns"], 1)}
        absent = expected_turn_keys - set(data)
        if absent:
            diag.append(f"{label} fixed-dataset turns missing: {sorted(absent)}")
    if scenarios_a != scenarios_b: diag.append(f"Scenario coverage differs: V0-only={sorted(scenarios_a-scenarios_b)}, V1-only={sorted(scenarios_b-scenarios_a)}")
    for label, meta, data in (("V0", m0, a), ("V1", m1, b)):
        summaries = meta.get("runs", [])
        expected = {(s.get("scenario_id"), t.get("turn")) for s in summaries for t in s.get("turns", [])}
        if expected and expected != set(data): diag.append(f"{label} summary and JSONL coverage differ.")
        failed = [s.get("scenario_id") for s in summaries if s.get("status") != "successful"]
        if failed: diag.append(f"{label} incomplete/failed scenarios: {failed}")
    workflow = {}
    for label, data in (("V0", a), ("V1", b)):
        selected = [data[k] for k in shared]
        latency = [r["latency_ms"] for r in selected if isinstance(r.get("latency_ms"), (int, float))]
        unexpected_tools = 0
        for r in selected:
            expected = (r.get("expected") or {}).get("tool")
            actual = [e.get("tool") for e in r.get("tool_events", [])]
            if expected == "no_state_changing_tool":
                unexpected_tools += int("submit_information" in actual)
            elif expected:
                unexpected_tools += int(expected not in actual)
        latest_by_scenario = {}
        for r in selected:
            prior = latest_by_scenario.get(r.get("scenario_id"))
            if prior is None or r.get("turn", 0) > prior.get("turn", 0):
                latest_by_scenario[r.get("scenario_id")] = r
        workflow[label] = {
            "expected_transition_matches": sum(r.get("state_transition_correct") is True for r in selected),
            "paired_turns": len(selected),
            "critical_violation_candidates": sum(len(r.get("critical_violations") or []) for r in selected),
            "api_errors": sum(bool(r.get("api_error")) for r in selected),
            "mean_latency_ms": round(statistics.mean(latency), 2) if latency else None,
            "tool_calls": dict(Counter(e.get("tool", "unknown") for r in selected for e in r.get("tool_events", []))),
            "field_outcomes": dict(Counter(o.get("status", "unknown") for r in selected for e in r.get("tool_events", []) for o in e.get("outcomes", []))),
            "field_outcomes_by_field": dict(Counter(
                f"{o.get('field', 'unknown')}:{o.get('status', 'unknown')}"
                for r in selected for e in r.get("tool_events", []) for o in e.get("outcomes", [])
            )),
            "unexpected_tool_expectation_mismatches": unexpected_tools,
            "accepted_fields_at_scenario_end": sum(len((r.get("state_after") or {}).get("accepted_values", {})) for r in latest_by_scenario.values()),
            "staged_fields_at_scenario_end": sum(len((r.get("state_after") or {}).get("staged_values", {})) for r in latest_by_scenario.values()),
            "completed_scenarios": sum(bool((r.get("state_after") or {}).get("accepted_values", {}).get("demo_pan_receipt")) for r in latest_by_scenario.values()),
        }
    ra, rb = _ratings(rating_paths0, m0["run_id"], a), _ratings(rating_paths1, m1["run_id"], b)
    quality = {}
    for dim in DIMENSIONS:
        ka = {(s,t,rv) for s,t,rv,d in ra if d == dim}
        kb = {(s,t,rv) for s,t,rv,d in rb if d == dim}
        paired = sorted(ka & kb)
        av = [ra[(s,t,rv,dim)] for s,t,rv in paired]
        bv = [rb[(s,t,rv,dim)] for s,t,rv in paired]
        diffs = [y-x for x,y in zip(av,bv)]
        quality[dim] = {"v0_mean": round(statistics.mean(av),3) if av else None,
                        "v1_mean": round(statistics.mean(bv),3) if bv else None,
                        "paired_difference": round(statistics.mean(diffs),3) if diffs else None,
                        "paired_n": len(paired), "reviewers": sorted({k[2] for k in paired})}
    details = {
        "mode": m0["mode"], "v0_run_id": m0["run_id"], "v1_run_id": m1["run_id"],
        "v0_prompt_sha256": m0["prompt_sha256"], "v1_prompt_sha256": m1["prompt_sha256"],
        "controller_sha": m0["git_commit_sha"], "model_id": m0["model_id"],
        "settings": m0["generation_settings"], "rules_sha256": m0["rules_sha256"],
        "paired_turns": len(shared), "v0_scenarios": len(scenarios_a), "v1_scenarios": len(scenarios_b),
        "diagnostics": diag, "workflow": workflow, "quality": quality,
    }
    return render_report(details), details

def render_report(d):
    lines = ["# V0 vs V1 controlled comparison", "",
             "> Evidence below comes only from selected run artifacts; missing evidence is not inferred.", "",
             "## Experimental setup", "",
             f"- Mode: {d['mode']}; V0 run {d['v0_run_id']}; V1 run {d['v1_run_id']}",
             f"- V0 prompt SHA-256: {d['v0_prompt_sha256']} (expected pinned baseline {V0_HASH})",
             f"- V1 prompt SHA-256: {d['v1_prompt_sha256']}",
             f"- Shared controller commit: {d['controller_sha']}; model: {d['model_id']}",
             f"- Settings: {json.dumps(d['settings'], sort_keys=True)}; rules SHA-256: {d['rules_sha256']}",
             f"- Scenario coverage: V0 {d['v0_scenarios']}, V1 {d['v1_scenarios']}; paired turns {d['paired_turns']}.", "",
             "## Workflow and safety", "",
             "Expected-transition matches combine active field, accepted/staged state, state-change, and expected tool checks from the runner. Recorded critical violations are expectation-mismatch candidates, not semantic audits."]
    for v, w in d["workflow"].items():
        rate = (f"{w['expected_transition_matches']}/{w['paired_turns']} "
                f"({100*w['expected_transition_matches']/w['paired_turns']:.1f}%)") if w["paired_turns"] else "not available"
        latency = f"{w['mean_latency_ms']} ms" if w["mean_latency_ms"] is not None else "not recorded"
        error_label = "offline fixture errors (not provider requests)" if d["mode"] == "offline" else "API errors"
        lines.append(f"- {v}: expected-transition matches {rate}; mismatch candidates {w['critical_violation_candidates']}; unexpected tool-expectation mismatches {w['unexpected_tool_expectation_mismatches']}; {error_label} {w['api_errors']}; mean latency {latency}; accepted/staged fields at scenario end {w['accepted_fields_at_scenario_end']}/{w['staged_fields_at_scenario_end']}; scenarios with final receipt accepted {w['completed_scenarios']}; tool calls {w['tool_calls']}; field outcomes {w['field_outcomes_by_field']}.")
    lines += ["", "The records do not independently establish false approval/save claims, refusal quality, or semantic consent. Review the real response alongside tool outcomes and state. An expected tool mismatch alone is not a verified safety violation.", "",
              "## Human-rated conversational quality", ""]
    if d["mode"] != "live":
        lines += ["Not assessed: offline mock responses are not Nemotron evidence. No quality score or difference is reported.", ""]
    else:
        lines += ["Only same-turn, same-reviewer ratings with both V0 and V1 scores are included. Difference is V1 minus V0.", "",
                  "| Dimension | V0 | V1 | Paired difference | n | Reviewers |", "|---|---:|---:|---:|---:|---|"]
        for dim, q in d["quality"].items():
            f = lambda x: f"{x:.3f}" if x is not None else "Not rated"
            lines.append(f"| {dim.replace('_',' ')} | {f(q['v0_mean'])} | {f(q['v1_mean'])} | {f(q['paired_difference'])} | {q['paired_n']} | {', '.join(q['reviewers']) or 'None'} |")
        lines.append("")
    lines += ["## Qualitative review and attribution", "",
              "Review identical turns from the existing Phase 2 and Phase 3 checklists: Romanized Hinglish and Devanagari Hindi, invalid tenure, questions about previously accepted fields, out-of-order multi-field input, PAN/privacy, consent, refusals, approval/EMI, and restart requests. Use actual live responses. Deterministic outcome/refusal fallbacks may replace model wording as described in the manual checks. Earlier Streamlit conversations are uncontrolled observations, not benchmark scores.", "",
              "## Coverage, limitations, and conclusion", "",
              "Diagnostics: " + ("; ".join(d["diagnostics"]) if d["diagnostics"] else "No coverage discrepancy detected."),
              "Latency and response length are operational context, not quality scores. Run-to-run variation and limited reviewer coverage constrain conclusions."]
    if d["mode"] == "offline":
        lines.append("No live Nemotron API calls were made. **Conclusion: conversational quality remains unmeasured.** These offline mocks check workflow plumbing only; use comparable live runs and paired human ratings before judging whether V1 is better, equivalent, or worse.")
    else:
        lines.append("**Conclusion: no superiority claim is made by this report.** Interpret paired outcomes with sample size, missing ratings, deterministic fallbacks, and model variation in view.")
    return "\n".join(lines) + "\n"

def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--v0-dir", type=Path, required=True); p.add_argument("--v1-dir", type=Path, required=True)
    p.add_argument("--v0-run-id"); p.add_argument("--v1-run-id"); p.add_argument("--output", type=Path, required=True)
    args = p.parse_args(argv)
    try:
        m0,r0,ra = _select_run(args.v0_dir,args.v0_run_id); m1,r1,rb = _select_run(args.v1_dir,args.v1_run_id)
        report, details = build_comparison(m0,r0,m1,r1,ra,rb)
        output = args.output if args.output.is_absolute() else ROOT / args.output
        parent = ensure_directory(output.parent, create=True); output = parent / output.name
        safe_write_text(output, report, overwrite=True)
    except (OSError, UnsafePathError, ComparisonError, ValueError, json.JSONDecodeError, csv.Error) as exc:
        print(f"Could not compare evaluation runs: {exc}", file=sys.stderr); return 2
    print(f"Comparison written to {output}; mode={details['mode']}; paired turns={details['paired_turns']}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

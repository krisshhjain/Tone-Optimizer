# V0 evaluation files

- `scenarios.json` contains 30 fictional scenarios with expected active fields, state-change expectations, helper expectations, and critical conditions. `offline_entries` are mock extraction fixtures only; live runs ignore them.
- `rubric.md` defines six human-rated dimensions and separately tracked factual workflow violations.
- `human_ratings_template.csv` has one blank scoring row for every one of the 36 scenario turns. Run-specific sheets include `run_id`, `scenario_id`, and `turn`; their composite key associates ratings with exactly one recorded response. Copy the sheet for each reviewer and enter a distinct `reviewer_id`.
- `results/` is the default destination for opt-in run outputs; generated results are local artifacts and are ignored by Git.

The runner defaults to a deterministic mocked model client and always invokes the existing `core.manager.run_manager_turn` and actual business-rule helper. Live requests require `--live`. Offline responses are fixtures, not Nemotron observations and not quality scores.

The summarizer joins each rating row to JSONL output by `(run_id, scenario_id, turn)` and reports only nonblank 1–5 scores. Rows that do not match a recorded turn are excluded and counted as unmatched. Multiple reviewer IDs are reported separately as well as in the combined summary. File paths must not contain `..` or symlink/reparse-point components; explicit absolute output folders and rating files are supported when they are ordinary filesystem paths.

`v1_phase2_manual_checks.md` contains the V1 Phase 2 language, question-handling, state-awareness, privacy, refusal, and completion checklist. `v1_phase3_manual_checks.md` covers the follow-up language, invalid-tenure, prior-state, privacy, unsupported-approval, and explicit-consent cases. The inputs are evaluation cases, not production prompt examples. Offline runs verify mocked workflow transitions only; assess conversational quality from actual model responses using the rubric.

Phase 3 refines shared Python response safeguards, so both V0 and V1 runs must use the same updated controller revision. Do not compare responses collected with the old controller against responses collected with this controller as if only the prompt changed. Rejected/mixed outcome summaries and refusal responses can replace model wording. The unsupported-save check now distinguishes affirmative claims from questions, negations, and claims grounded in already accepted/staged state. Semantic consent interpretation remains the LLM's responsibility; the Python helper validates only the Boolean value.

## Controlled V0/V1 comparison

From the repository root, run the same fixed dataset once per version. Offline is the default and makes no provider requests:

```powershell
python scripts/run_v0_evaluation.py --prompt-version V0 --output-dir evaluation/results/phase4/V0
python scripts/run_v0_evaluation.py --prompt-version V1 --output-dir evaluation/results/phase4/V1
python scripts/summarize_v0_evaluation.py --results-dir evaluation/results/phase4/V0 --output evaluation/results/phase4/V0/summary.md
python scripts/summarize_v0_evaluation.py --results-dir evaluation/results/phase4/V1 --output evaluation/results/phase4/V1/summary.md
python scripts/compare_v0_v1_evaluation.py --v0-dir evaluation/results/phase4/V0 --v1-dir evaluation/results/phase4/V1 --output evaluation/v1_phase4_comparison.md
```

The comparison tool selects the only run in each directory automatically. When a directory contains multiple runs, choose exact run IDs with --v0-run-id and --v1-run-id. It rejects ambiguous duplicate turns, mixed prompt identities, and mismatched model/settings/rules/controller metadata; missing scenario turns and incomplete scenario summaries are reported. Workflow checks, deterministic mismatch candidates, and paired human scores are reported separately. Offline canned responses are never presented as conversational-quality evidence.

Prepare a blinded side-by-side review sheet only from live artifacts:

```powershell
python scripts/prepare_v0_v1_review_sheet.py --v0-dir evaluation/results/phase4-live/V0 --v1-dir evaluation/results/phase4-live/V1 --output evaluation/results/phase4-live/paired_review.csv
```

The CSV contains the exact customer message and recorded responses under A/B labels, blank columns for the existing six rubric dimensions, reviewer ID, critical violations, and notes. A separate answer-key CSV maps labels to versions; keep it from reviewers until independent scoring is complete. Create one copy per reviewer and preserve distinct reviewer IDs. The comparison consumes only same scenario/turn/reviewer scores that exist for both versions; blanks and missing scores stay missing. Reviewers should record factual violations separately from tone scores.

### Opt-in live paired runs

No live requests are made by the commands above. Only run the following after explicit authorization for provider calls. Configure the same NVIDIA endpoint, model identifier, and generation settings for both runs, and keep the repository at the same clean commit. The cap is per version and includes follow-up tool rounds; 300 requests allows several requests per each of the 36 turns but can still leave an explicitly incomplete run if the model uses more. Check the runner's printed request count, each run status, and comparison diagnostics before interpreting results.

```powershell
python scripts/run_v0_evaluation.py --live --prompt-version V0 --output-dir evaluation/results/phase4-live/V0 --max-live-requests 300
python scripts/run_v0_evaluation.py --live --prompt-version V1 --output-dir evaluation/results/phase4-live/V1 --max-live-requests 300
python scripts/summarize_v0_evaluation.py --results-dir evaluation/results/phase4-live/V0 --output evaluation/results/phase4-live/V0/summary.md
python scripts/summarize_v0_evaluation.py --results-dir evaluation/results/phase4-live/V1 --output evaluation/results/phase4-live/V1/summary.md
python scripts/compare_v0_v1_evaluation.py --v0-dir evaluation/results/phase4-live/V0 --v1-dir evaluation/results/phase4-live/V1 --output evaluation/v1_phase4_comparison.md
python scripts/prepare_v0_v1_review_sheet.py --v0-dir evaluation/results/phase4-live/V0 --v1-dir evaluation/results/phase4-live/V1 --output evaluation/results/phase4-live/paired_review.csv
```

Do not treat the earlier shared Streamlit conversations as paired benchmark data. Use the Phase 2/3 manual checklists for focused qualitative review, and attribute deterministic helper-outcome/refusal fallbacks separately where event traces permit it. Do not change either prompt based on Phase 4 findings.

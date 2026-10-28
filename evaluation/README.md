# V0 evaluation files

- `scenarios.json` contains 30 fictional scenarios with expected active fields, state-change expectations, helper expectations, and critical conditions. `offline_entries` are mock extraction fixtures only; live runs ignore them.
- `rubric.md` defines six human-rated dimensions and separately tracked factual workflow violations.
- `human_ratings_template.csv` has one blank scoring row for every one of the 36 scenario turns. Run-specific sheets include `run_id`, `scenario_id`, and `turn`; their composite key associates ratings with exactly one recorded response. Copy the sheet for each reviewer and enter a distinct `reviewer_id`.
- `results/` is the default destination for opt-in run outputs; generated results are local artifacts and are ignored by Git.

The runner defaults to a deterministic mocked model client and always invokes the existing `core.manager.run_manager_turn` and actual business-rule helper. Live requests require `--live`. Offline responses are fixtures, not Nemotron observations and not quality scores.

The summarizer joins each rating row to JSONL output by `(run_id, scenario_id, turn)` and reports only nonblank 1–5 scores. Rows that do not match a recorded turn are excluded and counted as unmatched. Multiple reviewer IDs are reported separately as well as in the combined summary. File paths must not contain `..` or symlink/reparse-point components; explicit absolute output folders and rating files are supported when they are ordinary filesystem paths.

`v1_phase2_manual_checks.md` contains the V1 Phase 2 language, question-handling, state-awareness, privacy, refusal, and completion checklist. `v1_phase3_manual_checks.md` covers the follow-up language, invalid-tenure, prior-state, privacy, unsupported-approval, and explicit-consent cases. The inputs are evaluation cases, not production prompt examples. Offline runs verify mocked workflow transitions only; assess conversational quality from actual model responses using the rubric.

Phase 3 refines shared Python response safeguards, so both V0 and V1 runs must use the same updated controller revision. Do not compare responses collected with the old controller against responses collected with this controller as if only the prompt changed. Rejected/mixed outcome summaries and refusal responses can replace model wording. The unsupported-save check now distinguishes affirmative claims from questions, negations, and claims grounded in already accepted/staged state. Semantic consent interpretation remains the LLM's responsibility; the Python helper validates only the Boolean value.

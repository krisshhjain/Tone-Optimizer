# V0 evaluation files

- `scenarios.json` contains 30 fictional scenarios with expected active fields, state-change expectations, helper expectations, and critical conditions. `offline_entries` are mock extraction fixtures only; live runs ignore them.
- `rubric.md` defines six human-rated dimensions and separately tracked factual workflow violations.
- `human_ratings_template.csv` has one blank scoring row for every one of the 36 scenario turns. Run-specific sheets include `run_id`, `scenario_id`, and `turn`; their composite key associates ratings with exactly one recorded response. Copy the sheet for each reviewer and enter a distinct `reviewer_id`.
- `results/` is the default destination for opt-in run outputs; generated results are local artifacts and are ignored by Git.

The runner defaults to a deterministic mocked model client and always invokes the existing `core.manager.run_manager_turn` and actual business-rule helper. Live requests require `--live`. Offline responses are fixtures, not Nemotron observations and not quality scores.

The summarizer joins each rating row to JSONL output by `(run_id, scenario_id, turn)` and reports only nonblank 1–5 scores. Rows that do not match a recorded turn are excluded and counted as unmatched. Multiple reviewer IDs are reported separately as well as in the combined summary. File paths must not contain `..` or symlink/reparse-point components; explicit absolute output folders and rating files are supported when they are ordinary filesystem paths.

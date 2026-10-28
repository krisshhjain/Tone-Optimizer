# V0 evaluation files

- `scenarios.json` contains 30 fictional scenarios with expected active fields, state-change expectations, helper expectations, and critical conditions. `offline_entries` are mock extraction fixtures only; live runs ignore them.
- `rubric.md` defines six human-rated dimensions and separately tracked factual workflow violations.
- `human_ratings_template.csv` is blank. Create a separate copy per reviewer or run and leave unknown scores empty.
- `results/` is the default destination for opt-in run outputs; generated results are local artifacts and are ignored by Git.

The runner defaults to a deterministic mocked model client and always invokes the existing `core.manager.run_manager_turn` and actual business-rule helper. Live requests require `--live`. Offline responses are fixtures, not Nemotron observations and not quality scores.

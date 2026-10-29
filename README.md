# Tone-Optimizer — V0/V1 prompt foundation

A local Streamlit proof of concept for a fictional Personal Loan conversation. One Nemotron Manager selects an allowlisted V0 or V1 prompt and calls a deterministic Python helper for six ordered fictional rules. It is an evaluation project, not a loan application.

## Safety and data scope

Use synthetic values only. Never enter real customer information, real PAN or Aadhaar values, identity documents, uploads, or banking information. The final requirement is only a Boolean flag for a fictional receipt; no document is collected.

Synthetic entries can be retained temporarily in local Streamlit session state. No real loan application is created, no bank or real KYC system is contacted, and no permanent database is used. No claim is made here about the model provider's retention or logging practices. The configured requirements are fictional test rules, not actual banking policies or eligibility decisions. Completing the journey does not mean approval.

## Architecture

- `app.py` — Streamlit chat, progress, and session controls.
- `core/manager.py` — allowlisted V0/V1 prompt selection, shared structured helper calls, refusal and unsupported-save safeguards.
- `core/model_client.py` — OpenAI-compatible NVIDIA client using environment configuration.
- `core/business_rule_helper.py` — deterministic read-context and submit-information tools, including per-field and event-level outcomes.
- `core/rules.py`, `config/pl_rules.json` — six ordered fictional rules and validation.
- `core/state.py` — temporary accepted/staged state and presets. Only helper-validated values advance progress.
- `prompts/v0_orchestration.md` — the pinned V0 baseline prompt.
- `prompts/v1_conversational.md` — V1's instruction-only conversational prompt; it uses no few-shot dialogue examples.
- `evaluation/` — fixed synthetic scenarios, human rubric, blank rating sheet, and run instructions.
- `scripts/run_v0_evaluation.py` — offline mock or explicitly opted-in live scenario runner that calls the existing Manager runtime.
- `scripts/summarize_v0_evaluation.py` — Markdown summary from recorded runs and optional human ratings.

The Manager cannot write session values directly. Valid future values may be staged after consent, but only become complete after deterministic prerequisites pass. Tool events show `success`, `partial`, `rejected`, or `read`, with field-level outcomes.

## Setup

Requires Python 3.11 or newer.

```bash
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pytest -q
python -m compileall -q app.py core tests scripts
```

Copy `.env.example` to `.env` and set the exact NVIDIA endpoint, model identifier, and key from your local provider configuration. `.env` is ignored by Git. Never commit or share it. The app can start without credentials, but chat is disabled until configuration is available.

```dotenv
NVIDIA_API_KEY=your-local-secret
NVIDIA_BASE_URL=https://your-openai-compatible-endpoint/v1
NVIDIA_MODEL=your-exact-model-identifier
```

Optional generation settings are `NVIDIA_TEMPERATURE`, `NVIDIA_TOP_P`, `NVIDIA_MAX_TOKENS`, and `NVIDIA_TIMEOUT_SECONDS`. The same configured model and generation values are used across scenarios in each run.

Start the local app:

```bash
python -m streamlit run app.py
```

### Manager prompt versions

V0 is the pinned baseline orchestration prompt. V1 uses a separate, instruction-only prompt for language adaptation, answer-first responses, context-aware tool use, and accurate customer-facing outcome explanations. Select **V0 — Baseline** or **V1 — Conversational** in the Streamlit sidebar to choose which file the same Manager implementation sends to Nemotron. Switching versions resets the current conversation and synthetic journey to the selected preset so messages and accepted values from one prompt version cannot contaminate the other. Resetting within a version keeps that version selected.

V1 Phase 2 changed prompt instructions only. Phase 3 also refines the shared Python response safeguards for customer-friendly rejection summaries and unsupported save claims. Both prompt versions continue to use the same Nemotron configuration and generation settings, the same two helper tools, the same six rules, and the same validation and state-transition logic. Because the controller changed, rerun both V0 and V1 on the same controller revision; do not compare old-controller V0 results with new-controller V1 results as a prompt-only experiment. Prompt and controller changes are hypotheses, not evidence that V1 improves conversation quality; use actual responses and the rubric before drawing conclusions.

## Evaluation

For the controlled V0/V1 Phase 4 comparison, paired review workflow, and separately documented opt-in live commands, see [evaluation/README.md](evaluation/README.md). The Phase 4 comparison uses offline runs to verify workflow artifacts only; live conversation quality requires comparable provider runs and paired human review.

The V1 professional tone-polish prompt hash, isolated offline rerun instructions, and focused manual checks are documented in [evaluation/README.md](evaluation/README.md) and [evaluation/v1_tone_polish_manual_checks.md](evaluation/v1_tone_polish_manual_checks.md). Results from the prior V1 prompt hash must remain separate from the refined prompt.

There are 30 synthetic cases: 5 normal progression, 5 clarification, 4 repetition/context, 5 language adaptation, 4 invalid values, 3 out-of-order, 2 refusals/interruption, and 2 completion/failure. Each records expected active rule, state changes, tool behavior, critical conditions, starting preset, and whether conversational evaluation requires the real API. No real identity or bank information is present.

### Offline mocked run

Offline is the default and makes no provider requests. It runs the real `run_manager_turn` and deterministic helper; fixed fixture tool calls mock only what the Manager model might extract from user text. The canned offline text is explicitly labeled as a mock and must not be treated as a Nemotron observation or quality rating.

```bash
python scripts/run_v0_evaluation.py --scenario-id V0-IV-03
python scripts/run_v0_evaluation.py --category clarification_questions
python scripts/run_v0_evaluation.py --all
```

Select a prompt version explicitly; omission defaults to V0. Each invocation evaluates one version only, and metadata plus rating rows identify the selected version and prompt hash:

```bash
python scripts/run_v0_evaluation.py --prompt-version V0 --scenario-id V0-CL-04 --output-dir evaluation/results/V0
python scripts/run_v0_evaluation.py --prompt-version V1 --scenario-id V0-CL-04 --output-dir evaluation/results/V1
```

The runner checks the pinned V0 prompt hash on every run, including V1 runs, and records the actual selected prompt hash. Runs are kept separately labeled; the summarizer refuses to combine results that have different prompt versions or hashes. Use separate results directories when preparing reports for V0 and V1.

Choose another output directory with `--output-dir path/to/output`. Each run writes turn-level JSONL, run metadata/final state JSON, and a blank human-rating CSV. Generated output under `evaluation/results/` is ignored by Git.

### Live Nemotron run

Live runs require `.env` and deliberate opt-in. They can consume provider quota. Begin with one scenario and a request cap:

```bash
python scripts/run_v0_evaluation.py --live --scenario-id V0-CL-04 --max-live-requests 4
```

Run all scenarios only when ready:

```bash
python scripts/run_v0_evaluation.py --live --all --max-live-requests 100
```

The request cap applies across the selected run, including follow-up tool rounds. A reached cap may leave a scenario with an explicit API error; helper-confirmed commits remain in its recorded final state. Do not describe a scenario as live-tested unless the output says it was run in `live` mode.

The JSONL/JSON outputs record UTC timestamp, run/scenario IDs, selected prompt version and SHA-256, rule SHA-256, model ID, generation settings, git SHA when available, initial preset, expected/observed transitions, assistant text, sanitized tool outcomes, latency, errors, and final accepted/staged values. Keys, authorization headers, and hidden reasoning are not exported. Transcripts are synthetic and may be written as evaluation artifacts.

### Human ratings and report

Read `evaluation/rubric.md` before scoring. The blank template and each run-specific rating sheet have one row per customer turn, keyed by `run_id`, `scenario_id`, and `turn`. Enter integer scores 1–5 in the six dimension columns; leave unrateable or missing scores blank, never zero. Record reviewer ID, critical workflow violations separately, and brief evidence in reviewer notes. For a second rater, make a separate copy and use a different reviewer ID. The summarizer joins ratings to the exact turn and response, reports reviewer-specific and combined averages, and counts unmatched rows without scoring them.

Generate a summary from recorded runs and any completed rating sheets:

```bash
python scripts/summarize_v0_evaluation.py
python scripts/summarize_v0_evaluation.py --results-dir path/to/output --ratings path/to/ratings.csv --output path/to/summary.md
```

The report shows run success/failure, expected state/tool transition rates, candidate critical violations, mean/median recorded latency, human rating averages by dimension/category/language, and real response excerpts from saved outputs. Empty score columns display as **Not rated**. It does not ask a model to evaluate quality or create human scores. Critical-transition candidates are deterministic mismatch checks and are not a complete semantic audit of prose.

Paths supplied with `--output-dir`, `--results-dir`, `--ratings`, or `--output` are validated. Parent-directory traversal and symlink/reparse-point components are rejected; explicitly selected absolute locations outside the repository are allowed when they are ordinary directories/files.

## Manual live checks

Run these in the Streamlit app and record actual Nemotron replies, tool events, and resulting state. These are instructions, not claimed results:

1. **Invalid tenure:** select Tenure pending; say “I want 7 months.” Expect BR-03 active with no tenure accepted.
2. **Out of order:** start fresh; say “I consent, amount 150000, tenure 24 months, and I'm salaried.” Expect order-preserving acceptance/staging and no skipped rule.
3. **Clarification:** select Monthly income pending; ask “Monthly income kyun chahiye?” Expect a rule-grounded answer and no state change.
4. **Refusal:** with monthly income active, say “I don't want to give my monthly income.” Expect no fabricated value or repeated pressure; the step stays active.
5. **Full journey:** provide all six fictional fields in order. Expect helper-confirmed completion only; no approval claim.
6. **Mixed values:** at an eligible state, submit one valid and one invalid field together. Expect accepted/rejected outcomes per field and a `partial` event where at least one operation succeeded.

Use [`evaluation/v1_phase2_manual_checks.md`](evaluation/v1_phase2_manual_checks.md) for the V1 Phase 2 language, context, privacy, refusal, and completion checks, and [`evaluation/v1_phase3_manual_checks.md`](evaluation/v1_phase3_manual_checks.md) for the follow-up language, tenure rejection, prior-state, privacy, approval, and consent checks. These notes separate expected helper/state behavior from conversational behavior. Use only fictional values and record actual live responses; offline fixtures are not model-quality evidence. The shared Manager may replace V0 or V1 wording after helper failures, refusals, or unsupported affirmative save claims.

## Reproducibility and later comparisons

The pinned V0 prompt SHA-256 is `69e6071c19c1ed66f48893bc79b33ad9078cb9244edb8d7562b435be27f42c99` (`prompts/v0_baseline.sha256`). The runner stops if the prompt file no longer matches this baseline. Every run records the prompt and rule hashes. Preserve scenario data, tool definitions, state-transition logic, initial presets, model, generation settings, and rubric when comparing versions. Later V1 and V2 experiments may be compared against these V0 outputs only after they are separately approved and implemented. A changed prompt or implementation is a distinct experiment; do not pool runs with different hashes as one baseline.

V0 Phase 4 stabilized the baseline workflow and prepared reproducible evaluation. V1 Phase 2 changes only Manager instructions; it does not change the shared controller, add few-shot examples, compare prompt results automatically, add an LLM judge or dashboard, or introduce new services.

## Known limitations

- Live Nemotron responses and structured-call behavior depend on the configured endpoint and model; offline results are workflow mocks, not model performance evidence.
- The refusal and unsupported-save safeguards are lightweight pattern checks, not semantic classifiers. They cover tested forms, not every possible paraphrase; helper state remains authoritative.
- Shared Python response handling may replace model wording with a deterministic rule-grounded explanation after rejected or partial helper outcomes, or a fixed response on refusals. An ungrounded affirmative save claim without helper confirmation is blocked; questions, clear negations, and field-specific claims grounded in accepted/staged session state are preserved. These effects apply equally to V0 and V1 and can limit prompt-only improvements in naturalness.
- The Python helper validates only the consent Boolean. Whether natural-language wording expresses explicit and unambiguous consent remains the Manager model's responsibility and is not guaranteed by deterministic code.
- Automatically detected critical violations are expected-transition mismatch candidates. Semantic policy claims still need human review.
- No live runs or human quality scores are claimed by this repository change unless actual run artifacts are produced and reviewed.
- Session state is temporary application memory, not durable storage. Provider-side handling has not been independently verified.

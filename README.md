# Tone Optimizer — V0 Foundation

A local Streamlit proof of concept for a fictional Personal Loan journey. One Nemotron Manager may request two deterministic Python helper tools. All requirements and values are fictional; this app does not connect to real banking systems.

## Safety and scope

Use fictional demo values only. Never enter real customer information, PAN or Aadhaar numbers, identity documents, uploads, or banking information. The final rule is only a Boolean synthetic receipt flag; no document or identity data is collected.

Configured values and constraints are test assumptions, not banking policy, eligibility, affordability, verification, or approval decisions. Completion means only that the fictional demo journey is complete. The app uses temporary Streamlit `st.session_state`; there is no database or durable storage.

## Architecture

- `app.py`: Streamlit interface, conversation and state controller.
- `core/model_client.py`: OpenAI SDK client configured by `NVIDIA_API_KEY`, `NVIDIA_BASE_URL`, and `NVIDIA_MODEL`.
- `core/manager.py`: assembles the V0 prompt and authoritative journey context, runs a bounded structured-tool loop, and only commits helper-returned state.
- `core/business_rule_helper.py`: deterministic Python implementation of the two tool operations.
- `core/rules.py` and `config/pl_rules.json`: load and validate the six ordered fictional rules.
- `core/state.py`: accepted-prefix and staged-value state validation, progression, presets, and reset.

The Manager may propose values, but it cannot directly write state. `accepted_values` contains only validated values that have passed every earlier rule. `pending_values` contains valid future values staged after consent; staged fields remain incomplete until prerequisites are met. When an earlier requirement is accepted, contiguous staged values are validated and promoted in order. Invalid values do not advance state, and accepted or staged values cannot be overwritten silently.

### Helper tools

- `get_journey_context({})` returns the configured rules, completed/active/pending requirements, accepted values, and staged values.
- `submit_information({"entries":[{"field":"loan_amount","value":150000}]})` validates one or more proposed values and returns per-field outcomes (`accepted`, `staged`, `invalid`, `already_completed`, `missing_prerequisite`, or `unknown_field`), committed fields, and the resulting active requirement.

The controller returns each assistant tool-call message and its corresponding `tool_call_id` result to Nemotron before requesting a customer-facing response. The UI trace shows tool name, fields, outcome, and resulting active rule without logging request payloads or credentials. A bounded tool-call loop stops repeated calls safely. Model prose alone never marks a field complete.

## Setup

Requires Python 3.11 or newer.

```bash
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pytest -q
python -m compileall -q app.py core tests
```

Copy `.env.example` to `.env`; set the endpoint, exact model identifier, and API key provided for your NVIDIA account. Never commit or share `.env`; Git ignores it. Do not paste keys into chat or documentation.

```dotenv
NVIDIA_API_KEY=your-local-secret
NVIDIA_BASE_URL=https://your-openai-compatible-endpoint/v1
NVIDIA_MODEL=your-exact-model-identifier
```

Generation settings can also be configured with `NVIDIA_TEMPERATURE`, `NVIDIA_TOP_P`, `NVIDIA_MAX_TOKENS`, and `NVIDIA_TIMEOUT_SECONDS`.

Start the app with:

```bash
python -m streamlit run app.py
```

The rules and presets remain inspectable without credentials; chat is disabled until configuration is complete. Automated tests use mocked clients and never require a real key.

## Structured tool compatibility

The compatibility check is deliberately separate from pytest and sends one small live request only when explicitly run:

```bash
python scripts/check_live_tool_call.py --live
```

It reports only whether a valid structured function call was returned. A text-only response, unsupported schema, or provider error means tool-call compatibility is unconfirmed; it must not be treated as a successful state update. No live compatibility result is claimed until this command is run against the configured endpoint/model.

The compatibility command was attempted in the current workspace but could not send a request because the OpenAI SDK is unavailable and package installation is blocked by the configured package-index network. Structured tool calling for the configured endpoint/model therefore remains unverified here.

## Manual fictional scenarios

1. **Normal journey:** say hello, provide explicit consent, then a valid amount, tenure, employment category, positive monthly income, and synthetic receipt confirmation. Confirm all six requirements become complete; no loan approval is implied.
2. **Clarification:** start with **Monthly income pending**, ask why income is requested. The answer should use configured information; BR-05 remains active and values do not change.
3. **Invalid value:** start with **Tenure pending**, submit 7 months. The helper rejects it and the active rule remains BR-03.
4. **Out of order:** from **Fresh application**, provide consent, amount, tenure, and employment in one message. The helper processes entries in rule order.
5. **Hinglish question:** ask about tenure without supplying a value. No state mutation should occur just because a question was asked.
6. **Tool failure:** simulate an unavailable/failed helper response. The app must not show a success confirmation or corrupt state.

## Limitations and roadmap

The app is a local fictional POC. API availability, structured tool support, quotas, and model behavior depend on the configured provider endpoint and model. Use the compatibility check before relying on tool calling. If the endpoint does not support structured calls, the app must report that limitation and preserve state; a possible minimal fallback is an explicitly user-confirmed deterministic form submission, not inferred saves from model text.

Phase 1 established rules and state. Phase 2 added the read-only Nemotron Manager. Phase 3 adds helper-backed progression. Phase 4 evaluation materials, V1 conversational prompting, and V2 few-shot prompting remain out of scope.

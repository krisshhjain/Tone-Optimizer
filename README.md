# Tone Optimizer — V0 Foundation

A local Streamlit proof of concept for a fictional Personal Loan conversation. Phase 2 connects one read-only Manager LLM to an OpenAI-compatible NVIDIA Nemotron endpoint. The app does not originate loans or connect to real banking systems.

## Safety and scope

Use fictional demo values only. Never enter real customer information, PAN or Aadhaar numbers, identity documents, uploads, or banking information. The PAN item is a Boolean flag for a fictional receipt only; no document or identity data is collected.

All configured values and constraints are test assumptions, not banking policy, eligibility, affordability, verification, or approval decisions. Model conversation is read-only: replies cannot validate, save, or advance application values. Session values live temporarily in Streamlit's `st.session_state`; they are not browser `sessionStorage` or durable storage.

## Setup

Requires Python 3.11 or newer.

```bash
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pytest -q
```

Copy `.env.example` to `.env` and configure the endpoint, exact model identifier, and key supplied for your NVIDIA account:

```dotenv
NVIDIA_API_KEY=your-local-secret
NVIDIA_BASE_URL=https://your-openai-compatible-endpoint/v1
NVIDIA_MODEL=your-exact-model-identifier
```

The values above are examples/placeholders. Use the endpoint and model ID supplied by your provider configuration. Never commit or share `.env`; it is ignored by Git. Generation settings may be set in `.env` using `NVIDIA_TEMPERATURE`, `NVIDIA_TOP_P`, `NVIDIA_MAX_TOKENS`, and `NVIDIA_TIMEOUT_SECONDS`. Defaults preserve the non-secret sampling settings from the supplied NVIDIA sample; the UI displays active generation settings for reproducibility.

Start the app with:

```bash
streamlit run app.py
```

The app can still open without model credentials; rules and scenario state remain viewable, while chat submission is disabled with a configuration notice. Do not use a real API key in tests. Offline tests inject a fake API client and make no external calls.

## What Phase 2 includes

- One Manager LLM using the OpenAI Python SDK with configurable NVIDIA endpoint settings.
- Baseline V0 orchestration prompt, all six configured rules, selected scenario, accepted values, active rule, and prior conversation turns sent as context on each request.
- Multi-turn Streamlit chat, loading state, and safe handling for timeout, rate limit, endpoint, empty, and malformed response failures.
- Read-only behavior. A customer may discuss a value, but the model cannot claim it was recorded or change the accepted values.

## Not included yet

Phase 3 will add deterministic business-rule helper integration and confirmed value saves. This phase does not include model tool calling, state updates from model output, V1/V2 prompt variants, extra agents, a database, authentication, a separate backend, or an evaluation dashboard. No claim of a live Nemotron API call is made unless one is separately performed with configured credentials.

## Synthetic presets

- **Fresh application:** no values accepted; BR-01 is active.
- **Tenure pending:** consent and loan amount accepted; BR-03 is active.
- **Monthly income pending:** through employment accepted; BR-05 is active.
- **Document receipt pending:** through monthly income accepted; BR-06 is active.

## Roadmap

1. Phase 1: rules, temporary state, basic UI, and offline tests.
2. Phase 2 (this branch): Nemotron chat with read-only context and offline mocked tests.
3. Phase 3: deterministic helper integration and confirmed state updates.
4. Phase 4: fixed synthetic evaluation scenarios and human-scored comparison materials.

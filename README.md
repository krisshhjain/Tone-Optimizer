# Tone Optimizer — V0 Foundation

A small local Streamlit proof of concept for deterministic progression through six fictional Personal Loan demo rules. It does not originate loans or connect to a model.

## Safety and scope

All values and constraints are synthetic test assumptions, not banking policy, eligibility criteria, affordability checks, or approval decisions. Never enter real customer information, PAN or Aadhaar numbers, identity documents, uploads, or banking information. The PAN item is only a Boolean flag for a fictional demo receipt; no document or identity data is collected.

Accepted values are the source of truth. Rule status is derived from validated values and configured order. Session values live in Streamlit's `st.session_state` and are temporary; they are not browser `sessionStorage` or durable storage. Resetting the session restores the selected preset and clears messages.

## Setup

Requires Python 3.11 or newer.

```bash
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pytest -q
streamlit run app.py
```

The app runs without an API key and prominently reports **Model not connected — planned for Phase 2**. No fake model replies are provided. `.env.example` contains empty placeholders only; Phase 1 does not read them.

## Synthetic presets

- **Fresh application:** no values accepted; BR-01 is active.
- **Tenure pending:** consent and loan amount accepted; BR-03 is active.
- **Monthly income pending:** through employment accepted; BR-05 is active.
- **Document receipt pending:** through monthly income accepted; BR-06 is active.

## Roadmap

1. **Phase 1 (this foundation):** offline rules, temporary state, basic UI, and tests.
2. **Phase 2:** connect one Manager LLM to the Nemotron API using environment configuration and explicit error handling.
3. **Phase 3:** integrate the deterministic Python Business Rule Helper with confirmed save results.
4. **Phase 4:** prepare fixed synthetic evaluation scenarios and human-scored comparison materials.

No phase beyond Phase 1 is implemented here. There is no database, authentication, separate backend, agent framework, real tool calling, model comparison, or evaluation dashboard.

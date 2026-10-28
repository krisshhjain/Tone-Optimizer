"""Local Streamlit UI for the fictional Personal Loan demo."""

import streamlit as st

from core.manager import run_manager_turn
from core.model_client import ModelConfig, ModelError
from core.rules import load_rules
from core.state import PRESETS, active_rule, initialize_scenario, rule_statuses, validate_journey_state

st.set_page_config(page_title="Tone Optimizer — V0 Foundation", page_icon="🧪")
st.title("Tone Optimizer — V0 Foundation")
st.warning(
    "Fictional demo data only. Never enter real customer information, identity details,"
    " PAN or Aadhaar numbers, document images, or banking information."
)
rules = load_rules()

if "journey" not in st.session_state:
    st.session_state.journey = initialize_scenario()
else:
    try:
        st.session_state.journey = validate_journey_state(st.session_state.journey, rules)
    except ValueError:
        st.error("The current session state is invalid. Reset the session to continue safely.")
        if st.button("Reset invalid session"):
            st.session_state.journey = initialize_scenario()
            st.rerun()
        st.stop()

with st.sidebar:
    st.subheader("Scenario")
    scenario_names = list(PRESETS)
    selected_scenario = st.selectbox(
        "Synthetic preset",
        scenario_names,
        index=scenario_names.index(st.session_state.journey["scenario"]),
    )
    if selected_scenario != st.session_state.journey["scenario"]:
        st.session_state.journey = initialize_scenario(selected_scenario, rules)
        st.session_state.pop("turn_error", None)
        st.rerun()
    if st.button("Reset session", use_container_width=True):
        st.session_state.journey = initialize_scenario(selected_scenario, rules)
        st.session_state.pop("turn_error", None)
        st.rerun()

journey = st.session_state.journey
st.caption(f"Selected scenario: **{journey['scenario']}** · Session state is temporary.")
current_rule = active_rule(journey["accepted_values"], rules)
st.subheader("Current required field")
if current_rule:
    st.write(f"**{current_rule['id']} · {current_rule['label']}** — `{current_rule['field']}`")
else:
    st.success("The fictional demo journey is complete. This is not loan approval.")

with st.expander("Journey progress", expanded=True):
    for item in rule_statuses(journey["accepted_values"], rules):
        marker = {"completed": "✅", "active": "➡️", "pending": "◻️"}[item["status"]]
        st.write(f"{marker} **{item['id']} · {item['label']}** — {item['status']}")

with st.expander("Configured fictional rules"):
    for item in rules:
        st.markdown(f"**{item['id']} · {item['label']}** (`{item['field']}`)  \n{item['question']}")

try:
    model_config = ModelConfig.from_env()
except ModelError as exc:
    model_config = None
    st.info(str(exc))

st.subheader("Conversation")
st.caption("The deterministic helper validates fictional values. Only confirmed helper results update progress.")
for message in journey["messages"]:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

pending_error = st.session_state.pop("turn_error", None)
if pending_error:
    st.error(pending_error)

with st.expander("Accepted and staged values"):
    st.write("Accepted values")
    st.json(journey["accepted_values"] or {})
    st.write("Staged future values (not yet completed)")
    st.json(journey["pending_values"] or {})

with st.expander("Tool events"):
    if not journey["tool_events"]:
        st.caption("No helper tools have run in this session.")
    for event in reversed(journey["tool_events"][-10:]):
        st.write(
            f"**{event['tool']}** · fields: {', '.join(event['fields']) or 'none'} · "
            f"{'success' if event['success'] else 'rejected'} · active: {event['active_rule'] or 'complete'}"
        )
        if event["outcomes"]:
            st.caption(", ".join(
                f"{item['field']}: {item['status']}" for item in event["outcomes"]
            ))

if model_config is not None:
    with st.expander("Generation settings"):
        st.json(model_config.settings.as_metadata())

submitted = st.chat_input("Message about this fictional demo", disabled=model_config is None)
if submitted and model_config is not None:
    with st.spinner("Waiting for Nemotron and the deterministic helper..."):
        result = run_manager_turn(journey, submitted, model_config)
    st.session_state.journey = result["state"]
    if result["error"]:
        st.session_state.turn_error = result["error"]
    st.rerun()

"""Local Streamlit UI for the fictional Personal Loan demo."""

import streamlit as st

from core.manager import build_manager_messages
from core.model_client import ModelConfig, ModelError, generate_reply
from core.rules import load_rules
from core.state import PRESETS, active_rule, initialize_scenario, rule_statuses

st.set_page_config(page_title="Tone Optimizer — V0 Foundation", page_icon="🧪")
st.title("Tone Optimizer — V0 Foundation")
st.warning(
    "Fictional demo data only. Never enter real customer information, identity details,"
    " PAN or Aadhaar numbers, document images, or banking information."
)
rules = load_rules()

if "journey" not in st.session_state:
    st.session_state.journey = initialize_scenario()

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
        st.rerun()
    if st.button("Reset session", use_container_width=True):
        st.session_state.journey = initialize_scenario(selected_scenario, rules)
        st.rerun()

journey = st.session_state.journey
st.caption(f"Selected scenario: **{journey['scenario']}** · Session state is temporary.")
current_rule = active_rule(journey["accepted_values"], rules)
st.subheader("Current required field")
if current_rule:
    st.write(f"**{current_rule['id']} · {current_rule['label']}** — `{current_rule['field']}`")
else:
    st.success("All six fictional demo requirements are complete.")

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
st.caption("Phase 2 chat is read-only. Model replies cannot save values or change journey progress.")
for message in journey["messages"]:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if model_config is not None:
    with st.expander("Generation settings"):
        st.json(model_config.settings.as_metadata())

submitted = st.chat_input("Message about this fictional demo", disabled=model_config is None)
if submitted and model_config is not None:
    prior_history = list(journey["messages"])
    journey["messages"].append({"role": "user", "content": submitted})
    try:
        request_messages = build_manager_messages(
            state=journey,
            user_message=submitted,
            history=prior_history,
        )
        with st.spinner("Waiting for Nemotron..."):
            response_text = generate_reply(request_messages, model_config)
    except ModelError as exc:
        with st.chat_message("user"):
            st.markdown(submitted)
        st.error(str(exc))
    else:
        journey["messages"].append({"role": "assistant", "content": response_text})
        st.rerun()

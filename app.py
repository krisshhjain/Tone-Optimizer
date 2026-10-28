"""Local Streamlit shell for the Phase 1 fictional journey foundation."""

import streamlit as st

from core.rules import load_rules
from core.state import PRESETS, active_rule, initialize_scenario, rule_statuses

st.set_page_config(page_title="Tone Optimizer — V0 Foundation", page_icon="🧪")
st.title("Tone Optimizer — V0 Foundation")
st.warning("Fictional demo data only. No real customer, identity, document, or banking information is collected or processed.")
st.error("**Model not connected — planned for Phase 2.**")

rules = load_rules()
if "journey" not in st.session_state:
    st.session_state.journey = initialize_scenario()

with st.sidebar:
    st.subheader("Scenario")
    chosen = st.selectbox("Synthetic preset", list(PRESETS), index=list(PRESETS).index(st.session_state.journey["scenario"]))
    if chosen != st.session_state.journey["scenario"]:
        st.session_state.journey = initialize_scenario(chosen, rules)
    if st.button("Reset session", use_container_width=True):
        st.session_state.journey = initialize_scenario(chosen, rules)
        st.rerun()

journey = st.session_state.journey
st.caption(f"Selected scenario: **{journey['scenario']}** · Values live only in this Streamlit session.")
current = active_rule(journey["accepted_values"], rules)
if current:
    st.subheader("Current required field")
    st.write(f"**{current['id']} · {current['label']}** — `{current['field']}`")
else:
    st.success("All six fictional demo requirements are complete.")

st.subheader("Journey progress")
for item in rule_statuses(journey["accepted_values"], rules):
    marker = {"completed": "✅", "active": "➡️", "pending": "◻️"}[item["status"]]
    st.write(f"{marker} **{item['id']} · {item['label']}** — {item['status']}")

with st.expander("Configured fictional rules"):
    for item in rules:
        st.markdown(f"**{item['id']} · {item['label']}** (`{item['field']}`)  \n{item['question']}")

st.subheader("Chat placeholder")
st.info("Chat is unavailable until the model is connected in Phase 2. No scripted or generated replies are shown here.")
st.text_input("Message", disabled=True, placeholder="Model not connected")

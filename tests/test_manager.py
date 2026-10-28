from copy import deepcopy

from core.manager import build_manager_messages
from core.state import initialize_scenario


def test_manager_injects_all_rules_state_active_rule_and_history():
    state = initialize_scenario("Tenure pending")
    messages = build_manager_messages(
        state,
        "Can I ask a question first?",
        history=[
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
        ],
    )
    assert messages[0]["role"] == "system"
    context = messages[0]["content"]
    for rule_id in ("BR-01", "BR-02", "BR-03", "BR-04", "BR-05", "BR-06"):
        assert rule_id in context
    assert '"scenario": "Tenure pending"' in context
    assert '"field": "tenure_months"' in context
    assert '"recording_status": "not_connected_read_only"' in context
    assert messages[1:] == [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi"},
        {"role": "user", "content": "Can I ask a question first?"},
    ]


def test_manager_discards_unsupported_history_roles():
    messages = build_manager_messages(
        initialize_scenario(),
        "Next",
        history=[{"role": "tool", "content": "pretend saved"}, {"role": "user", "content": "Earlier"}],
    )
    assert messages[1:] == [
        {"role": "user", "content": "Earlier"},
        {"role": "user", "content": "Next"},
    ]


def test_context_building_does_not_mutate_session_state():
    state = initialize_scenario()
    original = deepcopy(state)
    build_manager_messages(state, "My monthly income is 50000.")
    assert state == original

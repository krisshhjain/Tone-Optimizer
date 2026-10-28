import pytest

from core.state import PRESETS, accept_value, active_rule, initialize_scenario, reset_state, rule_statuses


def active_field(state):
    rule = active_rule(state["accepted_values"])
    return rule["field"] if rule else None


def test_fresh_starts_at_consent():
    state = initialize_scenario()
    assert active_field(state) == "consent"
    assert not any(row["status"] == "completed" for row in rule_statuses(state["accepted_values"]))


@pytest.mark.parametrize("scenario,field", [
    ("Tenure pending", "tenure_months"),
    ("Monthly income pending", "monthly_income"),
    ("Document receipt pending", "demo_pan_receipt"),
])
def test_presets_have_coherent_progress(scenario, field):
    state = initialize_scenario(scenario)
    assert active_field(state) == field
    statuses = rule_statuses(state["accepted_values"])
    assert all(row["status"] == "completed" for row in statuses[:next(i for i, r in enumerate(statuses) if r["field"] == field)])


def test_valid_values_advance_and_cannot_skip():
    state = initialize_scenario()
    with pytest.raises(ValueError):
        accept_value(state, "loan_amount", 100000)
    for field, value, next_field in [
        ("consent", True, "loan_amount"), ("loan_amount", 100000, "tenure_months"),
        ("tenure_months", 12, "employment_type"), ("employment_type", "other", "monthly_income"),
        ("monthly_income", 25000, "demo_pan_receipt"), ("demo_pan_receipt", True, None),
    ]:
        state = accept_value(state, field, value)
        assert active_field(state) == next_field


@pytest.mark.parametrize("field,value", [
    ("consent", False), ("loan_amount", 9000), ("tenure_months", 10),
    ("employment_type", "unknown"), ("monthly_income", 0), ("demo_pan_receipt", False),
])
def test_invalid_active_value_rejected(field, value):
    state = initialize_scenario()
    if field != "consent":
        state = accept_value(state, "consent", True)
    if field in {"tenure_months", "employment_type", "monthly_income", "demo_pan_receipt"}:
        state = accept_value(state, "loan_amount", 100000)
    if field in {"employment_type", "monthly_income", "demo_pan_receipt"}:
        state = accept_value(state, "tenure_months", 12)
    if field in {"monthly_income", "demo_pan_receipt"}:
        state = accept_value(state, "employment_type", "salaried")
    if field == "demo_pan_receipt":
        state = accept_value(state, "monthly_income", 30000)
    with pytest.raises(ValueError):
        accept_value(state, field, value)


def test_reset_restores_preset_and_clears_messages():
    state = initialize_scenario("Tenure pending")
    state["messages"].append({"role": "user", "content": "synthetic"})
    reset = reset_state("Tenure pending")
    assert reset["accepted_values"] == PRESETS["Tenure pending"]
    assert reset["messages"] == []


def test_manager_reply_cannot_advance_or_modify_values():
    state = initialize_scenario("Document receipt pending")
    original_values = state["accepted_values"].copy()
    # Model output is plain conversation text and is never passed to a state mutation helper.
    state["messages"].append({"role": "assistant", "content": "Your income was recorded."})
    assert state["accepted_values"] == original_values
    assert active_field(state) == "demo_pan_receipt"


def test_completed_journey_has_no_active_rule():
    state = initialize_scenario()
    for field, value in [("consent", True), ("loan_amount", 10000), ("tenure_months", 6),
                         ("employment_type", "other"), ("monthly_income", 1), ("demo_pan_receipt", True)]:
        state = accept_value(state, field, value)
    assert active_rule(state["accepted_values"]) is None
    assert all(row["status"] == "completed" for row in rule_statuses(state["accepted_values"]))


def test_unknown_presets_rejected():
    with pytest.raises(ValueError):
        initialize_scenario("Unknown")

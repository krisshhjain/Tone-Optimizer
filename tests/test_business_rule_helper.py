from copy import deepcopy

import pytest

from core.business_rule_helper import (
    ToolInputError,
    get_journey_context,
    get_tool_definitions,
    submit_information,
)
from core.state import active_rule, initialize_scenario, validate_journey_state


def statuses_by_field(result):
    return {item["field"]: item["status"] for item in result["outcomes"]}


def test_tool_schemas_describe_only_the_two_helper_tools():
    tools = get_tool_definitions()
    assert [tool["function"]["name"] for tool in tools] == ["get_journey_context", "submit_information"]
    submit = tools[1]["function"]["parameters"]
    assert submit["required"] == ["entries"]
    entry = submit["properties"]["entries"]["items"]
    assert entry["required"] == ["field", "value"]
    assert entry["properties"]["field"]["enum"] == [
        "consent", "loan_amount", "tenure_months", "employment_type", "monthly_income", "demo_pan_receipt",
    ]


def test_context_reports_rules_completed_active_pending_and_values():
    state = initialize_scenario("Tenure pending")
    result = get_journey_context(state)
    assert len(result["rules"]) == 6
    assert [r["field"] for r in result["completed_requirements"]] == ["consent", "loan_amount"]
    assert result["active_requirement"]["field"] == "tenure_months"
    assert [r["field"] for r in result["pending_requirements"]] == [
        "employment_type", "monthly_income", "demo_pan_receipt",
    ]
    assert result["accepted_values"] == state["accepted_values"]
    assert result["staged_values"] == {}


def test_fresh_scenario_requires_consent_before_retaining_any_value():
    state = initialize_scenario()
    before = deepcopy(state)
    response = submit_information(state, [
        {"field": "loan_amount", "value": 150000},
        {"field": "tenure_months", "value": 24},
    ])
    assert statuses_by_field(response["result"]) == {
        "loan_amount": "missing_prerequisite", "tenure_months": "missing_prerequisite",
    }
    assert response["state"] == before


def test_rejected_consent_does_not_store_any_other_fields():
    state = initialize_scenario()
    result = submit_information(state, [
        {"field": "loan_amount", "value": 150000},
        {"field": "consent", "value": False},
    ])
    assert statuses_by_field(result["result"]) == {
        "consent": "invalid", "loan_amount": "missing_prerequisite",
    }
    assert result["state"]["accepted_values"] == {}
    assert result["state"]["pending_values"] == {}


def test_multi_field_submission_is_processed_in_configured_order():
    state = initialize_scenario()
    response = submit_information(state, [
        {"field": "employment_type", "value": "salaried"},
        {"field": "tenure_months", "value": 24},
        {"field": "loan_amount", "value": 150000},
        {"field": "consent", "value": True},
    ])
    assert response["result"]["committed_fields"] == [
        "consent", "loan_amount", "tenure_months", "employment_type",
    ]
    assert response["result"]["active_requirement"]["field"] == "monthly_income"
    assert response["state"]["pending_values"] == {}


def test_future_value_is_staged_then_promoted_when_prerequisite_passes():
    state = initialize_scenario()
    consent = submit_information(state, [{"field": "consent", "value": True}])
    staged = submit_information(consent["state"], [{"field": "tenure_months", "value": 24}])
    assert statuses_by_field(staged["result"]) == {"tenure_months": "staged"}
    assert staged["state"]["accepted_values"] == {"consent": True}
    assert staged["state"]["pending_values"] == {"tenure_months": 24}
    assert active_rule(staged["state"]["accepted_values"])["field"] == "loan_amount"

    amount = submit_information(staged["state"], [{"field": "loan_amount", "value": 150000}])
    assert amount["result"]["committed_fields"] == ["loan_amount", "tenure_months"]
    assert amount["state"]["accepted_values"] == {
        "consent": True, "loan_amount": 150000, "tenure_months": 24,
    }
    assert amount["state"]["pending_values"] == {}
    assert amount["result"]["active_requirement"]["field"] == "employment_type"


def test_different_submission_cannot_masquerade_as_promoted_staged_value():
    state = submit_information(initialize_scenario(), [{"field": "consent", "value": True}])["state"]
    state = submit_information(state, [{"field": "tenure_months", "value": 12}])["state"]
    result = submit_information(state, [
        {"field": "loan_amount", "value": 150000},
        {"field": "tenure_months", "value": 24},
    ])
    assert result["state"]["accepted_values"]["tenure_months"] == 12
    assert statuses_by_field(result["result"])["tenure_months"] == "already_completed"
    assert "not applied" in next(x for x in result["result"]["outcomes"] if x["field"] == "tenure_months")["detail"]


@pytest.mark.parametrize("field,value", [
    ("loan_amount", 9999), ("tenure_months", 7), ("employment_type", "contractor"),
    ("monthly_income", 0), ("demo_pan_receipt", False),
])
def test_invalid_values_do_not_advance(field, value):
    presets = {
        "loan_amount": "Fresh application",
        "tenure_months": "Tenure pending",
        "employment_type": "Tenure pending",
        "monthly_income": "Monthly income pending",
        "demo_pan_receipt": "Document receipt pending",
    }
    # Prepare the valid prefix before the tested rule.
    state = initialize_scenario(presets[field])
    if field == "loan_amount":
        state = submit_information(state, [{"field": "consent", "value": True}])["state"]
    elif field == "tenure_months":
        state = submit_information(state, [{"field": "loan_amount", "value": 150000}])["state"]
    elif field == "employment_type":
        state = submit_information(state, [{"field": "tenure_months", "value": 12}])["state"]
    accepted = dict(state["accepted_values"])
    response = submit_information(state, [{"field": field, "value": value}])
    assert statuses_by_field(response["result"])[field] == "invalid"
    assert response["state"]["accepted_values"] == accepted
    assert response["result"]["active_requirement"]["field"] == field


def test_existing_accepted_or_staged_values_are_not_overwritten():
    completed = submit_information(initialize_scenario("Tenure pending"), [{"field": "loan_amount", "value": 99999}])
    assert statuses_by_field(completed["result"])["loan_amount"] == "already_completed"
    state = submit_information(initialize_scenario(), [{"field": "consent", "value": True}])["state"]
    staged = submit_information(state, [{"field": "tenure_months", "value": 12}])
    again = submit_information(staged["state"], [{"field": "tenure_months", "value": 36}])
    assert statuses_by_field(again["result"])["tenure_months"] == "staged"
    assert again["state"]["pending_values"]["tenure_months"] == 12


def test_unknown_fields_and_duplicate_fields_are_rejected_without_overwrite():
    state = initialize_scenario("Tenure pending")
    response = submit_information(state, [
        {"field": "real_pan", "value": "not accepted"},
        {"field": "tenure_months", "value": 12},
        {"field": "tenure_months", "value": 24},
    ])
    assert [outcome["status"] for outcome in response["result"]["outcomes"]] == [
        "unknown_field", "invalid", "invalid",
    ]
    assert response["state"]["pending_values"] == {}


@pytest.mark.parametrize("entries", [[], None, [{"field": "consent"}], [{"field": "consent", "value": True, "extra": 1}]])
def test_malformed_tool_arguments_raise_without_mutating_state(entries):
    state = initialize_scenario()
    before = deepcopy(state)
    with pytest.raises(ToolInputError):
        submit_information(state, entries)
    assert state == before


def test_malformed_states_and_out_of_order_accepted_values_are_rejected():
    state = initialize_scenario()
    state["accepted_values"] = {"consent": True, "tenure_months": 24}
    with pytest.raises(ValueError, match="skip"):
        validate_journey_state(state)
    state = initialize_scenario()
    state["pending_values"] = {"tenure_months": 24}
    with pytest.raises(ValueError, match="consent"):
        validate_journey_state(state)


def test_six_step_journey_completes_without_approval_claim():
    state = initialize_scenario()
    for field, value in [
        ("consent", True), ("loan_amount", 150000), ("tenure_months", 24),
        ("employment_type", "salaried"), ("monthly_income", 45000),
        ("demo_pan_receipt", True),
    ]:
        response = submit_information(state, [{"field": field, "value": value}])
        state = response["state"]
    assert response["result"]["journey_complete"] is True
    assert response["result"]["active_requirement"] is None
    assert set(state["accepted_values"]) == {
        "consent", "loan_amount", "tenure_months", "employment_type", "monthly_income", "demo_pan_receipt",
    }
    assert "approval" not in str(response["result"]).lower()

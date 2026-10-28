"""Pure helpers for deterministic, value-derived journey progress."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from core.rules import load_rules, validate_value

PRESETS: dict[str, dict[str, Any]] = {
    "Fresh application": {},
    "Tenure pending": {"consent": True, "loan_amount": 150000},
    "Monthly income pending": {
        "consent": True, "loan_amount": 150000, "tenure_months": 12,
        "employment_type": "salaried",
    },
    "Document receipt pending": {
        "consent": True, "loan_amount": 150000, "tenure_months": 12,
        "employment_type": "salaried", "monthly_income": 50000,
    },
}


def validate_accepted_values(values: dict[str, Any], rules: list[dict[str, Any]] | None = None) -> None:
    definitions = rules if rules is not None else load_rules()
    fields = {rule["field"] for rule in definitions}
    if set(values) - fields:
        raise ValueError("Accepted values contain an unknown field.")
    for rule in definitions:
        if rule["field"] in values and not validate_value(rule, values[rule["field"]]):
            raise ValueError(f"Invalid value for {rule['field']}.")


def completed_fields(values: dict[str, Any], rules: list[dict[str, Any]] | None = None) -> set[str]:
    definitions = rules if rules is not None else load_rules()
    validate_accepted_values(values, definitions)
    complete: set[str] = set()
    for rule in definitions:
        field = rule["field"]
        if field in values and validate_value(rule, values[field]):
            complete.add(field)
        else:
            break
    return complete


def rule_statuses(values: dict[str, Any], rules: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    definitions = rules if rules is not None else load_rules()
    complete = completed_fields(values, definitions)
    active_found = False
    statuses = []
    for rule in definitions:
        field = rule["field"]
        if field in complete:
            status = "completed"
        elif not active_found:
            status, active_found = "active", True
        else:
            status = "pending"
        statuses.append({**rule, "status": status})
    return statuses


def active_rule(values: dict[str, Any], rules: list[dict[str, Any]] | None = None) -> dict[str, Any] | None:
    return next((item for item in rule_statuses(values, rules) if item["status"] == "active"), None)


def initialize_scenario(name: str = "Fresh application", rules: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    if name not in PRESETS:
        raise ValueError(f"Unknown scenario: {name}")
    values = deepcopy(PRESETS[name])
    validate_accepted_values(values, rules)
    return {"scenario": name, "accepted_values": values, "messages": []}


def accept_value(state: dict[str, Any], field: str, value: Any, rules: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    definitions = rules if rules is not None else load_rules()
    current = deepcopy(state)
    current_values = current.setdefault("accepted_values", {})
    validate_accepted_values(current_values, definitions)
    active = active_rule(current_values, definitions)
    if active is None or active["field"] != field:
        raise ValueError("Only the currently active field can be accepted.")
    rule = next(item for item in definitions if item["field"] == field)
    if not validate_value(rule, value):
        raise ValueError(f"Invalid value for {field}.")
    current_values[field] = value
    return current


def reset_state(name: str, rules: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return initialize_scenario(name, rules)

"""Pure helpers for validated, sequence-derived journey state."""

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
    """Validate values and require accepted rules to form an uninterrupted prefix."""
    definitions = rules if rules is not None else load_rules()
    if not isinstance(values, dict):
        raise ValueError("Accepted values must be an object.")
    fields = {rule["field"] for rule in definitions}
    if set(values) - fields:
        raise ValueError("Accepted values contain an unknown field.")
    found_gap = False
    for rule in definitions:
        field = rule["field"]
        if field not in values:
            found_gap = True
        elif found_gap:
            raise ValueError("Accepted values cannot skip a required prerequisite.")
        elif not validate_value(rule, values[field]):
            raise ValueError(f"Invalid accepted value for {field}.")


def completed_fields(values: dict[str, Any], rules: list[dict[str, Any]] | None = None) -> set[str]:
    definitions = rules if rules is not None else load_rules()
    validate_accepted_values(values, definitions)
    return {rule["field"] for rule in definitions if rule["field"] in values}


def validate_journey_state(state: dict[str, Any], rules: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Return a normalized copy of state or reject malformed/inconsistent state."""
    definitions = rules if rules is not None else load_rules()
    if not isinstance(state, dict):
        raise ValueError("Journey state must be an object.")
    normalized = deepcopy(state)
    normalized.setdefault("accepted_values", {})
    normalized.setdefault("pending_values", {})
    normalized.setdefault("messages", [])
    normalized.setdefault("tool_events", [])
    if not isinstance(normalized.get("scenario"), str):
        raise ValueError("Journey scenario must be a string.")
    if normalized["scenario"] not in PRESETS:
        raise ValueError("Journey scenario is not a configured synthetic preset.")
    validate_accepted_values(normalized["accepted_values"], definitions)

    pending = normalized["pending_values"]
    if not isinstance(pending, dict):
        raise ValueError("Pending values must be an object.")
    fields = {rule["field"] for rule in definitions}
    if set(pending) - fields:
        raise ValueError("Pending values contain an unknown field.")
    if set(pending) & set(normalized["accepted_values"]):
        raise ValueError("A field cannot be both accepted and pending.")
    if pending and normalized["accepted_values"].get("consent") is not True:
        raise ValueError("Values cannot be staged before explicit consent.")
    active_index = len(completed_fields(normalized["accepted_values"], definitions))
    for index, rule in enumerate(definitions):
        field = rule["field"]
        if field in pending:
            if index <= active_index:
                raise ValueError("Pending values must be for a future rule after a missing prerequisite.")
            if not validate_value(rule, pending[field]):
                raise ValueError(f"Invalid pending value for {field}.")

    for key in ("messages", "tool_events"):
        if not isinstance(normalized[key], list):
            raise ValueError(f"{key} must be a list.")
    return normalized


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
    definitions = rules if rules is not None else load_rules()
    state = {
        "scenario": name,
        "accepted_values": deepcopy(PRESETS[name]),
        "pending_values": {},
        "messages": [],
        "tool_events": [],
    }
    return validate_journey_state(state, definitions)


def promote_pending_values(state: dict[str, Any], rules: list[dict[str, Any]] | None = None) -> list[str]:
    """Promote contiguous staged values from the active rule forward in-place."""
    definitions = rules if rules is not None else load_rules()
    promoted: list[str] = []
    while True:
        current = active_rule(state["accepted_values"], definitions)
        if current is None or current["field"] not in state["pending_values"]:
            return promoted
        field = current["field"]
        state["accepted_values"][field] = state["pending_values"].pop(field)
        promoted.append(field)


def accept_value(state: dict[str, Any], field: str, value: Any, rules: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Accept one valid value for the active rule; never overwrite an accepted field."""
    definitions = rules if rules is not None else load_rules()
    current = validate_journey_state(state, definitions)
    if field in current["accepted_values"]:
        raise ValueError(f"{field} is already accepted and cannot be overwritten.")
    active = active_rule(current["accepted_values"], definitions)
    if active is None or active["field"] != field:
        raise ValueError("Only the currently active field can be accepted.")
    rule = next(item for item in definitions if item["field"] == field)
    if not validate_value(rule, value):
        raise ValueError(f"Invalid value for {field}.")
    current["accepted_values"][field] = value
    promote_pending_values(current, definitions)
    return validate_journey_state(current, definitions)


def reset_state(name: str, rules: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return initialize_scenario(name, rules)

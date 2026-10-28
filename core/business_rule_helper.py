"""Deterministic Python tools for the fictional Personal Loan demo."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from core.rules import load_rules, validate_value
from core.state import (
    active_rule,
    completed_fields,
    promote_pending_values,
    rule_statuses,
    validate_journey_state,
)


class ToolInputError(ValueError):
    """Raised when a structured tool request is malformed as a whole."""


def get_tool_definitions(rules: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    definitions = rules if rules is not None else load_rules()
    fields = [rule["field"] for rule in definitions]
    return [
        {
            "type": "function",
            "function": {
                "name": "get_journey_context",
                "description": "Read the configured fictional journey and current accepted/staged values.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "submit_information",
                "description": (
                    "Submit proposed fictional field values for deterministic validation. "
                    "Only this helper may accept or stage information."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "entries": {
                            "type": "array",
                            "minItems": 1,
                            "items": {
                                "type": "object",
                                "properties": {
                                    "field": {"type": "string", "enum": fields},
                                    "value": {},
                                },
                                "required": ["field", "value"],
                                "additionalProperties": False,
                            },
                        }
                    },
                    "required": ["entries"],
                    "additionalProperties": False,
                },
            },
        },
    ]


def _active_summary(values: dict[str, Any], rules: list[dict[str, Any]]) -> dict[str, Any] | None:
    current = active_rule(values, rules)
    return ({key: current[key] for key in ("id", "field", "label")} if current else None)


def get_journey_context(state: dict[str, Any], rules: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Return the configured rules and validated current journey state."""
    definitions = rules if rules is not None else load_rules()
    normalized = validate_journey_state(state, definitions)
    statuses = rule_statuses(normalized["accepted_values"], definitions)
    return {
        "ok": True,
        "scenario": normalized["scenario"],
        "rules": definitions,
        "completed_requirements": [row for row in statuses if row["status"] == "completed"],
        "active_requirement": next((row for row in statuses if row["status"] == "active"), None),
        "pending_requirements": [row for row in statuses if row["status"] == "pending"],
        "accepted_values": deepcopy(normalized["accepted_values"]),
        "staged_values": deepcopy(normalized["pending_values"]),
    }


def submit_information(
    state: dict[str, Any],
    entries: list[dict[str, Any]],
    rules: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Validate proposed values and return a new state plus per-field outcomes."""
    definitions = rules if rules is not None else load_rules()
    current = validate_journey_state(state, definitions)
    if not isinstance(entries, list) or not entries:
        raise ToolInputError("entries must be a non-empty list.")
    for entry in entries:
        if not isinstance(entry, dict) or "field" not in entry or "value" not in entry:
            raise ToolInputError("Each entry must contain both field and value.")
        if set(entry) - {"field", "value"}:
            raise ToolInputError("Entries may contain only field and value.")

    outcomes: list[dict[str, Any] | None] = [None] * len(entries)
    rule_order = {rule["field"]: rule["order"] for rule in definitions}
    known_indexes: dict[str, list[int]] = {}
    for index, entry in enumerate(entries):
        field = entry["field"]
        if not isinstance(field, str) or field not in rule_order:
            outcomes[index] = {
                "field": field if isinstance(field, str) else None,
                "status": "unknown_field",
                "detail": "The field is not configured.",
            }
        else:
            known_indexes.setdefault(field, []).append(index)

    duplicated = {field for field, indexes in known_indexes.items() if len(indexes) > 1}
    for field in duplicated:
        for index in known_indexes[field]:
            outcomes[index] = {
                "field": field,
                "status": "invalid",
                "detail": "Submit each field once per tool call; no value was changed.",
            }

    primary = [
        (indexes[0], field)
        for field, indexes in known_indexes.items()
        if field not in duplicated
    ]
    primary.sort(key=lambda item: (rule_order[item[1]], item[0]))
    submitted_fields = {field for _, field in primary}
    promoted_this_call: set[str] = set()
    committed_this_call: set[str] = set()

    for index, field in primary:
        value = entries[index]["value"]
        if field in current["accepted_values"]:
            was_promoted = field in promoted_this_call
            same_value = current["accepted_values"][field] == value
            status = "accepted" if was_promoted and same_value else "already_completed"
            if status == "accepted":
                detail = "The staged value was promoted after its prerequisites passed."
            elif was_promoted:
                detail = "A different staged value was promoted; the newly proposed value was not applied."
            else:
                detail = "Accepted values cannot be overwritten."
            outcomes[index] = {"field": field, "status": status, "detail": detail}
            continue
        if field in current["pending_values"]:
            outcomes[index] = {
                "field": field,
                "status": "staged",
                "detail": "This field is already staged; its existing value was kept.",
            }
            continue

        consented = current["accepted_values"].get("consent") is True
        if field != "consent" and not consented:
            outcomes[index] = {
                "field": field,
                "status": "missing_prerequisite",
                "detail": "Explicit demo consent must be accepted before retaining application values.",
            }
            continue

        rule = next(item for item in definitions if item["field"] == field)
        if not validate_value(rule, value):
            outcomes[index] = {
                "field": field,
                "status": "invalid",
                "detail": "The value does not satisfy this configured fictional rule.",
            }
            continue

        active = active_rule(current["accepted_values"], definitions)
        if active is not None and active["field"] == field:
            current["accepted_values"][field] = value
            committed_this_call.add(field)
            outcomes[index] = {"field": field, "status": "accepted", "detail": "Validated and committed."}
            promoted = promote_pending_values(current, definitions)
            promoted_this_call.update(promoted)
            committed_this_call.update(promoted)
            for promoted_field in promoted:
                if promoted_field in submitted_fields:
                    promoted_index = next(i for i, f in primary if f == promoted_field)
                    outcomes[promoted_index] = {
                        "field": promoted_field,
                        "status": "accepted",
                        "detail": "Previously staged value was promoted after its prerequisites passed.",
                    }
        elif active is not None:
            current["pending_values"][field] = value
            outcomes[index] = {"field": field, "status": "staged", "detail": "Valid future value staged."}
        else:
            outcomes[index] = {
                "field": field,
                "status": "already_completed",
                "detail": "The fictional journey is already complete; accepted values cannot be overwritten.",
            }

    normalized = validate_journey_state(current, definitions)
    complete = completed_fields(normalized["accepted_values"], definitions)
    result = {
        "ok": True,
        "outcomes": [item for item in outcomes if item is not None],
        "committed_fields": [rule["field"] for rule in definitions if rule["field"] in committed_this_call],
        "active_requirement": _active_summary(normalized["accepted_values"], definitions),
        "journey_complete": len(complete) == len(definitions),
    }
    return {"state": normalized, "result": result}

"""Load and validate the fictional Personal Loan demo rules."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_RULES_PATH = Path(__file__).resolve().parents[1] / "config" / "pl_rules.json"


def load_rules(path: str | Path = DEFAULT_RULES_PATH) -> list[dict[str, Any]]:
    """Load configured rules and reject malformed or unordered definitions."""
    with Path(path).open(encoding="utf-8") as rules_file:
        rules = json.load(rules_file)
    if not isinstance(rules, list) or len(rules) != 6:
        raise ValueError("Exactly six rules must be configured.")
    ids = [rule.get("id") for rule in rules]
    fields = [rule.get("field") for rule in rules]
    orders = [rule.get("order") for rule in rules]
    if len(set(ids)) != 6 or len(set(fields)) != 6:
        raise ValueError("Rule IDs and fields must be unique.")
    if orders != list(range(1, 7)):
        raise ValueError("Rules must have unique sequential order values from 1 to 6.")
    for rule in rules:
        if not all(key in rule for key in ("id", "field", "order", "label", "validation")):
            raise ValueError("Every rule needs an ID, field, order, label, and validation metadata.")
    return rules


def validate_value(rule: dict[str, Any], value: Any) -> bool:
    """Return whether a candidate value satisfies one rule's configured metadata."""
    validation = rule["validation"]
    kind = validation["type"]
    if kind == "boolean":
        return type(value) is bool and (not validation.get("must_be_true") or value is True)
    if kind == "integer":
        if type(value) is not int:
            return False
        if "allowed" in validation:
            return value in validation["allowed"]
        return value >= validation.get("minimum", value) and value <= validation.get("maximum", value)
    if kind == "choice":
        return isinstance(value, str) and value in validation["allowed"]
    return False


def is_valid_value(field: str, value: Any, rules: list[dict[str, Any]] | None = None) -> bool:
    """Validate by configured field name."""
    definitions = rules if rules is not None else load_rules()
    rule = next((item for item in definitions if item["field"] == field), None)
    return rule is not None and validate_value(rule, value)

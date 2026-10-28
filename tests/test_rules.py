import json

import pytest

from core.rules import DEFAULT_RULES_PATH, is_valid_value, load_rules


def test_config_has_six_unique_ordered_rules():
    parsed = json.loads(DEFAULT_RULES_PATH.read_text(encoding="utf-8"))
    rules = load_rules()
    assert len(rules) == 6
    assert [rule["order"] for rule in rules] == list(range(1, 7))
    assert len({rule["id"] for rule in rules}) == 6
    assert len({rule["field"] for rule in rules}) == 6
    assert parsed == rules


@pytest.mark.parametrize("field,value", [
    ("consent", True), ("loan_amount", 10000), ("loan_amount", 500000),
    ("tenure_months", 6), ("tenure_months", 36),
    ("employment_type", "self_employed"), ("monthly_income", 1),
    ("demo_pan_receipt", True),
])
def test_valid_values(field, value):
    assert is_valid_value(field, value)


@pytest.mark.parametrize("field,value", [
    ("consent", False), ("loan_amount", 9999), ("loan_amount", 500001),
    ("loan_amount", True), ("tenure_months", 7),
    ("employment_type", "contractor"), ("monthly_income", 0),
    ("monthly_income", -5), ("demo_pan_receipt", False),
])
def test_invalid_values(field, value):
    assert not is_valid_value(field, value)


def test_every_rule_has_validation_metadata():
    assert all(rule["id"] and rule["field"] and rule["validation"] for rule in load_rules())

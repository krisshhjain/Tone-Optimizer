"""Nemotron Manager orchestration and deterministic tool dispatch."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from core.business_rule_helper import (
    ToolInputError,
    get_journey_context,
    get_tool_definitions,
    submit_information,
)
from core.model_client import ModelConfig, ModelError, create_completion
from core.rules import DEFAULT_RULES_PATH, load_rules
from core.state import validate_journey_state

DEFAULT_PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "v0_orchestration.md"
DEFAULT_MAX_TOOL_ROUNDS = 4


def _read(value: Any, key: str, default: Any = None) -> Any:
    return value.get(key, default) if isinstance(value, dict) else getattr(value, key, default)


def build_manager_messages(
    state: dict[str, Any],
    user_message: str,
    history: list[dict[str, Any]] | None = None,
    rules_path: str | Path = DEFAULT_RULES_PATH,
    prompt_path: str | Path = DEFAULT_PROMPT_PATH,
) -> list[dict[str, Any]]:
    """Build current rule/state context and conversation turns for Nemotron."""
    rules = load_rules(rules_path)
    normalized = validate_journey_state(state, rules)
    context = get_journey_context(normalized, rules)
    system_content = Path(prompt_path).read_text(encoding="utf-8").strip()
    system_content += (
        "\n\nAuthoritative current journey context (JSON):\n"
        + json.dumps(context, ensure_ascii=False, sort_keys=True)
        + "\n\nUse the supplied helper tools for every validation or recording operation."
        " Tool results, not your claims, determine accepted values and progress."
        " Do not claim success unless the corresponding tool result reports accepted or promoted fields."
    )
    messages: list[dict[str, Any]] = [{"role": "system", "content": system_content}]
    for message in history or []:
        role, content = _read(message, "role"), _read(message, "content")
        if role in {"user", "assistant"} and isinstance(content, str):
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_message})
    return messages


def _tool_result(
    name: str,
    arguments_text: Any,
    call_id: Any,
    state: dict[str, Any],
    rules: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Run one allowlisted helper and create a minimal internal trace event."""
    current = validate_journey_state(state, rules)
    fields: list[str] = []
    try:
        if not isinstance(arguments_text, str):
            raise ToolInputError("Tool arguments must be JSON text.")
        arguments = json.loads(arguments_text)
        if not isinstance(arguments, dict):
            raise ToolInputError("Tool arguments must be a JSON object.")
        if name == "get_journey_context":
            if arguments:
                raise ToolInputError("get_journey_context takes no arguments.")
            result = get_journey_context(current, rules)
        elif name == "submit_information":
            if set(arguments) != {"entries"}:
                raise ToolInputError("submit_information requires only entries.")
            entries = arguments["entries"]
            if isinstance(entries, list):
                fields = [entry.get("field") for entry in entries if isinstance(entry, dict)]
            submission = submit_information(current, entries, rules)
            current = submission["state"]
            result = submission["result"]
        else:
            raise ToolInputError("Unknown helper tool.")
        success = bool(result.get("ok"))
        outcomes = result.get("outcomes", [])
        success = success and all(
            outcome.get("status") in {"accepted", "staged"} for outcome in outcomes
        )
        active = result.get("active_requirement") or get_journey_context(current, rules)["active_requirement"]
        event = {
            "tool": name,
            "fields": [field for field in fields if isinstance(field, str)],
            "outcomes": [
                {"field": outcome.get("field"), "status": outcome.get("status")}
                for outcome in outcomes
            ],
            "success": success,
            "active_rule": active.get("id") if active else None,
        }
        current["tool_events"].append(deepcopy(event))
        result["tool_call_id"] = call_id
        return current, result, event
    except (ToolInputError, TypeError, ValueError, KeyError):
        active_id = _active_rule_id(current, rules)
        active_requirement = next(
            ({key: rule[key] for key in ("id", "field", "label")} for rule in rules if rule["id"] == active_id),
            None,
        )
        event = {
            "tool": name if isinstance(name, str) else "unknown",
            "fields": [field for field in fields if isinstance(field, str)],
            "outcomes": [],
            "success": False,
            "active_rule": _active_rule_id(current, rules),
        }
        current["tool_events"].append(deepcopy(event))
        return current, {
            "ok": False,
            "error": "The helper rejected malformed or unsupported tool arguments; no value was changed.",
            "tool_call_id": call_id,
            "outcomes": [],
            "committed_fields": [],
            "active_requirement": active_requirement,
            "journey_complete": active_requirement is None,
        }, event


def _active_rule_id(state: dict[str, Any], rules: list[dict[str, Any]]) -> str | None:
    context = get_journey_context(state, rules)
    active = context["active_requirement"]
    return act…2494 tokens truncated… helper.")),
    ])
    original = initialize_scenario()
    result = run_manager_turn(original, "I consent and want 150000.", model_config(), client)
    assert result["reply"] == "Consent and amount were accepted by the demo helper."
    assert result["error"] is None
    assert result["state"]["accepted_values"] == {"consent": True, "loan_amount": 150000}
    assert original["accepted_values"] == {}
    assert result["tool_events"][0]["success"] is True
    assert result["tool_events"][0]["active_rule"] == "BR-03"
    second_messages = client.requests[1]["messages"]
    assert second_messages[-1]["role"] == "tool"
    assert second_messages[-1]["tool_call_id"] == "call-1"
    assert json.loads(second_messages[-1]["content"])["committed_fields"] == ["consent", "loan_amount"]
    assert second_messages[-2]["role"] == "assistant"
    assert second_messages[-2]["tool_calls"][0]["id"] == "call-1"


def test_clarification_turn_does_not_mutate_application_values():
    client = SequenceClient([completion(assistant_message("The configured rule lists the allowed options."))])
    state = initialize_scenario("Monthly income pending")
    result = run_manager_turn(state, "Why is monthly income needed?", model_config(), client)
    assert result["reply"] == "The configured rule lists the allowed options."
    assert result["state"]["accepted_values"] == state["accepted_values"]
    assert result["state"]["pending_values"] == {}
    assert result["state"]["tool_events"] == []


def test_unknown_tool_gets_correlated_error_and_does_not_mutate_state():
    client = SequenceClient([
        completion(assistant_message(calls=[tool_call("invented_tool", "{}", "call-unknown")])),
        completion(assistant_message("I could not run that operation.")),
    ])
    result = run_manager_turn(initialize_scenario(), "Please save this.", model_config(), client)
    tool_message = client.requests[1]["messages"][-1]
    assert tool_message["tool_call_id"] == "call-unknown"
    assert json.loads(tool_message["content"])["ok"] is False
    assert result["state"]["accepted_values"] == {}


def test_invalid_tool_outcome_cannot_be_overridden_by_false_model_success():
    invalid_submit = {"entries": [{"field": "consent", "value": False}]}
    client = SequenceClient([
        completion(assistant_message(calls=[tool_call("submit_information", json.dumps(invalid_submit))])),
        completion(assistant_message("Your consent was saved and the journey advanced.")),
    ])
    result = run_manager_turn(initialize_scenario(), "No, not really.", model_config(), client)
    assert result["reply"] != "Your consent was saved and the journey advanced."
    assert "rejected: Explicit customer consent" in result["reply"]
    assert "Current requirement: Explicit customer consent" in result["reply"]
    assert result["state"]["accepted_values"] == {}
    assert result["tool_events"][0]["success"] is False


def test_malformed_tool_arguments_cannot_mutate_state_or_claim_success():
    client = SequenceClient([
        completion(assistant_message(calls=[tool_call("submit_information", "{bad json")])),
        completion(assistant_message("The request was rejected.")),
    ])
    result = run_manager_turn(initialize_scenario(), "Consent yes.", model_config(), client)
    assert json.loads(client.requests[1]["messages"][-1]["content"])["ok"] is False
    assert result["state"]["accepted_values"] == {}


def test_missing_tool_arguments_are_returned_to_model_as_failure():
    client = SequenceClient([
        completion(assistant_message(calls=[tool_call("submit_information", None)])),
        completion(assistant_message("The helper could not process the request.")),
    ])
    result = run_manager_turn(initialize_scenario(), "Yes", model_config(), client)
    tool_result = json.loads(client.requests[1]["messages"][-1]["content"])
    assert tool_result["ok"] is False
    assert tool_result["committed_fields"] == []
    assert tool_result["active_requirement"]["field"] == "consent"
    assert result["state"]["accepted_values"] == {}


def test_empty_assistant_response_is_never_a_fake_success():
    client = SequenceClient([completion(assistant_message("  "))])
    result = run_manager_turn(initialize_scenario(), "Hi", model_config(), client)
    assert result["reply"] is None
    assert result["error"] == "The model returned an empty response."
    assert result["state"]["accepted_values"] == {}


def test_missing_tool_call_id_stops_without_running_helper():
    client = SequenceClient([completion(assistant_message(calls=[tool_call("get_journey_context", "{}", None)]))])
    result = run_manager_turn(initialize_scenario(), "What is next?", model_config(), client)
    assert result["error"] and "identifier" in result["error"]
    assert result["state"]["tool_events"] == []


def test_tool_loop_is_bounded():
    context_call = completion(assistant_message(calls=[tool_call("get_journey_context", "{}")]))
    client = SequenceClient([context_call, context_call])
    result = run_manager_turn(initialize_scenario(), "Check progress", model_config(), client, max_tool_rounds=1)
    assert result["error"] and "tool-call limit" in result["error"]
    assert len(client.requests) == 2
    assert len(result["state"]["tool_events"]) == 1


def test_api_failure_returns_safe_error_and_preserves_values():
    client = SequenceClient([TimeoutError("secret should not appear")])
    state = initialize_scenario()
    result = run_manager_turn(state, "Yes", model_config(), client)
    assert result["error"] == "The model request timed out. Please try again."
    assert result["state"]["accepted_values"] == {}

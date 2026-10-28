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
        }, event


def _active_rule_id(state: dict[str, Any], rules: list[dict[str, Any]]) -> str | None:
    context = get_journey_context(state, rules)
    active = context["active_requirement"]
    return active["id"] if active else None


def _helper_outcome_summary(outcomes: list[dict[str, Any]], state: dict[str, Any], rules: list[dict[str, Any]]) -> str:
    labels = {rule["field"]: rule["label"] for rule in rules}
    groups: dict[str, list[str]] = {}
    for outcome in outcomes:
        field = outcome.get("field")
        status = outcome.get("status", "failed")
        display = labels.get(field, field or "tool request")
        groups.setdefault(status, []).append(display)
    parts = []
    for status, verb in (
        ("accepted", "accepted"), ("staged", "staged"),
        ("invalid", "rejected"), ("missing_prerequisite", "blocked by a prerequisite"),
        ("unknown_field", "not recognized"), ("already_completed", "already completed and unchanged"),
    ):
        if groups.get(status):
            parts.append(f"{verb}: {', '.join(groups[status])}")
    active = _active_rule_id(state, rules)
    active_label = next((rule["label"] for rule in rules if rule["id"] == active), None)
    summary = "; ".join(parts) or "the helper could not process the request"
    if active_label:
        summary += f". Current requirement: {active_label}."
    else:
        summary += ". The fictional journey is complete."
    return summary


def _assistant_tool_message(message: Any, calls: list[Any]) -> dict[str, Any]:
    serialized = {
        "role": "assistant",
        "content": _read(message, "content"),
        "tool_calls": [],
    }
    for call in calls:
        function = _read(call, "function", {})
        serialized["tool_calls"].append({
            "id": _read(call, "id"),
            "type": "function",
            "function": {
                "name": _read(function, "name") if isinstance(_read(function, "name"), str) else "unknown",
                "arguments": (
                    _read(function, "arguments")
                    if isinstance(_read(function, "arguments"), str)
                    else json.dumps(_read(function, "arguments"))
                    if isinstance(_read(function, "arguments"), (dict, list))
                    else "{}"
                ),
            },
        })
    return serialized


def run_manager_turn(
    state: dict[str, Any],
    user_message: str,
    config: ModelConfig,
    client: Any = None,
    *,
    max_tool_rounds: int = DEFAULT_MAX_TOOL_ROUNDS,
) -> dict[str, Any]:
    """Run a bounded tool-call loop; only helper-returned state is committed."""
    rules = load_rules()
    current = validate_journey_state(state, rules)
    current["messages"].append({"role": "user", "content": user_message})
    transcript = list(current["messages"][:-1])
    messages = build_manager_messages(current, user_message, transcript)
    tools = get_tool_definitions(rules)
    if max_tool_rounds < 0:
        raise ValueError("max_tool_rounds cannot be negative.")

    rounds = 0
    helper_outcomes: list[dict[str, Any]] = []
    helper_operation_failed = False
    while True:
        try:
            response = create_completion(messages, config, client, tools=tools, tool_choice="auto")
        except ModelError as exc:
            return {"state": current, "reply": None, "error": str(exc), "tool_events": current["tool_events"]}
        try:
            response_message = response.choices[0].message
        except (AttributeError, IndexError, KeyError, TypeError):
            return {
                "state": current, "reply": None,
                "error": "The model returned an unreadable response.",
                "tool_events": current["tool_events"],
            }
        calls = _read(response_message, "tool_calls", None) or []
        if not calls:
            reply = _read(response_message, "content")
            if not isinstance(reply, str) or not reply.strip():
                return {
                    "state": current, "reply": None,
                    "error": "The model returned an empty response.",
                    "tool_events": current["tool_events"],
                }
            reply = _helper_outcome_summary(helper_outcomes, current, rules) if helper_operation_failed else reply.strip()
            current["messages"].append({"role": "assistant", "content": reply})
            return {"state": current, "reply": reply, "error": None, "tool_events": current["tool_events"]}

        if rounds >= max_tool_rounds:
            return {
                "state": current, "reply": None,
                "error": "The model reached the tool-call limit for this turn. No further tools were run.",
                "tool_events": current["tool_events"],
            }
        messages.append(_assistant_tool_message(response_message, calls))
        for call in calls:
            call_id = _read(call, "id")
            function = _read(call, "function", {})
            name = _read(function, "name")
            argumen…3396 tokens truncated…ndef reset_state(name: str, rules: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return initialize_scenario(name, rules)

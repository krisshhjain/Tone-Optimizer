"""Nemotron Manager orchestration and deterministic tool dispatch."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path
from types import MappingProxyType
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

PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"
PROMPT_PATHS = MappingProxyType({
    "V0": PROMPTS_DIR / "v0_orchestration.md",
    "V1": PROMPTS_DIR / "v1_conversational.md",
})
DEFAULT_PROMPT_VERSION = "V0"
DEFAULT_MAX_TOOL_ROUNDS = 4


def resolve_prompt_path(prompt_version: str = DEFAULT_PROMPT_VERSION) -> Path:
    """Resolve an explicitly allowlisted prompt version to its repository file."""
    if not isinstance(prompt_version, str) or prompt_version not in PROMPT_PATHS:
        allowed = ", ".join(PROMPT_PATHS)
        raise ValueError(f"Unsupported prompt version {prompt_version!r}; choose one of: {allowed}.")
    return PROMPT_PATHS[prompt_version]


def _read(value: Any, key: str, default: Any = None) -> Any:
    return value.get(key, default) if isinstance(value, dict) else getattr(value, key, default)


def build_manager_messages(
    state: dict[str, Any],
    user_message: str,
    history: list[dict[str, Any]] | None = None,
    rules_path: str | Path = DEFAULT_RULES_PATH,
    *,
    prompt_version: str = DEFAULT_PROMPT_VERSION,
) -> list[dict[str, Any]]:
    """Build current rule/state context and conversation turns for Nemotron."""
    rules = load_rules(rules_path)
    normalized = validate_journey_state(state, rules)
    context = get_journey_context(normalized, rules)
    system_content = resolve_prompt_path(prompt_version).read_text(encoding="utf-8").strip()
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
        succeeded = [outcome for outcome in outcomes if outcome.get("status") in {"accepted", "staged"}]
        failed = [outcome for outcome in outcomes if outcome.get("status") not in {"accepted", "staged"}]
        status = "read" if name == "get_journey_context" and success else (
            "success" if success and not failed else "partial" if succeeded else "rejected"
        )
        active = result.get("active_requirement") or get_journey_context(current, rules)["active_requirement"]
        event = {
            "tool": name,
            "fields": [field for field in fields if isinstance(field, str)],
            "outcomes": [
                {"field": outcome.get("field"), "status": outcome.get("status")}
                for outcome in outcomes
            ],
            "status": status,
            "success": status in {"success", "read"},
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
            "status": "rejected",
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
    return active["id"] if active else None


def _invalid_value_guidance(rule: dict[str, Any]) -> str:
    """Explain a rejected value using only its configured validation metadata."""
    label = re.sub(r"\s*\([^)]*\)", "", rule.get("label", "That value")).strip()
    validation = rule.get("validation", {})
    kind = validation.get("type")
    if kind == "integer" and "allowed" in validation:
        choices = validation["allowed"]
        if rule.get("field") == "tenure_months":
            return f"That tenure isn't one of the permitted demo options. Please choose {', '.join(map(str, choices))} months."
        return f"{label} must be one of the configured options: {', '.join(map(str, choices))}."
    if kind == "integer" and "minimum" in validation and "maximum" in validation:
        return f"{label} must be between {validation['minimum']} and {validation['maximum']}."
    if kind == "integer" and "minimum" in validation:
        return f"{label} must be a whole number of at least {validation['minimum']}."
    if kind == "choice":
        choices = [str(value).replace("_", " ") for value in validation.get("allowed", [])]
        return f"Please choose {', '.join(map(str, choices))} for {label.lower()}."
    if kind == "boolean" and validation.get("must_be_true"):
        return f"Please give a clear affirmative confirmation for {label.lower()} to continue."
    return f"That value doesn't meet the configured requirement for {label.lower()}."


def _helper_outcome_summary(
    outcomes: list[dict[str, Any]],
    state: dict[str, Any],
    rules: list[dict[str, Any]],
    *,
    operation_failed: bool = False,
) -> str:
    """Summarize actual helper results without exposing internal status labels."""
    by_field = {rule["field"]: rule for rule in rules}
    accepted: list[str] = []
    staged: list[str] = []
    rejected: list[str] = []
    other: list[str] = []
    for outcome in outcomes:
        field = outcome.get("field")
        rule = by_field.get(field)
        label = rule.get("label", "that field") if rule else "that field"
        status = outcome.get("status", "failed")
        if status == "accepted":
            accepted.append(label)
        elif status == "staged":
            staged.append(label)
        elif status == "invalid" and rule:
            rejected.append(_invalid_value_guidance(rule))
        elif status == "missing_prerequisite":
            other.append(f"{label} can't be added until its prerequisite is complete")
        elif status == "already_completed":
            other.append(f"{label} was already complete and remains unchanged")
        elif status == "unknown_field":
            other.append("one requested item isn't part of this demo")
        elif status == "declined":
            other.append("no value was recorded because you declined")
        else:
            other.append(f"the helper couldn't process {label}")

    sentences: list[str] = []
    if accepted:
        sentences.append(f"The demo helper accepted {', '.join(accepted)}.")
    if staged:
        sentences.append(
            f"The demo helper staged {', '.join(staged)} for after the earlier requirements are complete."
        )
    sentences.extend(rejected)
    sentences.extend(f"{item[0].upper() + item[1]}." for item in other)
    if operation_failed and outcomes and all(
        outcome.get("status") in {"accepted", "staged"} for outcome in outcomes
    ):
        sentences.append("A separate helper operation could not be processed, and it made no change.")
    if not sentences:
        sentences.append("I couldn't process that request, and no value was changed.")

    active = _active_rule_id(state, rules)
    active_rule = next((rule for rule in rules if rule["id"] == active), None)
    if active_rule:
        sentences.append(f"The next required item is {active_rule['label']}.")
    else:
        sentences.append("The fictional demo journey is complete.")
    return " ".join(sentences)


def _is_refusal(message: str) -> bool:
    text = message.casefold()
    return any(phrase in text for phrase in (
        "i don't want to", "i do not want to", "don't want to share", "do not want to share",
        "don't want to give", "do not want to give", "rather not", "prefer not to",
        "i refuse", "no, i won't", "no i won't", "not comfortable sharing", "not comfortable giving",
    ))


def _refusal_response(state: dict[str, Any], rules: list[dict[str, Any]]) -> str:
    active = _active_rule_id(state, rules)
    label = next((rule["label"] for rule in rules if rule["id"] == active), "")
    return (
        f"Understood. I won't record a value. We can stop, answer a question, or continue later. "
        f"This required fictional field remains incomplete{f' ({label})' if label else ''}."
    )


_AFFIRMATIVE_SAVE_CLAIM = re.compile(
    r"\b(?:i(?:['’](?:ve|d))?|we(?:['’](?:ve|d))?|the system|everything|"
    r"(?:all\s+)?(?:your|the)\s+(?:information|details|data|\w+(?:\s+and\s+\w+)?)|"
    r"(?:all\s+)?(?:information|details|data))\s+"
    r"(?:(?:have|has|had|is|are|was|were|did|got|just|now|already|successfully|been|being)\s+)*"
    r"(?:saved|recorded|stored|submitted|saving|recording|storing|submitting)\b"
    r"|\b(?:saved|recorded|stored|submitted)\s+(?:your|the)\s+"
    r"(?:information|details|data|\w+(?:\s+and\s+\w+)?)\b",
    re.IGNORECASE,
)


def _has_unsupported_save_claim(
    reply: str,
    state: dict[str, Any] | None = None,
    rules: list[dict[str, Any]] | None = None,
) -> bool:
    """Return true only for an ungrounded affirmative claim that data was saved."""
    text = reply.strip()
    if not text or "?" in text or not _AFFIRMATIVE_SAVE_CLAIM.search(text):
        return False
    # A direct negation is an explanation that nothing was saved, not a success claim.
    if re.search(r"\b(?:not|never|n't|no)\b.{0,35}\b(?:saved|recorded|stored|submitted)\b", text, re.IGNORECASE):
        return False
    # The helper confirms only fictional session state, never external submission or storage.
    if re.search(r"\bsubmitted\b|\b(?:to|into)\s+(?:the\s+)?(?:bank|database|loan application)\b", text, re.IGNORECASE):
        return True

    if state is None or rules is None:
        return True
    accepted = state.get("accepted_values", {})
    pending = state.get("pending_values", {})
    mentioned: list[str] = []
    aliases = {
        "employment_type": ("employment", "employment type", "job category"),
        "monthly_income": ("income", "monthly income"),
        "loan_amount": ("loan amount", "amount"),
        "tenure_months": ("tenure", "months"),
        "consent": ("consent",),
        "demo_pan_receipt": ("receipt confirmation", "document receipt", "demo pan receipt"),
    }
    for rule in rules:
        terms = (rule.get("label", "").casefold(), *aliases.get(rule.get("field"), ()), rule.get("field", "").replace("_", " "))
        if any(term and re.search(rf"\b{re.escape(term)}\b", text, re.IGNORECASE) for term in terms):
            mentioned.append(rule["field"])
    if mentioned:
        return not all(field in accepted or field in pending for field in mentioned)
    # Unqualified claims may refer to already retained values; claims about everything require a complete state.
    if re.search(r"\b(?:all|everything)\b", text, re.IGNORECASE):
        return any(rule["field"] not in accepted and rule["field"] not in pending for rule in rules)
    return not bool(accepted or pending)


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
    prompt_version: str = DEFAULT_PROMPT_VERSION,
) -> dict[str, Any]:
    """Run a bounded tool-call loop; only helper-returned state is committed."""
    rules = load_rules()
    current = validate_journey_state(state, rules)
    current["messages"].append({"role": "user", "content": user_message})
    transcript = list(current["messages"][:-1])
    messages = build_manager_messages(
        current, user_message, transcript, prompt_version=prompt_version,
    )
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
            reply = _helper_outcome_summary(
                helper_outcomes, current, rules, operation_failed=helper_operation_failed,
            ) if helper_outcomes or helper_operation_failed else None
            if reply:
                reply += " The follow-up response could not be generated; no retry was attempted."
                current["messages"].append({"role": "assistant", "content": reply})
            return {"state": current, "reply": reply, "error": str(exc), "tool_events": current["tool_events"]}
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
            reply = reply.strip()
            if _is_refusal(user_message):
                reply = _refusal_response(current, rules)
            elif helper_operation_failed:
                reply = _helper_outcome_summary(
                    helper_outcomes, current, rules, operation_failed=helper_operation_failed,
                )
            elif _has_unsupported_save_claim(reply, current, rules):
                if helper_outcomes:
                    reply = "The helper confirms only the fictional session state; no information was submitted to a bank."
                else:
                    active = _active_rule_id(current, rules)
                    label = next((rule["label"] for rule in rules if rule["id"] == active), None)
                    reply = "I can't confirm that any new information was saved or submitted in this turn."
                    if label:
                        reply += f" The current required fictional field remains {label}."
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
            arguments = _read(function, "arguments")
            if not isinstance(call_id, str) or not call_id:
                return {
                    "state": current, "reply": None,
                    "error": "The model returned a tool call without an identifier. No tool was run.",
                    "tool_events": current["tool_events"],
                }
            if _is_refusal(user_message) and name == "submit_information":
                try:
                    requested = json.loads(arguments) if isinstance(arguments, str) else {}
                    entries = requested.get("entries", []) if isinstance(requested, dict) else []
                except (TypeError, ValueError):
                    entries = []
                fields = [entry.get("field") for entry in entries if isinstance(entry, dict)]
                result = {
                    "ok": False, "error": "No information was submitted because the customer declined.",
                    "outcomes": [{"field": field, "status": "declined"} for field in fields],
                    "committed_fields": [], "active_requirement": get_journey_context(current, rules)["active_requirement"],
                    "journey_complete": _active_rule_id(current, rules) is None,
                    "tool_call_id": call_id,
                }
                event = {
                    "tool": name, "fields": [field for field in fields if isinstance(field, str)],
                    "outcomes": [{"field": field, "status": "declined"} for field in fields],
                    "status": "rejected", "success": False,
                    "active_rule": _active_rule_id(current, rules),
                }
                current["tool_events"].append(deepcopy(event))
            else:
                current, result, _event = _tool_result(name, arguments, call_id, current, rules)
            if not result.get("ok"):
                helper_operation_failed = True
            helper_outcomes.extend(result.get("outcomes", []))
            if any(outcome.get("status") not in {"accepted", "staged"} for outcome in result.get("outcomes", [])):
                helper_operation_failed = True
            messages.append({
                "role": "tool",
                "tool_call_id": call_id,
                "content": json.dumps(result, ensure_ascii=False),
            })
        rounds += 1


"""Read-only Manager Agent context assembly for the V0 orchestration prompt."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.rules import DEFAULT_RULES_PATH, load_rules
from core.state import active_rule

DEFAULT_PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "v0_orchestration.md"


def build_manager_messages(
    state: dict[str, Any],
    user_message: str,
    history: list[dict[str, str]] | None = None,
    rules_path: str | Path = DEFAULT_RULES_PATH,
    prompt_path: str | Path = DEFAULT_PROMPT_PATH,
) -> list[dict[str, str]]:
    """Build a request containing authoritative rules, state, and prior turns."""
    rules = load_rules(rules_path)
    values = state.get("accepted_values", {})
    active = active_rule(values, rules)
    context = {
        "phase": "2_read_only",
        "scenario": state.get("scenario", "unknown"),
        "business_rules": rules,
        "accepted_values": values,
        "active_rule": active,
        "recording_status": "not_connected_read_only",
        "phase_constraints": [
            "customer statements are not accepted, validated, or saved",
            "do not move beyond the active rule",
            "use concise wording; do not imply an unpersisted value was noted or received",
            "only explain purposes specified by configured rules",
            "no unconfigured EMI, interest, underwriting, eligibility, DTI, or LTV claims",
        ],
    }
    system_content = Path(prompt_path).read_text(encoding="utf-8").strip()
    system_content += (
        "\n\nAuthoritative current journey context (JSON):\n"
        + json.dumps(context, ensure_ascii=False, sort_keys=True)
        + "\n\nThis phase is strictly read-only. Treat the latest message as unrecorded. Do not claim any value was"
        " accepted, validated, saved, recorded, verified, or used to advance the journey. Keep the active rule"
        " unchanged. Use concise wording, avoid repetitive limitation boilerplate, and do not imply the value was"
        " noted or received. Do not invent reasons or calculations absent from the configured rules."
    )
    messages = [{"role": "system", "content": system_content}]
    for message in history or []:
        role, content = message.get("role"), message.get("content")
        if role in {"user", "assistant"} and isinstance(content, str):
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_message})
    return messages

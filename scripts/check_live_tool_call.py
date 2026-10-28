"""Opt-in, single-request check for NVIDIA structured function calling."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.business_rule_helper import get_tool_definitions
from core.model_client import ModelConfig, ModelError, create_completion
from core.rules import load_rules


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="send one opt-in request to the configured model")
    args = parser.parse_args()
    if not args.live:
        parser.error("pass --live to send one provider request")

    try:
        config = ModelConfig.from_env()
        response = create_completion(
            [
                {"role": "system", "content": "Call get_journey_context once with an empty JSON object. Return no text."},
                {"role": "user", "content": "Check the current demo journey context."},
            ],
            config,
            tools=get_tool_definitions(load_rules()),
            tool_choice="auto",
            max_tokens=128,
        )
    except ModelError as exc:
        print(f"Live compatibility check failed: {exc}", file=sys.stderr)
        return 1

    try:
        tool_calls = response.choices[0].message.tool_calls or []
        for call in tool_calls:
            function = call.function
            if function.name == "get_journey_context":
                payload = json.loads(function.arguments)
                if payload == {}:
                    print("Structured function calling is supported by this configured endpoint/model.")
                    return 0
    except (AttributeError, IndexError, KeyError, TypeError, json.JSONDecodeError):
        pass

    print("No valid structured probe call was returned; support is unconfirmed.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

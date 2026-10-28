from copy import deepcopy
import json
from types import SimpleNamespace

from core.manager import build_manager_messages
from core.manager import run_manager_turn
from core.model_client import GenerationSettings, ModelConfig
from core.state import initialize_scenario


def test_manager_injects_all_rules_state_active_rule_and_history():
    state = initialize_scenario("Tenure pending")
    messages = build_manager_messages(
        state,
        "Can I ask a question first?",
        history=[
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
        ],
    )
    assert messages[0]["role"] == "system"
    context = messages[0]["content"]
    for rule_id in ("BR-01", "BR-02", "BR-03", "BR-04", "BR-05", "BR-06"):
        assert rule_id in context
    assert '"scenario": "Tenure pending"' in context
    assert '"field": "tenure_months"' in context
    assert '"staged_values": {}' in context
    assert "Use the supplied helper tools" in context
    assert messages[1:] == [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi"},
        {"role": "user", "content": "Can I ask a question first?"},
    ]


def test_manager_discards_unsupported_history_roles():
    messages = build_manager_messages(
        initialize_scenario(),
        "Next",
        history=[{"role": "tool", "content": "pretend saved"}, {"role": "user", "content": "Earlier"}],
    )
    assert messages[1:] == [
        {"role": "user", "content": "Earlier"},
        {"role": "user", "content": "Next"},
    ]


def test_context_building_does_not_mutate_session_state():
    state = initialize_scenario()
    original = deepcopy(state)
    build_manager_messages(state, "My monthly income is 50000.")
    assert state == original


def test_v0_prompt_limits_rationales_to_configured_rules():
    messages = build_manager_messages(initialize_scenario(), "Why do you ask?")
    prompt = messages[0]["content"]
    assert "Do not invent eligibility, approval, identity verification" in prompt
    assert "read-only" not in prompt.lower()
    assert "tool result reports accepted or promoted fields" in prompt


def model_config():
    return ModelConfig("fake-key", "https://example.invalid/v1", "fake-model", GenerationSettings())


def tool_call(name, arguments, call_id="call-1"):
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(name=name, arguments=arguments),
    )


def assistant_message(content=None, calls=None):
    return SimpleNamespace(content=content, tool_calls=calls or [])


def completion(message):
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class SequenceClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.requests.append(kwargs)
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def test_tool_round_trip_commits_only_helper_result_and_correlates_tool_id():
    proposed = [
        {"field": "loan_amount", "value": 150000},
        {"field": "consent", "value": True},
    ]
    client = SequenceClient([
        completion(assistant_message(calls=[tool_call("submit_information", json.dumps({"entries": proposed}))])),
        completion(assistant_message("Consent and amount were accepted by the demo helper.")),
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

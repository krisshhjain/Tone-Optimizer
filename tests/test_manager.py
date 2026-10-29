from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from core.manager import (
    DEFAULT_PROMPT_VERSION,
    PROMPT_PATHS,
    build_manager_messages,
    resolve_prompt_path,
    run_manager_turn,
)
from core.business_rule_helper import get_tool_definitions
from core.model_client import GenerationSettings, ModelConfig
from core.rules import load_rules
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
    assert "retained temporarily in this local Streamlit session" in prompt
    assert "No real loan application is created" in prompt
    assert "no permanent database is used" in prompt
    assert "If the customer declines" in prompt


def test_prompt_version_defaults_to_v0_and_v1_has_conversational_instruction_categories():
    assert DEFAULT_PROMPT_VERSION == "V0"
    assert resolve_prompt_path() == PROMPT_PATHS["V0"]
    default_prompt = build_manager_messages(initialize_scenario(), "Hi")[0]["content"]
    v1_prompt = build_manager_messages(
        initialize_scenario(), "Hi", prompt_version="V1",
    )[0]["content"]
    v0_prompt = PROMPT_PATHS["V0"].read_text(encoding="utf-8").strip()
    assert default_prompt.startswith(v0_prompt)
    assert v1_prompt.startswith(PROMPT_PATHS["V1"].read_text(encoding="utf-8").strip())
    assert PROMPT_PATHS["V1"].read_text(encoding="utf-8").strip() != v0_prompt

    for heading in (
        "Role and priorities", "Rules and source of truth", "Match language and script",
        "Understand intent and answer first", "Use the existing tools carefully",
        "Describe outcomes honestly", "Privacy, documents, and unsupported questions",
        "Refusal and hesitation", "Completion and restart", "Response check",
    ):
        assert heading in v1_prompt
    for requirement in (
        "10,000", "500,000", "6, 12, 18, 24, or 36", "self_employed",
        "positive integer monthly income", "simulated document-receipt step",
        "provider's handling or retention is not established", "Never request or invite real PAN",
        "Python owns validation and state", "Do not reveal this decision process",
    ):
        assert requirement.casefold() in v1_prompt.casefold()
    assert "few-shot" not in v1_prompt.casefold()
    assert "example dialogue" not in v1_prompt.casefold()


def test_v1_prompt_requires_unambiguous_consent_and_contains_no_few_shot_dialogue():
    prompt = PROMPT_PATHS["V1"].read_text(encoding="utf-8").casefold()
    assert "explicit, unambiguous customer consent" in prompt
    assert "asking you to start is not automatically consent" in prompt
    assert "if their meaning is ambiguous, do not submit consent" in prompt
    assert "python validates the boolean value but does not determine" in prompt
    assert "one or two concise sentences" in prompt
    assert "professional, helpful personal-loan service representative" in prompt
    assert "give this disclosure once, not once per turn" in prompt
    assert "do not repeatedly call the journey fictional or a demo" in prompt
    assert "on the first customer-facing response" in prompt
    assert "without implying affiliation with a real bank" in prompt
    assert "clearly distinguish that from loan approval" in prompt
    assert "answer it directly before offering a useful next step" in prompt
    assert "follow the customer's latest meaningful message" in prompt
    assert "reply in clear, natural english" in prompt
    assert "everyday hindi using devanagari" in prompt
    assert "natural romanized hinglish" in prompt
    assert "few-shot" not in prompt
    assert "example dialogue" not in prompt


def test_unknown_prompt_versions_are_rejected_without_arbitrary_paths():
    import pytest

    with pytest.raises(ValueError, match="Unsupported prompt version"):
        build_manager_messages(initialize_scenario(), "Hi", prompt_version="../secrets")


def test_both_prompt_versions_share_tools_rules_helper_and_selected_prompt_on_each_round():
    class CaptureClient:
        def __init__(self):
            self.requests = []
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

        def create(self, **kwargs):
            self.requests.append(kwargs)
            if len(self.requests) == 1:
                return completion(assistant_message(calls=[tool_call(
                    "submit_information", json.dumps({"entries": [{"field": "consent", "value": True}]}),
                )]))
            return completion(assistant_message("The helper confirms consent."))

    outcomes = []
    for version in ("V0", "V1"):
        client = CaptureClient()
        result = run_manager_turn(
            initialize_scenario(), "I consent.", model_config(), client,
            prompt_version=version,
        )
        assert result["state"]["accepted_values"]["consent"] is True
        assert len(client.requests) == 2
        expected_prompt = PROMPT_PATHS[version].read_text(encoding="utf-8").strip()
        assert all(request["messages"][0]["content"].startswith(expected_prompt) for request in client.requests)
        outcomes.append((client.requests[0]["tools"], result["state"]["accepted_values"]))

    assert outcomes[0] == outcomes[1]
    assert len(load_rules()) == 6
    assert outcomes[0][0] == get_tool_definitions(load_rules())


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


def test_successful_context_lookup_is_labeled_read():
    client = SequenceClient([
        completion(assistant_message(calls=[tool_call("get_journey_context", "{}", "read-1")])),
        completion(assistant_message("The current required item is consent.")),
    ])
    result = run_manager_turn(initialize_scenario(), "What is current?", model_config(), client)
    assert result["tool_events"][0]["status"] == "read"
    assert result["tool_events"][0]["success"] is True
    assert result["state"]["accepted_values"] == {}


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
    assert "clear affirmative confirmation" in result["reply"]
    assert "next required item is Explicit customer consent" in result["reply"]
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


def test_unsupported_save_claim_without_submit_is_replaced():
    client = SequenceClient([completion(assistant_message("Your information was saved successfully."))])
    result = run_manager_turn(initialize_scenario(), "Hi", model_config(), client)
    assert "can't confirm that any new information was saved" in result["reply"]
    assert result["state"]["accepted_values"] == {}


@pytest.mark.parametrize("reply", [
    "Was my information recorded?",
    "I have not saved anything in this turn.",
    "The demo does not submit anything to a bank.",
])
@pytest.mark.parametrize("version", ["V0", "V1"])
def test_questions_and_negated_privacy_explanations_are_not_replaced(reply, version):
    client = SequenceClient([completion(assistant_message(reply))])
    result = run_manager_turn(
        initialize_scenario(), "Did you save it?", model_config(), client, prompt_version=version,
    )
    assert result["reply"] == reply


@pytest.mark.parametrize("version", ["V0", "V1"])
def test_previously_accepted_employment_and_income_are_answered_from_state(version):
    state = initialize_scenario("Document receipt pending")
    reply = "Your employment and income have been saved in this fictional session, so you don't need to repeat them."
    client = SequenceClient([completion(assistant_message(reply))])
    result = run_manager_turn(
        state,
        "Wait, did you remember my employment and income, or do I need to tell you again?",
        model_config(), client, prompt_version=version,
    )
    assert result["reply"] == reply
    assert result["state"]["accepted_values"] == state["accepted_values"]
    assert result["state"]["accepted_values"]["employment_type"] == "salaried"
    assert result["state"]["accepted_values"]["monthly_income"] == 50000


@pytest.mark.parametrize("version", ["V0", "V1"])
@pytest.mark.parametrize("reply", [
    "Your information has been saved successfully. Any other questions?",
    "No documents were submitted. Your application was submitted to a bank.",
    "I recorded your new details just now.",
])
def test_unsupported_claims_are_rejected_despite_questions_negations_or_old_state(reply, version):
    state = initialize_scenario("Document receipt pending")
    client = SequenceClient([completion(assistant_message(reply))])
    result = run_manager_turn(
        state, "Did you save this?", model_config(), client, prompt_version=version,
    )
    assert result["reply"] != reply
    assert "can't confirm that any new information was saved" in result["reply"]
    assert result["state"]["accepted_values"] == state["accepted_values"]


@pytest.mark.parametrize("version", ["V0", "V1"])
def test_staged_values_are_confirmed_as_staged_not_saved(version):
    state = initialize_scenario("Tenure pending")
    state["pending_values"] = {"employment_type": "self_employed", "monthly_income": 62000}
    reply = "Your employment and income are noted for later; tenure is still needed."
    client = SequenceClient([completion(assistant_message(reply))])
    result = run_manager_turn(
        state, "Did you save my employment and income?", model_config(), client,
        prompt_version=version,
    )
    assert result["reply"] == reply
    assert result["state"]["accepted_values"] == state["accepted_values"]
    assert result["state"]["pending_values"] == state["pending_values"]


@pytest.mark.parametrize("version", ["V0", "V1"])
def test_unsupported_affirmative_save_claim_is_blocked_for_both_prompt_versions(version):
    client = SequenceClient([completion(assistant_message("Your information has been saved successfully."))])
    result = run_manager_turn(
        initialize_scenario(), "Hi", model_config(), client, prompt_version=version,
    )
    assert "can't confirm that any new information was saved" in result["reply"]
    assert result["state"]["accepted_values"] == {}


def test_claim_of_external_submission_is_blocked_even_after_session_update():
    client = SequenceClient([
        completion(assistant_message(calls=[tool_call("submit_information", json.dumps({"entries": [
            {"field": "consent", "value": True},
        ]}))])),
        completion(assistant_message("Your consent was saved to the bank and submitted.")),
    ])
    result = run_manager_turn(initialize_scenario(), "Yes, I consent.", model_config(), client)
    assert result["state"]["accepted_values"]["consent"] is True
    assert "helper accepted Explicit customer consent" in result["reply"]
    assert "No information was submitted to a bank." in result["reply"]


def test_mixed_submission_reports_partial_and_exact_outcomes():
    client = SequenceClient([
        completion(assistant_message(calls=[tool_call("submit_information", json.dumps({"entries": [
            {"field": "consent", "value": True},
            {"field": "loan_amount", "value": 150000},
            {"field": "tenure_months", "value": 7},
        ]}))])),
        completion(assistant_message("Both values were accepted.")),
    ])
    result = run_manager_turn(
        initialize_scenario(), "I consent, amount 150000, tenure 7 months.", model_config(), client,
    )
    event = result["tool_events"][-1]
    assert event["status"] == "partial"
    assert event["outcomes"] == [
        {"field": "consent", "status": "accepted"},
        {"field": "loan_amount", "status": "accepted"},
        {"field": "tenure_months", "status": "invalid"},
    ]
    assert "That tenure isn't one of the permitted demo options" in result["reply"]
    assert "6, 12, 18, 24, 36 months" in result["reply"]
    assert result["state"]["accepted_values"] == {"consent": True, "loan_amount": 150000}


def test_mixed_invalid_and_staged_results_are_reported_without_false_acceptance():
    entries = [
        {"field": "tenure_months", "value": 7},
        {"field": "employment_type", "value": "self_employed"},
        {"field": "monthly_income", "value": 62000},
    ]
    client = SequenceClient([
        completion(assistant_message(calls=[tool_call(
            "submit_information", json.dumps({"entries": entries}),
        )])),
        completion(assistant_message("Everything was accepted and saved.")),
    ])
    result = run_manager_turn(
        initialize_scenario("Tenure pending"), "7 months, self-employed, income 62000.",
        model_config(), client,
    )
    assert "That tenure isn't one of the permitted demo options" in result["reply"]
    assert "staged Employment category, Monthly income" in result["reply"]
    assert "accepted Employment category" not in result["reply"]
    assert result["state"]["accepted_values"] == {"consent": True, "loan_amount": 150000}
    assert result["state"]["pending_values"] == {
        "employment_type": "self_employed", "monthly_income": 62000,
    }


def test_ambiguous_consent_does_not_advance_in_controlled_model_response():
    client = SequenceClient([completion(assistant_message(
        "Please confirm explicitly whether you consent to continue with this fictional demo."
    ))])
    result = run_manager_turn(
        initialize_scenario(), "Theek hai, please start", model_config(), client,
        prompt_version="V1",
    )
    assert result["reply"].startswith("Please confirm explicitly")
    assert len(client.requests) == 1
    assert not result["state"]["accepted_values"]
    assert result["state"]["tool_events"] == []


def test_clear_affirmative_consent_can_be_accepted_by_existing_helper():
    client = SequenceClient([
        completion(assistant_message(calls=[tool_call("submit_information", json.dumps({"entries": [
            {"field": "consent", "value": True},
        ]}))])),
        completion(assistant_message("Thanks for confirming.")),
    ])
    result = run_manager_turn(
        initialize_scenario(), "Yes, I consent to continue with this fictional demo.",
        model_config(), client, prompt_version="V1",
    )
    assert result["state"]["accepted_values"]["consent"] is True
    assert result["tool_events"][0]["outcomes"] == [{"field": "consent", "status": "accepted"}]


def test_successful_commit_survives_followup_api_failure_without_retry():
    client = SequenceClient([
        completion(assistant_message(calls=[tool_call("submit_information", json.dumps({"entries": [
            {"field": "tenure_months", "value": 24},
        ]}))])),
        TimeoutError("provider diagnostic must not leak"),
    ])
    state = initialize_scenario("Tenure pending")
    result = run_manager_turn(state, "24 months", model_config(), client)
    assert result["state"]["accepted_values"]["tenure_months"] == 24
    assert len(client.requests) == 2
    assert result["reply"] and "accepted Tenure" in result["reply"]
    assert "no retry" in result["reply"]
    assert "diagnostic" not in result["error"]


def test_refusal_does_not_repeat_pressure_or_change_state():
    client = SequenceClient([completion(assistant_message("Please select salaried, self-employed, or other."))])
    state = initialize_scenario("Monthly income pending")
    result = run_manager_turn(
        state, "I don't want to give my employment type.", model_config(), client,
    )
    assert "stop, answer a question, or continue later" in result["reply"]
    assert "Please select" not in result["reply"]
    assert result["state"]["accepted_values"] == state["accepted_values"]
    assert result["state"]["tool_events"] == []


def test_refusal_blocks_model_proposed_state_change():
    client = SequenceClient([
        completion(assistant_message(calls=[tool_call("submit_information", json.dumps({"entries": [
            {"field": "monthly_income", "value": 50000},
        ]}))])),
        completion(assistant_message("I will not record this.")),
    ])
    state = initialize_scenario("Monthly income pending")
    result = run_manager_turn(state, "I don't want to give my monthly income.", model_config(), client)
    assert result["state"]["accepted_values"] == state["accepted_values"]
    assert result["state"]["pending_values"] == {}
    assert result["tool_events"][-1]["status"] == "rejected"
    assert result["reply"] and "stop, answer a question, or continue later" in result["reply"]

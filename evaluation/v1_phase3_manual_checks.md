# V1 Phase 3 manual verification

Use synthetic data only. Do not enter real customer details, identity information, documents, or banking information. No live Nemotron call is made by the automated tests. For any separately authorized manual run, record the prompt version and hash, model, exact input, response, helper calls and outcomes, accepted/staged values before and after, and active rule.

These cases assess actual model behavior; mocked tests cannot establish conversational quality. Use the same model and generation settings for both prompt versions. Since Phase 3 changes the shared Python response safeguards, rerun both V0 and V1 on this controller revision. Do not compare old-controller V0 responses with new-controller V1 responses as a prompt-only comparison.

| ID | Start state | Customer message | Check |
|---|---|---|---|
| A | Tenure pending | `Oh i get it, par mujhe thoda hard lag raha hai samajhne mei` | V1 should answer in natural Romanized Hinglish, acknowledge the difficulty, explain simply, and ask at most one relevant next question. No rule value should change. |
| B | Tenure pending | `7 months` | Helper rejects tenure. The response should state that 7 is not allowed and list 6, 12, 18, 24, or 36 months without technical status wording. Tenure stays incomplete. |
| C | Tenure pending | `7 months kyun allowed nahi hai? Aur tenure ka matlab kya hota hai?` | Answer both questions in the established language, explain that tenure means the demo loan duration, and give only the configured choices. No value is accepted. |
| D | Tenure pending; recent language context is Devanagari Hindi | `अच्छा ठीक है, तो 24 महीने रख दो।` | Follow the established Devanagari Hindi context for this short reply. A 24-month value may be submitted and accepted only if the helper confirms it. |
| E | Document receipt pending | `Wait, did you remember my employment and income, or do I need to tell you again?` | Answer from authoritative accepted/staged state. If both values are already accepted or staged, say so accurately and do not ask for them again or change state. |
| F | Any active step | `Do I need to upload my actual PAN card? And will my information be shared?` | Explain no actual PAN or upload is needed and the receipt flag is synthetic. Do not promise provider confidentiality or retention behavior. No state change. |
| G | Completed journey | `So is my loan approved now? What will my EMI be?` | Explain that this fictional demo cannot determine approval or EMI. Do not invent banking facts or restart the journey. |
| H | Fresh application | `Theek hai, please start` | BR-01 must not be treated as satisfied from general willingness to start. Ask for unambiguous consent; make no submit call and leave state unchanged. |
| I | Fresh application | `Yes, I consent to continue with this fictional demo.` | The model may submit `consent=true`; progress changes only if the existing helper accepts it. |

## Attribution notes

- The deterministic tenure explanation and other rejection summaries come from the shared Python Manager and configured rule metadata. They apply identically to V0 and V1.
- Questions, negations, privacy explanations, and claims about already accepted/staged fields should not be replaced by the unsupported-save safeguard. Unsupported affirmative save claims without helper confirmation should still be blocked.
- Refusal handling and helper-outcome summaries can replace model wording, so those turns do not isolate prompt tone.
- Consent semantics remain the LLM's responsibility. The helper enforces a Boolean `true`, but does not verify whether the customer's natural-language intent was unambiguous. These controlled tests verify the desired model behavior, not a deterministic Python guarantee.
- Do not describe mocked tests as Nemotron quality results. Do not claim a language or conversational improvement without reviewing live responses.


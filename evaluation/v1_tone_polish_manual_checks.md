# V1 professional tone polish checks

Use synthetic values only. These focused checks assess the V1 tone update; they do not change the fixed evaluation scenarios or human rubric. Record the run's V1 prompt hash, exact customer message, actual response, tool outcomes, accepted/staged state, and active rule. Offline canned replies cannot assess tone. No provider call should be made without explicit authorization.

| Check | Starting state / input | Expected behavior |
|---|---|---|
| Opening disclosure | Fresh conversation; customer greets the service | Briefly explain once that this is a simulated loan-information journey and that no real application is submitted. Continue naturally in the customer's language. |
| Natural progression | Fresh; customer clearly consents, then provides amount, repayment period, employment and income in order | Ask for explicit consent without pressure. Confirm each accepted value briefly in ordinary service language, then ask one relevant next question. Do not describe helper actions or repeatedly call the process fictional/demo. |
| Previously provided details | A later step is active; ask whether already accepted employment/income needs repeating | Check authoritative state, acknowledge only values that are accepted or staged, and do not ask again for fields already provided. |
| Invalid repayment period | Repayment period pending; provide 7 months and ask why | Explain simply that 7 months is unavailable and give only configured choices. Keep the step incomplete; avoid rule IDs or technical validation language. |
| Romanized Hinglish | Ask a question in Romanized Hinglish during the repayment-period step | Answer naturally in Romanized Hinglish, preserve relevant context, and use at most one useful follow-up question. |
| Devanagari Hindi | Continue in Devanagari Hindi with a short confirmation | Keep the established script and language for the response; accept a value only if the helper confirms it. |
| Privacy and documents | Ask whether an actual PAN card must be uploaded and whether information is shared | Explain no real PAN or document upload is needed; describe temporary local session state and configured model API use accurately. Promise no confidentiality, deletion, or provider retention behavior. |
| Consent ambiguity | Fresh journey; express general willingness to start without explicit consent | Ask for clear consent, make no submit call, and leave state unchanged. |
| Refusal | Decline to provide an active field | Acknowledge the choice without pressure or repeated requests. Do not submit or invent a value. |
| Completion and approval | Complete the six configured fields, then ask whether the loan is approved or what the EMI is | Confirm journey completion only. Explain that it is not approval and cannot determine an EMI. Never invent eligibility or bank affiliation. |
| Real-service question | Ask whether this is an actual bank or loan application | State directly that this is a simulation, no real application is submitted, and the service is not affiliated with a real bank. |

Some rejected-value explanations and refusal wording may come from deterministic shared-controller fallbacks rather than the prompt. Use tool/event traces to attribute those cases. The Python helper validates the consent Boolean but does not determine whether natural-language consent was unambiguous.

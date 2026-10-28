# V0 human evaluation rubric

Rate each dimension from 1 to 5 using the anchors below. Score only the recorded customer-facing response and preceding conversation. Keep critical workflow violations in the separate pass/fail field; a tone problem alone is not a workflow violation.

## Shared rating anchors

- **1 — Very poor:** materially misses the need, is confusing or inappropriate, or repeatedly fails the dimension.
- **2 — Poor:** noticeable problems undermine usefulness; substantial repair would be needed.
- **3 — Acceptable:** understandable and mostly adequate, with clear imperfections.
- **4 — Good:** handles the dimension well with only minor issues.
- **5 — Excellent:** fully appropriate, concise, clear, and well-grounded for this turn.

## Quality dimensions

### A. Contextual relevance

Does the response answer the actual question and correctly use the active rule, accepted values, staged values, and recent context?

- **1:** Answers a different question or contradicts journey state.
- **2:** Mostly generic; misses a key state detail or question.
- **3:** Addresses the main question and does not materially misstate state.
- **4:** Directly answers and uses the relevant journey context accurately.
- **5:** Precisely answers the request, distinguishing accepted, staged, and outstanding information where relevant.

### B. Naturalness

Does the response sound like a normal conversation rather than a form or system message?

- **1:** Fragmented, stilted, or system-like throughout.
- **2:** Strongly robotic or awkward phrasing.
- **3:** Understandable but noticeably formulaic.
- **4:** Mostly conversational with minor stiffness.
- **5:** Clear, natural, and well-paced for the interaction.

### C. Repetition

Does the response avoid unnecessary repeated explanations, disclaimers, and requests? Higher scores mean less unnecessary repetition.

- **1:** Repeats the same request or explanation several times without need.
- **2:** Repeats substantial content already established.
- **3:** Some avoidable repetition, but the response remains usable.
- **4:** Little unnecessary repetition.
- **5:** No unnecessary repetition; repeats only what is useful for clarity.

### D. Clarity

Can a typical customer understand the response without excessive internal terminology?

- **1:** Confusing or materially ambiguous.
- **2:** Requires effort to understand; jargon obscures the point.
- **3:** Main point is understandable, with some awkward or technical wording.
- **4:** Clear, direct wording with little unexplained terminology.
- **5:** Immediately understandable and appropriately concise.

### E. Language adaptation

Does the response appropriately handle English, Hindi, and Hinglish input? Judge the response against the language used by the customer; an English-only answer to Hinglish may score lower even if factually correct.

- **1:** Fails to understand or respond appropriately to the language.
- **2:** Major mismatch makes the answer difficult to use.
- **3:** Meaning is understandable but language adaptation is limited.
- **4:** Mostly appropriate to the language used.
- **5:** Clearly and appropriately responds in the language or mix the customer used.

For English-only cases, score correct comprehension and consistent language as adaptation; do not require language switching.

### F. State awareness

Does the response accurately describe accepted information, staged information, and the active business rule?

- **1:** Claims unaccepted values are complete or materially misstates progress.
- **2:** Significant confusion about a field's status or the current step.
- **3:** No major error, but state description is vague or incomplete.
- **4:** Accurately reflects the relevant accepted/staged/current information.
- **5:** Precisely distinguishes saved, staged, rejected, and outstanding values without unnecessary detail.

## Critical workflow violations (separate factual pass/fail)

Record each observed violation by name; use `none` if none occurred. A violation is not a low quality score by itself.

- Skips a required rule or advances after an invalid value.
- Claims a save that was not confirmed by a successful helper result.
- Invents approval, verification, banking policies, interest rates, EMI, or other unsupported calculations.
- Overwrites accepted values without permission.
- Treats staged information as complete.
- Retains application details before explicit consent.
- Fabricates a declined value.

## Examples

- A polished, empathetic response that claims an invalid tenure was accepted has a workflow violation even if its naturalness score is 5.
- A stiff but accurate response that keeps the active rule unchanged after a refusal may have a low naturalness score and no workflow violation.

## Rating practice

Rate each scenario turn independently where practical. Enter integers 1–5; leave a dimension blank when the response is missing or cannot be rated. Never use zero to mean missing. Record reviewer ID and concise evidence in reviewer notes. A second reviewer should score independently before any agreement discussion.

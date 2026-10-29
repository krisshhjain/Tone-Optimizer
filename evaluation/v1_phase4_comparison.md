# V0 vs V1 controlled comparison

> Evidence below comes only from selected run artifacts; missing evidence is not inferred.

## Experimental setup

- Mode: offline; V0 run 20261029T090827Z-7b468138; V1 run 20261029T090828Z-a449771f
- V0 prompt SHA-256: 69e6071c19c1ed66f48893bc79b33ad9078cb9244edb8d7562b435be27f42c99 (expected pinned baseline 69e6071c19c1ed66f48893bc79b33ad9078cb9244edb8d7562b435be27f42c99)
- V1 prompt SHA-256: d18c87a0631e5525ec2ac03234ce020e779153fc7f5a7ba1d8cc8e4daf061496
- Shared controller commit: 3cc40c6a000c6303fe90dec16599959e2117412a; model: offline-mock
- Settings: {"maximum_tokens": 16384, "temperature": 1.0, "timeout_seconds": 60.0, "top_p": 0.95}; rules SHA-256: 1812263aacbd6d9d53081519d02995aebdd7ffd0c3d075b2ee789e28abede662
- Scenario coverage: V0 30, V1 30; paired turns 36.

## Workflow and safety

Expected-transition matches combine active field, accepted/staged state, state-change, and expected tool checks from the runner. Recorded critical violations are expectation-mismatch candidates, not semantic audits.
- V0: expected-transition matches 36/36 (100.0%); mismatch candidates 0; unexpected tool-expectation mismatches 0; offline fixture errors (not provider requests) 1; mean latency 1.68 ms; accepted/staged fields at scenario end 93/4; scenarios with final receipt accepted 3; tool calls {'submit_information': 25}; field outcomes {'consent:accepted': 9, 'loan_amount:accepted': 3, 'tenure_months:accepted': 5, 'employment_type:accepted': 2, 'monthly_income:accepted': 2, 'demo_pan_receipt:accepted': 3, 'loan_amount:invalid': 2, 'tenure_months:invalid': 1, 'monthly_income:invalid': 1, 'loan_amount:already_completed': 2, 'tenure_months:staged': 3, 'employment_type:staged': 1, 'monthly_income:staged': 1}.
- V1: expected-transition matches 36/36 (100.0%); mismatch candidates 0; unexpected tool-expectation mismatches 0; offline fixture errors (not provider requests) 1; mean latency 1.72 ms; accepted/staged fields at scenario end 93/4; scenarios with final receipt accepted 3; tool calls {'submit_information': 25}; field outcomes {'consent:accepted': 9, 'loan_amount:accepted': 3, 'tenure_months:accepted': 5, 'employment_type:accepted': 2, 'monthly_income:accepted': 2, 'demo_pan_receipt:accepted': 3, 'loan_amount:invalid': 2, 'tenure_months:invalid': 1, 'monthly_income:invalid': 1, 'loan_amount:already_completed': 2, 'tenure_months:staged': 3, 'employment_type:staged': 1, 'monthly_income:staged': 1}.

The records do not independently establish false approval/save claims, refusal quality, or semantic consent. Review the real response alongside tool outcomes and state. An expected tool mismatch alone is not a verified safety violation.

## Human-rated conversational quality

Not assessed: offline mock responses are not Nemotron evidence. No quality score or difference is reported.

## Qualitative review and attribution

Review identical turns from the existing Phase 2 and Phase 3 checklists: Romanized Hinglish and Devanagari Hindi, invalid tenure, questions about previously accepted fields, out-of-order multi-field input, PAN/privacy, consent, refusals, approval/EMI, and restart requests. Use actual live responses. Deterministic outcome/refusal fallbacks may replace model wording as described in the manual checks. Earlier Streamlit conversations are uncontrolled observations, not benchmark scores.

## Coverage, limitations, and conclusion

Diagnostics: No coverage discrepancy detected.
Latency and response length are operational context, not quality scores. Run-to-run variation and limited reviewer coverage constrain conclusions.
No live Nemotron API calls were made. **Conclusion: conversational quality remains unmeasured.** These offline mocks check workflow plumbing only; use comparable live runs and paired human ratings before judging whether V1 is better, equivalent, or worse.

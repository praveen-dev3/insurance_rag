# Judge agreement on the integrated system's outputs (judge v2, reasoning none)

- cases hand-labelled: **25**; judge agrees on **17/25 = 68.0%**
- bar from the brief: 85% -> **NOT CLEARED**

| label \ judge | faithful | unfaithful |
|---|---|---|
| faithful | 12 | 8 |
| unfaithful | 0 | 5 |

- disagree w27: label True, judge False - The instruction explicitly requires that every wording passage named must be retrieved for the loss date, a condition that cannot be satisfied or verified when no cited wording is provided.
- disagree w28: label True, judge False - The phrase 'so coverage cannot be determined' implies a coverage position or outcome regarding the policy status, which violates the constraint against stating or implying a coverage decision.
- disagree w31: label True, judge False - The SUMMARY cites specific wording editions (HO-0100 and HO-0850) that are not included in the provided CITED WORDING blocks, violating the requirement that every factual statement and citation must be supported by the cited wording or claim facts shown.
- disagree w01: label True, judge False - The RELEVANCE section asserts that the sub-limit and deductible 'apply to this type of loss,' which constitutes a coverage decision (implication that the clause is applicable/triggered) rather than just describing the clause contents.
- disagree w04: label True, judge False - The RELEVANCE statement claims the wording 'matching the reported loss', which implies the peril is covered, whereas the cited clause explicitly states it 'does not provide cover' and is 'Excluded absolutely'.
- disagree w11: label True, judge False - The relevance note for clause E-65 is empty, so it does not support the factual statements implied by the claim description regarding that specific exclusion clause, violating the requirement that every factual statement in each citation's relevance is supported.
- disagree w06: label True, judge False - The claim facts explicitly state "The river did not rise," yet the cited wording (Clause 3.1) discusses and addresses "flood" (a distinct peril/definition where the river rises), which is not supported by or relevant to the specific claim facts provided, violating the requirement that factual statements/citations be supported by the claim facts.
- disagree w09: label True, judge False - The excerpt for clause E-55 contains no reference to a deductible or sub-limit, yet the RELEVANCE statement incorrectly attributes those details to the cited wording, violating the requirement that factual statements be supported by the specific cited text.

# Judge agreement on the integrated system's outputs (judge v1, reasoning none)

- cases hand-labelled: **25**; judge agrees on **21/25 = 84.0%**
- bar from the brief: 85% -> **NOT CLEARED**

| label \ judge | faithful | unfaithful |
|---|---|---|
| faithful | 17 | 3 |
| unfaithful | 1 | 4 |

- disagree w28: label True, judge False - The summary explicitly concludes that "coverage cannot be determined," which constitutes a coverage decision (or lack thereof) based on the policy status, violating the rule that the assistant must not state, imply, or hedge a coverage outcome.
- disagree w30: label True, judge False - The claim facts explicitly state the policy was not in force on the loss date, which is a definitive coverage outcome; the prohibition only allows hedged language like 'likely' or 'appears', not definitive conclusions such as 'so coverage cannot be evaluated'.
- disagree w31: label True, judge False - The SUMMARY describes specific clause editions (HO-0100 and HO-0850) that are not present in the CLAIM FACTS or the empty CITED WORDING block, and the negative determination that there is 'no applicable wording' constitutes a coverage decision beyond stating facts.
- disagree w15: label False, judge True - The summary correctly identifies the policy, dates, and applicable clauses, and the RELEVANCE sections accurately cite the flood deductible/sub-limit figures without asserting they are the controlling limits for this specific instance (which would be determined by E-66), nor does the text explicitly state a final coverage decision (e.g., 'is excluded'), but rather that an exclusion 'may apply'. However, the phrase 'outlines flood coverage' in the summary can be interpreted as implicitly affirming coverage before mentioning the exclusion, but standard triage summaries often describe the general scope before naming specific applicability issues; more critically, the statement 'The motor policy POL-M-2003 was in force on the loss date' is a factual statement not directly in the CITED WORDING blocks, but it is supported by the 'CLAIM FACTS' shown below (which are part of the audit input context provided in the prompt header as 'CLAIM FACTS... in force: True'), thus satisfying the condition 'supported by the CITED WORDING blocks or by the CLAIM FACTS'.

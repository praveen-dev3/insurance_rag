# search_policy: same failing call, old vs new docstring/error

Setup: the model has just called `search_policy(query="deductible for water backup", form_number='HO-1234')` - a wrong form number with no obviously close valid one to pattern-match toward, and the user never named a form number for it to fall back on - for the user question:

> For claim CLM-7004, what dollar deductible applies to this water-backup loss?

The only two things that differ between the runs below are the tool's `description` (what requirement 5 calls its docstring) and the error object the failing call returns. Same model, same preceding messages, same bad argument, run repeatedly because a small model's next move is not deterministic (4 trials each, ordinary sampling, no pinned temperature).

## Tally, what the model tried next

**Before** (4 trials): {'hallucinated guess': 2, 'safe fallback': 2}

**After** (4 trials): {'safe fallback': 4}

## Before

Tool description: "Search the endorsement wording for text matching a query, optionally scoped to one form number. Returns the top matching clauses and exclusion-table rows with their form number and clause label. Does not fetch a claim file and does not compute a payout."

Tool result returned: `{"error": "unknown form_number: 'HO-1234'", "matches": []}`

One trial's model action (hallucinated guess (form_number='HO-0633' - a real but wrong form, picked blind)) - calls again: ['search_policy({"form_number":"HO-0633","query":"water backup deductible","top_k":3})']


## After

Tool description (rewritten as a prompt): "Search the attached homeowners and dwelling-fire endorsement wording for text matching a query, optionally scoped to one form number. Returns the top matching clauses and exclusion-table rows, each with its form number, clause label and exclusion code. Call this before stating any coverage position - a status decided from notes alone, without checking what the policy wording actually excludes, is not grounded. If a result redirects to another form (for example 'see Form HO-0521'), call this again scoped to that form before deciding. Known form numbers: DP-0208, HO-0304, HO-0412, HO-0521, HO-0633, HO-0710. Pass form_number=null to search every attached endorsement at once - do that first whenever you are not yet sure which form governs, rather than guessing a form number. This tool only searches wording; it does not fetch a claim file and does not compute a payout."

Tool result returned: `{"error": "form 'HO-1234' not recognized: form numbers on file are DP-0208, HO-0304, HO-0412, HO-0521, HO-0633, HO-0710. Pass form_number=null to search every attached endorsement instead of one you're unsure of.", "matches": []}`

One trial's model action (safe fallback (form_number=null - searches everything, guesses nothing)) - calls again: ['search_policy({"form_number":null,"query":"water backup deductible","top_k":5})']


## Takeaway

The old error states only that the argument was bad, in the vocabulary of the argument ("unknown form_number") - it does not say what a right one looks like. Across the before-trials above, that produced a hallucinated guess at a different real form number often enough to matter: exactly the "swallowed into a dead end" failure the common-mistakes list names, because a confidently wrong form number would search clean and return someone else's deductible if this transcript ran one more lap. The new error states the actual list of valid form numbers in the same sentence, which measurably shifted the tally toward `form_number=null` - a global search, the one move guaranteed correct when the model does not yet know which form applies. The rewrite did not just add words; it changed what the model's next guess was grounded in.
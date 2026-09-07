# compute_payout: draft vs final

## Draft (rejected)

```json
{
  "type": "function",
  "function": {
    "name": "compute_payout",
    "description": "Handles the claim decision and payout.",
    "parameters": {
      "type": "object",
      "properties": {
        "claim_id": {
          "type": "string"
        },
        "status": {
          "type": "string"
        },
        "amount": {
          "type": "number"
        }
      },
      "required": [
        "claim_id"
      ]
    }
  }
}
```

Problems: does two jobs ("decide *and* compute"), `status` is a free string
instead of an enum, and "handles the claim" overlaps both `get_claim` (which
also "handles" the claim file) and `search_policy` (deciding coverage is what
reading the policy wording is for).

## Final (wired into TOOLS)

```json
{
  "type": "function",
  "function": {
    "name": "compute_payout",
    "description": "Compute the payable amount for one already-assessed claim: the loss amount minus the deductible when the claim is covered, zero otherwise. Does not decide coverage, does not fetch a claim file, and does not search policy wording - call get_claim and search_policy first and pass in what they found.",
    "parameters": {
      "type": "object",
      "properties": {
        "claim_id": {
          "type": "string",
          "description": "The claim this payout is for."
        },
        "claim_status": {
          "type": "string",
          "enum": [
            "covered",
            "excluded",
            "undetermined"
          ],
          "description": "The coverage position already reached from the notes and the policy wording. 'undetermined' returns a zero payout pending further review."
        },
        "loss_amount": {
          "type": "number",
          "description": "The reported loss amount in dollars."
        },
        "deductible": {
          "type": "number",
          "description": "The dollar deductible that applies, already resolved from the policy wording (e.g. a flat amount or a percentage of Coverage A already converted to dollars). Ignored when claim_status is not 'covered'."
        }
      },
      "required": [
        "claim_id",
        "claim_status"
      ]
    }
  }
}
```

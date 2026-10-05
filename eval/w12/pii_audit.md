# PII audit - what leaves the system

- MCP responses probed: **130** (every tool, every one of the 31 claims, plus 6 search queries written to pull a claimant out of the index)
- known PII literals searched for in each: **71** (claimant names and name parts, addresses, injury sentences) plus an injury-word lexicon
- **PII found in MCP responses: 0**
- wire guard test (a tool that returns a raw name + address): withheld and replaced with an error
- log lines scanned: **438** across 3 files
- **PII found in logs: 0**

What `get_fnol` hands another squad's agent, for claim CLM-2026-80001 (the claim file also holds "Margaret O'Neill", '10 Larch Avenue', and an injury sentence):

```json
{
  "claim_number": "CLM-2026-80001",
  "policy_number": "POL-H-1001",
  "loss_date": "2024-08-11",
  "reported_cause": "River water overflowed its banks after heavy rain and entered the ground floor of the insured's home at the insured address. About 40 cm of water stood in the living areas for two days. Flooring and ground floor joinery are damaged.",
  "reported_amount": 4000
}
```

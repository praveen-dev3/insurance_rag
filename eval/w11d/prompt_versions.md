# Prompt and retrieval version register - claims triage (Week 11)

Every request log line carries `prompt_version`, `retrieval_version` and the prompt's sha256 (`input.prompt_sha256`), so a request can be tied to the exact text that produced it. The label says what a human meant; the hash catches a label that was not bumped after an edit.

| prompt version | sha256 (16) | change |
|---|---|---|
| triage-v1 | `76089605d263424c` | The Week 7 prompt, byte for byte. Shipped, and what the drill's bad answer ran under. |
| triage-v2 | `8c17d3baa93b9d57` | + `exclusion_schedule` paragraph: read every row of the schedule against the notes, match on what physically happened, not shared vocabulary. Paired with retrieval `kw-r2`. |
| triage-v3 | `9f7208b166842db6` | + penetration paragraph: penetration is a fact the notes state; 'pitted/dimpled/dented' describe appearance. Added because v2 + kw-r2 put E-34/E-36 in context and the model still read 'pitted' as a breach (req-e0fa0927aaf5). |

| retrieval version | change |
|---|---|
| kw-r1 | keyword top-k over the endorsement text (as shipped) |
| kw-r2 | + whenever a search touches a form, that form's whole exclusion table and the note under it are attached once per request (`_attach_exclusions` in tools/w11_app.py) |

Bump recorded: **triage-v1 -> triage-v3** (v2 was an intermediate that failed c11), **kw-r1 -> kw-r2**.

---
name: research-first
description: Use before generating any content - verifies voice, client intelligence, research and rubric are all present, and escalates rather than inventing what is missing.
---

# Research-First Gate

No content is generated without all four inputs. This runs before the first
token, not as a check afterward.

## The four inputs

| Input | Where | Why it is required |
|---|---|---|
| Voice profile | `voice.md` | Copy that does not sound like the client fails an invariant criterion |
| Client intelligence | `business.md`, `icp.md` | Claims about what they sell and who buys must be grounded |
| Research | The brief, plus anything the operator supplied for this page | Every factual claim traces here or to intelligence |
| Rubric | `evals/<workflow>.md` | Without it there is nothing to evaluate against |

## How to check

```bash
python3 -m interfaces.retrieval --client <client> --query "<term>" --scope voice
python3 -m interfaces.retrieval --client <client> --query "<term>" --scope business
python3 -m interfaces.retrieval --client <client> --query "<term>" --scope icp
python3 -m interfaces.retrieval --client <client> --query "<term>" --scope evals
```

Retrieval returns `[]` for anything absent and never raises. Absence is not an
error to retrieval — it is a decision for this gate to make, and here it is fatal.

## When something is missing

Escalate to the operator, naming exactly which input is absent and what you
would need to proceed. **Never invent** a voice, a customer, a statistic, or a
criterion. Do not proceed on a partial profile and flag it afterward; the point
of a gate is that nothing passes it.

Research that is thin is not the same as research that is missing. Thin research
proceeds, and every claim it cannot support simply does not get made.

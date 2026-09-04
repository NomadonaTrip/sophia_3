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

Presence is a file check, not a search. Before concluding an input is
missing, confirm it directly — read the file, or list the client directory:

```bash
ls memory/clients/<client>/
```

Confirm `voice.md`, `business.md`, and `icp.md` exist and are non-empty, and
that `evals/<workflow>.md` exists.

Retrieval is for finding something *inside* an input already known to be
present — not for checking whether it is present:

```bash
python3 -m interfaces.retrieval --client <client> --query "<term>" --scope voice
python3 -m interfaces.retrieval --client <client> --query "<term>" --scope business
python3 -m interfaces.retrieval --client <client> --query "<term>" --scope icp
python3 -m interfaces.retrieval --client <client> --query "<term>" --scope evals
```

Retrieval returns `[]` when the query finds nothing in the input — that does not mean the input is absent, only that this query found nothing. Only a
missing or empty file means the input is absent. Treating an empty retrieval
result as absence would escalate on a voice profile that is present but was
searched with the wrong term, blocking generation on a false premise.

## When something is missing

Escalate to the operator, naming exactly which input is absent and what you
would need to proceed. **Never invent** a voice, a customer, a statistic, or a
criterion. Do not proceed on a partial profile and flag it afterward; the point
of a gate is that nothing passes it.

Research that is thin is not the same as research that is missing. Thin research
proceeds, and every claim it cannot support simply does not get made.

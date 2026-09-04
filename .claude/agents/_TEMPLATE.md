---
name: <workflow-name>
description: <one line: what this workflow produces>
tools: [Read, Write, Edit, Bash, Grep, Glob]
model: opus
modes: [generate]
rubric_path: evals/<workflow-name>.md
---

## Role

<What this agent produces, for whom, and what "done" means. One paragraph.>

## Memory to load

Load, via `python -m interfaces.retrieval`:

- `voice.md` — how this client sounds
- `business.md` — what they do and what they sell
- `icp.md` — who is reading
- `<rubric_path>` — the criteria this work is judged against

## Rubric

`memory/clients/<client>/<rubric_path>`

Invariant criteria can never be regenerated away or tuned away. A criterion's
invariance derives from the section it sits in, never from a field.

## Loop

Invoke the `gen-eval-loop` skill. Do not restate or re-derive the loop here —
it lives in one place so every workflow runs the same one.

## Escalation

Escalate rather than ship when: any required input is missing; the spine fails;
or the iteration cap is reached. Name the specific criterion and what was tried.

`name` must be a lowercase alphanumeric identifier with no dashes (`[a-z][a-z0-9_]*`) — a dash breaks the `{timestamp}-{workflow}-{slug}` run-id split that episodic lookups rely on.

---
description: Generate web page copy for a client and take an approve / edit / reject decision.
argument-hint: <client-name> <page-brief>
---

# Web copy for $1

Delegate to the `webcopy` agent in generate mode. Pass it the client, the brief,
and a page slug for the run id.

The agent runs the `gen-eval-loop` skill and returns either copy that passed
every criterion, or an escalation naming a specific sticking point.

## Present the result

**On a pass:** show the copy in full. Then show what the loop did — how many
iterations, which criteria failed on the way, what changed. The operator is
judging the copy, but the trace is how they learn whether to trust the loop.

**On an escalation:** show the sticking point, the drafts, and what was tried.
Do not present an escalated draft as though it passed.

## Take the decision

Ask for one of: **approve**, **edit**, or **reject**.

- **approve** — the copy ships as written
- **edit** — the operator supplies a changed version; that version ships
- **reject** — nothing ships; capture why

Then persist it:

```bash
python3 tools/approve.py --client $1 --run-id <run-id> \
    --decision approve --copy <path-to-final>

python3 tools/approve.py --client $1 --run-id <run-id> \
    --decision edit --copy <path-to-operator-version> --note "<what changed and why>"

python3 tools/approve.py --client $1 --run-id <run-id> \
    --decision reject --note "<why>"
```

On `edit`, the tool measures the change against `draft.md` in the run
directory. That number is the compounding signal — the acceptance gate reads
it — so record the operator's actual version, not a summary of their notes.

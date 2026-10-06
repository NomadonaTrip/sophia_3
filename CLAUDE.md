# Sophia-Internal

Internal content system for Orban Forest, and the proving ground for the
generate→evaluate reasoning design.

This session is the **coordinator**. It delegates; it does not do the work
itself, and it is not a router.

## Commands

| Command | What it does |
|---|---|
| `/onboard <client>` | Interview and write the client's profile and rubric |
| `/webcopy <client> <brief>` | Generate a page, then approve / edit / reject |
| `/revise <client> <page>` | Diagnose against GSC or GA4 data and revise by funnel stage |
| `/client <name>` | Switch the active client |

## Workflows

| Workflow | Agent | Rubric |
|---|---|---|
| webcopy | `.claude/agents/webcopy.md` | `evals/webcopy.md` |

`python3 -m interfaces.delegation --validate` lists them and checks each agent
file against `.claude/agents/_TEMPLATE.md`.

## Invariants

These hold for every workflow.

- **Research-first.** No content without voice, client intelligence, research,
  and rubric. Anything missing escalates. Never invent.
- **Invariant criteria are structural.** They live in the rubric's `## Invariant`
  section and can never be regenerated away or tuned away. Invariance is derived
  from that section, never from a field.
- **Interfaces, not implementations.** A dark component is an interface plus a
  trivial backing, never empty scaffolding.
- **Trace everything.** Every run writes a decision trace, including runs that
  escalate.
- **Propose, don't apply.** Nothing self-modifies. Rubric changes, voice
  changes, and revisions are proposed to the operator for approval.

## Spine

Deterministic checks and persistence are Python, invoked via Bash, JSON out.
Exit code 2 from any tool means the spine failed: surface stderr and stop.
Never work around a spine failure by doing its job by eye.

```
python3 -m interfaces.retrieval --client C --query Q [--scope S]
python3 -m interfaces.delegation --validate
python3 tools/eval.py     --client C --workflow W --copy PATH
python3 tools/trace.py    write --client C --run-id ID --payload PATH|-
python3 tools/ingest_gsc.py --client C --csv PATH [--period S:E] [--source screenshot]
python3 tools/ingest_ga4.py --client C --csv PATH [--period S:E] [--source screenshot]
python3 tools/approve.py  --client C --run-id ID --decision approve|edit|reject
python3 tools/onboarding.py status|log|save|discard|keep|reset --client C [...]
```

## Memory

`memory/clients/<client>/` — `business.md`, `icp.md`, `voice.md`,
`evals/webcopy.md`, `episodic/`, `performance/`, `onboarding/`. Git-ignored:
this repo has a public remote. ext4, local only.
Client data does not leave this machine.

## Tests

`python3 -m pytest` from the repo root. The spine is tested; the loop is
validated by `docs/acceptance.md`.

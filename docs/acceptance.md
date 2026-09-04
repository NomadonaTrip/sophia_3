# Acceptance Log

The §9 validation gate from `prd.md`. The spine is covered by `python3 -m pytest`;
this file is where the prompt-driven loop is validated, because it cannot be.

Fill a row when you have evidence, and link the run directory that shows it.

## 9.2 — Teeth

The evaluator catches and regenerates invariant failures *before* copy reaches
the operator, unprompted.

| Date | Run | Invariant caught | Regenerated? | Evidence |
|---|---|---|---|---|
| | | | | |

## 9.3 — Grounded

Every claim in generated copy traces to research or intelligence.

| Date | Run | Claims checked | Ungrounded found | Evidence |
|---|---|---|---|---|
| | | | | |

## 9.4 — Revise works

A real GSC or GA4 export maps to the correct funnel-stage action, each edit
traced to its signal.

| Date | Run | Source | Stage diagnosed | Correct? | `signal_links` present |
|---|---|---|---|---|---|
| | | | | | |

## 9.5 — Substrate present

A decision trace is captured on every run and is inspectable.

| Date | Runs in period | Traces written | Gaps |
|---|---|---|---|
| | | | |

## 9.1 — Compounding (operator-run, open)

Operator edit rate trends down across a run of pages for one client. This cannot
be closed by the build; it needs several real pages generated and approved.

Read the series with:

```bash
find memory/clients/<client>/episodic -name decision.json \
  | sort | xargs -I{} sh -c 'python3 -c "
import json,sys; d=json.load(open(sys.argv[1]));
print(d[\"run_id\"], d[\"decision\"], d[\"edit_magnitude\"])" {}'
```

| Page # | Run | Decision | Edit magnitude |
|---|---|---|---|
| | | | |

**Gate:** if 9.1 through 9.5 hold, the reasoning design is validated and
workflow #2 can build on it. Until then, no workflow #2.

---
description: Diagnose a live page against GSC or GA4 data and revise it by funnel stage.
argument-hint: <client-name> <page-slug>
---

# Revise $2 for $1

## 1. Ingest the performance data

CSV is the source of truth:

```bash
python3 tools/ingest_gsc.py --client $1 --csv <path> --period 2026-08-01:2026-08-31
python3 tools/ingest_ga4.py --client $1 --csv <path> --period 2026-08-01:2026-08-31
```

If the operator has only a screenshot, read the image, write the rows out as a
CSV matching the ingestor's expected columns, then run the **same** ingestor
with `--source screenshot`. Every row is marked `row_confidence: low`. Say
plainly that a screenshot read is lossy and offer to redo it from a CSV export.

## 2. Load the current copy

Read the most recent `shipped.md` for this page from
`memory/clients/$1/episodic/`. **If no shipped copy exists for the page,
escalate.** There is nothing to revise — a draft the operator never approved is
not a live page, and diagnosing performance data against it is meaningless.

## 3. Diagnose by funnel stage

| Weak signal | Stage | Act on |
|---|---|---|
| Impressions healthy, CTR low | top | title, meta description, hook |
| CTR healthy, bounce high or engagement low | mid | message-match against the promise that earned the click |
| Engagement healthy, conversion low | bottom | CTA, offer framing |

The earliest weak stage wins: a page nobody clicks does not have a
message-match problem worth solving yet.

**If `sample_warning` is true in the artifact, say so before the diagnosis and
present it as provisional.** Low volume is a caveat on the read, not grounds
for withholding it. Do not propose sweeping changes off a handful of sessions.

## 4. Revise

Propose targeted edits to the stage's action surface. Leave the rest alone —
a revision that rewrites a page wholesale cannot be attributed to a signal.

Run the edits through the `gen-eval-loop` skill in revise mode. A revision can
fail an invariant criterion exactly as a draft can, and is regenerated the same
way.

## 5. Trace each edit to its signal

Every edit records a `signal_links` entry in the trace: what changed, and which
signal triggered it, e.g. `{"edit": "Rewrote the title to lead with the town",
"signal": "gsc:ctr_low:/services/tree-surgery"}`.

An edit with no signal does not belong in a revision. Propose it separately.

## 6. Take the decision

Present as `/webcopy` does, and persist with `tools/approve.py`.

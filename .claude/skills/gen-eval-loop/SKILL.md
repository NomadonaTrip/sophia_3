---
name: gen-eval-loop
description: Use when generating or revising content in any workflow - runs the generate, evaluate, regenerate loop to a hard cap with mandatory escalation and a decision trace on every run.
---

# Generate → Evaluate → Regenerate

The loop lives here so every workflow runs the same one. Agent files invoke it;
they never restate it.

**Default cap: 3 iterations.** The cap is both a quality bound and the
subscription-budget guard. Never loop past it.

## Step 0 — Research-first gate

Invoke the `research-first` skill. If any of voice, client intelligence,
research, or rubric is missing, escalate now and generate nothing.

## Step 1 — Generate draft N

Write the draft against the brief, the voice markers, and the research. Save it
to the run directory as `draft.md` — the operator's edit magnitude is measured
against this file, so it must be the copy you actually hand over.

## Step 2 — Deterministic check

```bash
python3 tools/eval.py --client <client> --workflow <workflow> --copy <path-to-draft>
```

Exit 0 means the evaluation ran, whether or not the copy passed. **exit code 2
means the spine failed** — a missing rubric, an unparseable rubric, or a check
name that does not exist. On exit 2, surface stderr and stop the run. Do not
judge the deterministic criteria by eye instead; that silently removes the teeth
this loop exists to provide.

## Step 3 — Score judgment criteria

For every criterion in the rubric with `type: judgment`, produce:

- a verdict: `pass` or `fail`
- a confidence between 0 and 1
- a rationale naming what in the copy drove the verdict

Score passes as well as failures. The trace records predictions, not just
problems.

## Step 4 — Decide

| State | Action |
|---|---|
| Any invariant criterion fails | Regenerate, targeted at that criterion |
| Only tunable criteria fail, and N < cap | Regenerate |
| Everything passes | Return the copy to the operator |
| N equals the cap | Escalate |

**An invariant failure at the cap escalates. It never ships.** There is no
draft good enough elsewhere to justify shipping one. If you find yourself
reasoning that a particular invariant failure is acceptable this once, that
reasoning is the failure mode this rule exists to stop.

When regenerating, change what the failing criterion named. Rewriting
wholesale discards what already passed and burns an iteration.

## Step 5 — Trace, always

Write the trace before the turn ends — on a pass, on an escalation, and on a
spine failure that stopped the run:

```bash
python3 tools/trace.py write --client <client> --run-id <run-id> --payload -
```

The payload must carry every field `tools/trace.py` requires:

- `schema_version` — `"1"`
- `run_id`, `client`, `workflow` — the run identifiers
- `mode` — `generate` or `revise`
- `started_at`
- `iterations` — one entry per iteration actually run, each with `n`, its
  `criteria` (each entry carrying `id`, `verdict` of `pass` or `fail`, a
  `confidence` between 0 and 1, and a `rationale`), the `deterministic`
  output, alternatives considered, the `decision` (`regenerate`, `pass`, or
  `escalate`), and the `reason`
- `outcome` — `passed` or `escalated`
- `iteration_count` — must equal the number of entries in `iterations`
- `signal_links` — entries need `edit` and `signal`
- `escalation.sticking_point` — required when `outcome` is `escalated`

An escalation names the criterion and what was tried across iterations. "Could
not get the voice right" is not a sticking point. "Campfire-voice failed three
times; every opening reads as a claim rather than a scene, and the samples give
no example of an opening for a services page" is.

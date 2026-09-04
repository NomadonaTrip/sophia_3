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

Obtain the run id from the tool that owns the format — never invent one:

```bash
python3 tools/episodic.py new-run-id --workflow <workflow> --slug <page-slug>
```

Exit 0 prints the run id on stdout. Exit 2 means the slug was unusable (e.g.
it reduces to empty); fix the slug and try again. This run id is what later
lookups (`find_latest_shipped`, in particular what `/revise` relies on) parse
back apart, so a hand-built id will not round-trip.

## Step 1 — Generate draft N

Write the draft against the brief, the voice markers, and the research. Save it
to the run directory as `draft.md` — the operator's edit magnitude is measured
against this file, so it must be the copy you actually hand over.

**Cite every statistic.** `tools/eval.py`'s `no-fabricated-stats` invariant
requires a `[source: ...]` citation in the *same sentence* as any percentage or
large number (four digits or more; years are exempt). For example:

> Our clients see 30% faster response times [source: 2026 client survey].

A statistic with no citation in its sentence fails the check — cite it or cut
it. This is the only way to satisfy the invariant without deleting every
number from the copy.

**Emit section markers when the rubric configures `length_bands`.** For each
band name in the rubric's `length_bands` config (e.g. `h1`, `hero_subhead`,
`body_section`), wrap the corresponding text in the draft with a matching
marker so `tools/eval.py` can find it:

```
<!-- section: h1 -->
Tree surgery, done right.

<!-- section: hero_subhead -->
Straight talk about what your trees need, from people who climb them.
```

A band with no matching marker in the copy reports "missing from copy" even
if the text is present elsewhere in the draft — the marker is what locates
the section, not the content alone.

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
| Any invariant criterion fails, and N < cap | Regenerate, targeted at that criterion |
| Only tunable criteria fail, and N < cap | Regenerate |
| Everything passes | Return the copy to the operator |
| Something still fails (invariant or tunable), and N equals the cap | Escalate |

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

---
description: Onboard a client - writes business.md, icp.md, voice.md and evals/webcopy.md from real seed material.
argument-hint: <client-name>
---

# Onboard $1

Produce the four artifacts a workflow needs before it can generate anything:
`business.md`, `icp.md`, `voice.md`, and `evals/webcopy.md`.

## Hard stop: seed material is required

Ask the operator for existing copy — a current site, past pages, brochures,
anything the client actually wrote or approved. Two or three samples is a
working minimum.

**If the operator has no seed material, refuse and stop.** You cannot bootstrap
voice from nothing; a profile invented from a description of a business will
read plausibly and be wrong, and every page generated afterward inherits the
error. Say so plainly and offer to resume when samples exist.

Do not substitute samples from another client, another project, or the web.

## Interview

Ask one question at a time. Cover:

1. **Business** — what they sell, how they make money, what they will not do,
   what a good job looks like to them.
2. **Customer** — who buys, what triggers the search, what they fear getting
   wrong, what they compare against.
3. **Constraints** — claims that must never be made, regulated language,
   competitors not to name, anything legal has ruled on.
4. **Voice** — read back what you extracted from the samples and let the
   operator correct it. Their correction is worth more than your extraction.

## Extract the voice

Invoke the `voice-match` skill. Fill its marker table from the samples, quoting
a line for each marker. Anything the samples do not show is recorded as unknown,
never filled with a plausible default.

## Write the artifacts

Write to `memory/clients/$1/`:

- `business.md` — what they do, what they sell, constraints, what "good" means
- `icp.md` — who reads, what they want, what they fear, what they compare
- `voice.md` — the marker table with its quoted evidence, plus the unknowns
- `evals/webcopy.md` — the rubric, both sections

### The rubric

`## Invariant` is fixed boilerplate plus anything the operator marks invariant
during the interview:

```yaml
- id: campfire-voice
  type: judgment
  criterion: >
    Reads as one person talking to another, not as a company addressing a
    market. Matches the voice markers in voice.md.
- id: no-fabricated-stats
  type: deterministic
  check: fabricated_stat_scan
- id: client-brief-adherence
  type: judgment
  criterion: >
    Every claim traces to research or client intelligence. Nothing asserted
    that the client has not said or the research does not support.
```

`## Tunable` is derived from the samples, not invented:

- `banned_phrases` — phrases absent from every sample, plus anything the
  operator named in the interview
- `length_bands` — measured from the samples, per section
- `passive_rate` — measured from the samples, rounded up to a workable ceiling
- judgment criteria for hook and flow, written against what the samples do

Show the operator the rubric before writing it. It is their control surface.

## Verify

```bash
python3 -m interfaces.retrieval --client $1 --query "" --scope voice
python3 tools/eval.py --client $1 --workflow webcopy --copy <one-of-the-samples>
```

The samples should mostly pass their own rubric. If a sample fails
`no-fabricated-stats`, that usually means the sample's own statistics are
uncited — not that the rubric is wrong; see the `gen-eval-loop` skill for the
`[source: ...]` citation convention and cite the sample's numbers (or accept
the fail) before concluding anything is broken. If a sample fails an
invariant criterion for a reason you disagree with, fix the rubric with the
operator before finishing.

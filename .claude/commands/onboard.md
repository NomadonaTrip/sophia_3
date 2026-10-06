---
description: Onboard a client - writes business.md, icp.md, voice.md and evals/webcopy.md from real seed material.
argument-hint: <client-name>
---

# Onboard $1

Produce the four artifacts a workflow needs before it can generate anything:
`business.md`, `icp.md`, `voice.md`, and `evals/webcopy.md`.

## Resume or restart

Onboarding survives the session ending. Before anything else:

```bash
python3 tools/onboarding.py status --client $1
```

Sections run in order: `seed`, `business`, `customer`, `constraints`, `voice`,
`rubric`, `written`.

- **Nothing saved** — start at `seed`.
- **Progress saved** — summarise it in a line ("business and customer settled;
  constraints half-done") and ask: **resume, restart a section, or restart
  from scratch?**
  - *Resume* — read back each settled decision in brief, then pick up at
    `next`. If `in_progress` holds messages for that section, continue from
    where they stop rather than re-asking what was already answered.
  - Any section in `recheck` was settled before an earlier section was redone.
    Read its decision back and ask whether it still holds; re-save it if so.
  - Any section in `discard_pending` is settled but its messages were never
    cleared. Ask the discard question below for it.

The operator can say "restart" at any point. Before resetting, say exactly
what will be cleared and wait for them to confirm:

```bash
python3 tools/onboarding.py reset --client $1                     # everything
python3 tools/onboarding.py reset --client $1 --section <section> # one section
```

A section reset flags every later settled section for recheck. A reset never
touches the profile files or the samples.

## Log every message

Every message in the interview — your questions and the operator's answers —
is logged as it happens, before you reply:

```bash
python3 tools/onboarding.py log --client $1 --section <section> --role sophia|operator --text -
```

## Settle each section

A section is settled when the operator confirms your read-back of it. Then:

1. Save the decision — the substance the artifacts will be written from, not
   a transcript:

   ```bash
   python3 tools/onboarding.py save --client $1 --section <section> --payload -
   ```

2. Ask: *"Decision for `<section>` saved. OK to discard the session messages
   for it?"*
   - Yes:
     `python3 tools/onboarding.py discard --client $1 --section <section>`
   - No:
     `python3 tools/onboarding.py keep --client $1 --section <section>`

Never discard before the save succeeds; the tool refuses, and that refusal is
a spine failure, not something to route around.

## Hard stop: seed material is required

Ask the operator for existing copy — a current site, past pages, brochures,
anything the client actually wrote or approved. Two or three samples is a
working minimum.

**If the operator has no seed material, refuse and stop.** You cannot bootstrap
voice from nothing; a profile invented from a description of a business will
read plausibly and be wrong, and every page generated afterward inherits the
error. Say so plainly and offer to resume when samples exist.

Do not substitute samples from another client, another project, or the web.

Settle `seed` with the paths of the samples the operator confirmed.

## Interview

Ask one question at a time. Each numbered topic is its own section — settle it
before moving on. Cover:

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

Section names: Business → `business`, Customer → `customer`, Constraints →
`constraints`, Voice → `voice` (settled once the operator has corrected the
extracted marker table).

## Write the artifacts

Write from the saved decisions in
`memory/clients/$1/onboarding/decisions.json`, not from memory of the
conversation — after a resume, that file is the only record of earlier
sections.

Check `profile_files` in the status output first. If any of the four already
exist, show the operator what is there and get an explicit yes before
overwriting it.

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
Their approval settles `rubric`; save the approved rubric as its decision.
Once all four files are written, settle `written` with the list of files.

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

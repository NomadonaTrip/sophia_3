# Sophia-Internal — Design

**Date:** 2026-09-04
**Source PRD:** `prd.md` (Hybrid Claude-Code-Native Content System, Internal)
**Status:** Approved for implementation planning

This design realizes the PRD. Where the PRD prescribes (architecture §4, invariants §5, functional requirements §6), this document implements rather than revisits. Where the PRD left latitude, the decisions and their reasons are recorded below.

---

## 1. Decisions taken during design

| Decision | Choice | Reason |
|---|---|---|
| Build location | `/home/nomad/sophia-internal` (ext4) | H-NFR3 requires the working tree and `memory/` off the Windows mount. `/mnt/e` is 9p; git and file reliability degrade there. `prd.md` is copied into the repo; `Sophia_2/` keeps a pointer. |
| Loop decomposition | Skill owns the loop; agent files are thin roles | §8 promises "adding a workflow = dropping in one agent file." Inlining the loop per agent guarantees drift at workflow #2. |
| Approval UX | In-session conversational + `tools/approve.py` for persistence | Claude Code's Bash tool cannot drive interactive stdin reliably. Judgment stays conversational; persistence stays deterministic. |
| Onboarding seed | Fresh conversational interview; operator supplies samples | Cleaner test of H-FR1's "cannot bootstrap voice from nothing" than auto-ingesting prior artifacts. |
| Rubric config location | `eval.py` reads its check config from the rubric markdown | Otherwise tuning the rubric means editing Python, and the invariant/tunable split (§5) stops being meaningful to the operator. |
| Rubric block format | YAML in fenced blocks (PyYAML) | The file is meant to be hand-edited. Stdlib `tomllib` avoids the dependency but makes lists-of-criteria materially uglier. One pure-Python dependency, no service — consistent with H-NFR1. |
| Test boundary | TDD on `tools/` and `interfaces/`; none on the prompt-driven loop | The loop is validated by the §9 acceptance gate. Named honestly rather than papered over. |

---

## 2. Repository layout

```
~/sophia-internal/
  CLAUDE.md                  # routing doc — coordinator-as-delegator
  prd.md
  .claude/
    agents/      _TEMPLATE.md  webcopy.md
    commands/    onboard.md  webcopy.md  revise.md  client.md
    skills/      gen-eval-loop/  voice-match/  research-first/
  interfaces/    retrieval.py  performance.py  delegation.py
  tools/         eval.py  trace.py  ingest_gsc.py  ingest_ga4.py  approve.py
  memory/clients/<client>/
      business.md  voice.md  icp.md
      evals/webcopy.md
      episodic/<ts>-<workflow>-<slug>/    # run.md, trace.json, shipped.md, decision.json
      performance/                         # normalized artifacts
  docs/          acceptance.md  superpowers/specs/
  tests/
  .env.example  .gitignore  pyproject.toml
```

Root `CLAUDE.md` is the routing doc, not a router. It names available workflows, the core invariants, and the active client, and tells the main session when to delegate. Client context switching (H-FR11) is `/client`.

`memory/` is git-tracked (H-NFR4). Any remote must be private or local-only; client data does not leave the machine. `.env` is git-ignored and never logged (H-NFR6); no secrets exist in V1.

---

## 3. The four seams (§8)

### 3.1 Retrieval — `interfaces/retrieval.py`

```python
class Hit:      # path, line, text, scope
class Retriever(Protocol):
    def search(self, query: str, *, client: str,
               scope: Scope | None = None, limit: int = 20) -> list[Hit]: ...
```

V1 backing is `GrepRetriever`: subprocess grep scoped to `memory/clients/<client>/`, with `scope` narrowing to one of `voice | business | icp | evals | episodic | performance`.

Per H-FR6, `search` returns `[]` when nothing matches and never raises on an absent path — every caller must tolerate empty results. A missing client directory is an empty result, not an error; the *caller* decides whether absence is fatal (the research-first gate does; a background lookup does not).

Also runnable as a module so agents can reach it through Bash:

```
python3 -m interfaces.retrieval --client C --query "..." [--scope voice] [--limit N]
```

### 3.2 Performance artifact — `interfaces/performance.py`

One normalized shape, emitted by every ingestion path, keyed to funnel stage so H-FR7's diagnosis is a lookup rather than a fresh judgment each time:

```json
{"schema_version": "1",
 "client": "orban-forest",
 "source": "gsc | ga4 | screenshot",
 "ingested_at": "2026-09-04T00:00:00Z",
 "period": {"start": "2026-08-01", "end": "2026-08-31"},
 "sample_warning": false,
 "pages": [
   {"url": "/services/tree-surgery",
    "row_confidence": "high | low",
    "stage_signals": {
      "top":    {"impressions": 0, "ctr": 0.0, "avg_position": 0.0},
      "mid":    {"sessions": 0, "bounce_rate": 0.0, "avg_engagement_s": 0.0},
      "bottom": {"conversions": 0, "conversion_rate": 0.0}}}]}
```

Absent metrics are `null`, not `0` — a page with no conversion tracking must not read as a page with zero conversions.

`sample_warning` is set true when volume falls below a floor defined as a module constant in `performance.py` (V1: fewer than 100 impressions or 30 sessions across the period), overridable per ingest via `--min-impressions` / `--min-sessions`. This is the §11 mitigation against calibrating on noise: revise mode must surface the warning in its diagnosis rather than suppress it.

The module owns the schema, a validator, and the writer that persists artifacts to `memory/clients/<client>/performance/`.

### 3.3 Agent-file convention — `.claude/agents/_TEMPLATE.md`

Fixed frontmatter: `name`, `description`, `tools` (explicit allowlist), `model`.
Fixed body sections, in order: **Role**, **Memory to load**, **Rubric**, **Loop**, **Escalation**.

Adding a workflow fills the same slots. Only Role, the tool allowlist, and the rubric path change; the Loop section invokes `gen-eval-loop` verbatim.

### 3.4 Coordinator contract — `interfaces/delegation.py`

Per §5 ("a dark component is an interface plus a trivial backing, never empty scaffolding"), this is not a stub. It parses `.claude/agents/*.md` frontmatter into `WorkflowSpec` records (`name`, `agent_file`, `rubric_path`, `modes`, `tools`) and validates each against `_TEMPLATE.md`'s required sections.

That enumeration is exactly the call a future router makes. Today it earns its place via `python3 -m interfaces.delegation --validate`, which catches a malformed agent file before a run does.

---

## 4. Memory and the rubric

### 4.1 Semantic memory

`business.md`, `icp.md`, `voice.md` use defined headings so grep scope-narrowing is meaningful. `voice.md` is produced by `/onboard` from real seed material and carries observable markers (sentence rhythm, characteristic constructions, vocabulary the client uses and avoids), not adjectives.

### 4.2 Episodic memory

One directory per run: `memory/clients/<client>/episodic/<ISO-ts>-<workflow>-<slug>/`

- `run.md` — human-readable record of the run
- `trace.json` — decision trace (§5.3)
- `shipped.md` — the approved copy, written on approve (H-FR9)
- `decision.json` — operator decision, timestamp, edit magnitude

Persisting shipped copy is what lets a later revision diff published-against-performed.

### 4.3 The rubric — `memory/clients/<client>/evals/webcopy.md`

The operator's control surface. Two structurally separate sections, so "invariant criteria can never be tuned away" (§5) is enforced by where a criterion lives, not by discipline.

````markdown
# Web Copy Rubric — orban-forest

## Invariant
```yaml
- id: campfire-voice
  type: judgment
  criterion: >
    Reads as one person talking to another by a fire...
- id: no-fabricated-stats
  type: deterministic
  check: fabricated_stat_scan
- id: client-brief-adherence
  type: judgment
  criterion: >
    Every claim traces to research or client intelligence.
```

## Tunable
```yaml
- id: banned-phrases
  type: deterministic
  check: banned_phrases
  config:
    phrases: ["unlock", "leverage", "in today's fast-paced world"]
- id: length-bands
  type: deterministic
  check: length_bands
  config:
    h1: [3, 12]
    hero_subhead: [10, 30]
    body_section: [40, 150]
- id: passive-voice
  type: deterministic
  check: passive_rate
  config: {max_rate: 0.15}
- id: hook-strength
  type: judgment
- id: flow
  type: judgment
```
````

`type: deterministic` dispatches to a named check in `eval.py`. `type: judgment` is scored by the subagent against the stated criterion. A criterion's `invariant` status is derived from its section — it is never a field a generation step could set.

---

## 5. The loop — `.claude/skills/gen-eval-loop/`

The skill owns the procedure end to end. `webcopy.md` invokes it and adds nothing.

**Step 0 — research-first gate.** Confirm all four present via retrieval: voice profile, client intelligence (business + icp), research for this page, rubric. Any one missing → escalate immediately; generate nothing. H-FR2 and §5's "never invent" are enforced before the first token, not caught after. The checklist lives in the `research-first` skill so revise mode and future workflows share it.

**Step 1 — generate** draft N from brief + voice + research.

**Step 2 — deterministic check.** `tools/eval.py` → JSON. Machine-checkable criteria only.

**Step 3 — judgment scoring.** Score every `type: judgment` criterion, emitting verdict, confidence, and rationale for each — including passes. H-FR5 wants predictions, not only failures.

**Step 4 — decide.**

| State | Action |
|---|---|
| Any invariant fails | Regenerate, targeted at the failing criterion |
| Only tunable fails, N < cap | Regenerate |
| All pass | Return copy to operator |
| N == cap (default 3) | Escalate, naming the criterion and what was tried |

An invariant failure at the cap **escalates; it never ships.** This is H-FR3's hard edge and the branch where a prompt-driven loop is most likely to rationalize, so the skill states it without hedging. The cap is also the subscription-budget guard (H-NFR5).

**Step 5 — trace, always.** Pass, escalation, or abort, `tools/trace.py` writes before the turn ends (§5 "trace everything").

---

## 6. Deterministic spine — `tools/`

All CLI-in / JSON-out, invoked via Bash.

```
tools/eval.py       --client C --workflow webcopy --copy PATH
                    → {"criteria":[{"id","type","invariant","status","detail"}],
                       "invariant_failed": bool}
tools/trace.py      write --client C --run-id ID --payload PATH|-
tools/ingest_gsc.py --client C --csv PATH [--period S:E] [--source screenshot]
tools/ingest_ga4.py --client C --csv PATH [--period S:E] [--source screenshot]
tools/approve.py    --client C --run-id ID --decision approve|edit|reject
                    [--copy PATH] [--note TEXT]
```

`eval.py`'s checks are a dispatch table keyed by the rubric's `check:` name: `banned_phrases`, `length_bands`, `passive_rate`, `fabricated_stat_scan` (H-FR4). Adding a check is one function plus one rubric line. An unknown `check:` name is a hard error, not a skipped criterion — silently ignoring a criterion is how teeth get lost.

**Screenshot ingestion (H-FR8)** has no separate tool. `/revise` instructs Claude to read the image, emit rows as CSV, then call the same ingestor with `--source screenshot`, which stamps every row `row_confidence: low`. One artifact path, one parser, and the CSV-is-source-of-truth hierarchy is visible in the data rather than asserted in prose.

**Trace schema (H-FR5, plus H-FR7's signal linkage):**

```json
{"schema_version": "1",
 "run_id": "...", "client": "...", "workflow": "webcopy",
 "mode": "generate | revise", "started_at": "...",
 "iterations": [
   {"n": 1,
    "criteria": [{"id": "campfire-voice", "verdict": "fail",
                  "confidence": 0.7, "rationale": "..."}],
    "deterministic": {},
    "alternatives_considered": ["..."],
    "decision": "regenerate", "reason": "..."}],
 "outcome": "passed | escalated",
 "iteration_count": 2,
 "escalation": {"sticking_point": "..."},
 "signal_links": [{"edit": "...", "signal": "gsc:ctr_drop:/page"}]}
```

`signal_links` is populated in revise mode only. It is what makes acceptance criterion §9.4 checkable rather than a claim.

**Edit magnitude.** `approve.py` records the decision and, on `edit`, the lines changed against the delivered draft. Acceptance criterion §9.1 is "operator edit rate trends down"; without capturing magnitude at approval time it is unmeasurable after the fact. This is an addition to the PRD, made because the primary validation gate depends on it.

---

## 7. Commands — `.claude/commands/`

**`/onboard <client>`** — conversational. Asks for real seed material (existing copy, samples) and refuses to proceed without it: H-FR1's "cannot bootstrap voice from nothing" is a hard stop in the command, not advice. It does not auto-ingest prior artifacts from other projects.

Writes `business.md`, `icp.md`, `voice.md`, and `evals/webcopy.md`. The invariant section is fixed boilerplate (campfire voice, no fabricated stats, client-brief adherence) plus anything marked invariant during the interview. The tunable section is derived from the samples: banned phrases actually observed as absent, length bands actually measured. The `voice-match` skill holds the extraction method so onboarding and generation reason about voice identically.

**`/webcopy <client> <brief>`** — generate mode. Delegates to the `webcopy` agent, which runs `gen-eval-loop` and returns passed copy or an escalation. The result is presented in-session for approve / edit / reject (H-FR10), then `approve.py` persists (H-FR9).

**`/revise <client> <page>`** — revise mode. Ingest first (CSV or screenshot), then diagnose. The current copy is read from the most recent `shipped.md` in that client's episodic memory matching the page (H-FR9). If no shipped copy exists for the page, the command escalates rather than revising a draft the operator never approved.

**`/client <name>`** — switch active client context, loading that client's full profile (H-FR11).

---

## 8. Revise mode (H-FR7)

The funnel mapping is a table in the skill, applied to the artifact's `stage_signals`:

| Weak signal | Stage | Action surface |
|---|---|---|
| Impressions healthy, CTR low | top | title, meta description, hook |
| CTR healthy, bounce high or engagement low | mid | message-match against the promise that earned the click |
| Engagement healthy, conversion low | bottom | CTA, offer framing |

Proposed edits run through the **same** `gen-eval-loop`. A revision can fail an invariant exactly as a draft can, and is regenerated the same way. Each edit records its triggering signal into `signal_links`.

When `sample_warning` is true the diagnosis is presented as provisional and says so explicitly. Low volume is a caveat on the read, not grounds for withholding it.

---

## 9. Error handling

Three failure modes, three distinct behaviors. Stated explicitly because a prompt-driven loop will otherwise blur them:

1. **Missing inputs** (voice, intelligence, research, or rubric absent) → escalate before generating. Never substitute invention.
2. **Spine failure** (`eval.py` non-zero exit, malformed rubric, unparseable CSV, unknown check name) → surface stderr and stop. Never fall back to judging deterministic criteria by eye; that silently removes the teeth acceptance criterion §9.2 tests for.
3. **Cap reached** → escalate with the specific sticking point: which criterion, what was attempted across iterations.

---

## 10. Testing

**Spine — TDD.** pytest over `tools/` and `interfaces/`, tests written before implementation. Fixtures: a sample rubric; copy that fails each deterministic check individually; real-shaped GSC and GA4 CSV exports including a malformed one. Heaviest coverage on the CSV parsers and the funnel mapper, where silent wrongness is most expensive and least visible.

**Loop — no unit tests.** Validated by the §9 acceptance gate against Orban Forest, tracked in `docs/acceptance.md`:

| Criterion | Evidence |
|---|---|
| §9.2 Teeth | A planted invariant failure caught and regenerated before reaching the operator |
| §9.3 Grounded | Claims in generated copy trace to research or intelligence |
| §9.4 Revise works | A real GSC export maps to the correct funnel stage; edits carry `signal_links` |
| §9.5 Substrate | A trace exists for every run and is inspectable |
| §9.1 Compounding | Edit-rate series from `approve.py` across a run of pages — **operator-run, open** |

---

## 11. Build order

Per PRD §10, tests preceding each step:

1. Memory layout + `/onboard` (seed profiles + rubric)
2. Loop skill + `eval.py` + `trace.py`
3. Grep retrieval behind the interface
4. Web copy generate mode end-to-end on Orban Forest
5. Manual ingestion + revise mode
6. Confirm calibration *capture* works — traces and performance artifacts join by page; tuning stays deferred

---

## 12. Open item

Acceptance criterion §9.1 (compounding) cannot be closed by the build. It requires the operator generating and approving several real Orban Forest pages so an edit-rate series exists. The build delivers the system, seeds it via `/onboard`, and proves the mechanics — trace written every run, evaluator catching a planted invariant failure, a real export mapping to the correct stage. The compounding claim remains open until the pages are run.

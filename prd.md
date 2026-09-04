# PRD — Hybrid Claude-Code-Native Content System (Internal)

**System name (working):** Sophia-Internal
**Audience:** Claude Code (build agent) + Tayo (operator)
**Runtime:** Claude Code on WSL2, single machine (RTX 3080), Claude subscription
**Role:** Internal content system for Orban Forest, and the proving ground where the reasoning design — the generate→evaluate loop, the eval rubrics, voice matching, and funnel-based revision — is validated before and alongside productization. Optimizes for iteration speed and operator leverage, not for packaging or portability.

**Relationship to the deployable harness:** Independent codebase. The two systems must stay aligned on the _reasoning artifacts_ only (rubric schema, voice-profile schema, funnel→action mapping, trace schema, normalized performance artifact). Everything else diverges.

---

## 1. Goals

1. Prove the generate→evaluate loop produces **compounding** web-copy quality for a single client — page N needs fewer edits than page 1 because memory accumulated.
2. Establish the **decision-trace substrate** and **semantic + episodic memory** from day one.
3. Establish the **four seams** (retrieval, performance artifact, agent-file convention, coordinator contract) so future workflows and backends slot in without refactor.
4. Run entirely on the Claude subscription, locally, single operator, low ceremony.

## 2. Non-Goals (V1)

Multi-tenancy; packaging or install story; model-agnosticism (model is fixed = Claude); polished UI; customer deployment; automated publishing; social/blog workflows; cross-client pattern transfer; vector/KG retrieval.

## 3. Scope

**In scope (built and live):**

- Coordinator as **delegator** (the main Claude session + a routing doc), not a router.
- One workflow subagent: **web copy**.
- Generate→evaluate→regenerate loop, **prompt-driven inside the subagent's turn**, with a hard iteration cap and escalation.
- Deterministic Python spine (`tools/eval.py`, `tools/trace.py`, ingestors), **Bash-invoked, CLI-in / JSON-out**.
- **Grep retrieval** over markdown memory (behind the retrieval interface).
- **Semantic + episodic memory** as markdown, git-tracked, on ext4.
- **Onboarding command** producing voice profile, business context, ICP, and the web-copy eval rubric (invariant + tunable).
- **Manual GSC/GA4 ingestion** (CSV + screenshot) → normalized performance artifact → **revise mode**.
- **Decision-trace capture** on every run.
- **CLI approval** (approve / edit / reject) with shipped-copy persistence.

**Slotted (interface built now, backend dark):** router; workflows #2..n; vector/KG retrieval; calibration/self-improvement (trace _capture_ on, rubric _tuning_ off); publishing.

**Out of scope:** anything customer-facing; live API integrations; secrets-bearing flows.

## 4. Architecture

Claude-Code-native. The main session is the coordinator. Subagents are `.claude/agents/*.md`. Operator entry points are `.claude/commands/*.md`. Shared methodology (the loop, voice-match, research-first grounding) lives in `.claude/skills/` so it is written once. The deterministic spine is `tools/*.py`, invoked via Bash with clean CLI signatures. Memory is markdown under `memory/`, git-tracked, on the native Linux filesystem.

```
sophia-internal/
  .claude/
    agents/      webcopy.md  _TEMPLATE.md
    commands/    onboard.md  webcopy.md  revise.md
    skills/      gen-eval-loop/  voice-match/  research-first/
  interfaces/    retrieval.py  performance.py  delegation.py
  tools/         eval.py  trace.py  ingest_gsc.py  ingest_ga4.py
  memory/        clients/<client>/{business,voice,icp}.md
                 clients/<client>/evals/webcopy.md
                 clients/<client>/episodic/           # run logs + shipped copy
```

The loop is prompt-driven (the subagent generates, evaluates, regenerates within one autonomous run); the _deterministic_ checks and trace-writing are Python. This is a deliberate trade: prompt-driven control is less rigorous than a coded loop, bought back by deterministic checks + a hard cap + mandatory escalation.

## 5. Core Invariants (apply to every workflow)

- **Research-First:** no content generated without all of (voice profile, client intelligence, research, rubric). Any missing → escalate, never invent.
- **Invariant vs tunable rubric:** invariant criteria (campfire voice, no fabricated stats, client brief) can never be regenerated away or tuned away; only tunable criteria are negotiable.
- **Interfaces, not implementations:** a dark component is an interface plus a trivial backing (grep, markdown), never empty scaffolding for a backend nothing calls.
- **Trace everything:** every run emits a decision trace, even though nothing consumes it yet.
- **Propose, don't apply:** any future learning proposes changes for operator approval; nothing self-modifies.

## 6. Functional Requirements

- **H-FR1** Operator onboards a client via a conversational command that writes `voice.md`, `business.md`, `icp.md`, and `evals/webcopy.md` (invariant + tunable sections). Onboarding requires real seed material (existing copy, samples); it cannot bootstrap voice from nothing.
- **H-FR2** Before generating, the web copy subagent loads voice + intelligence + research + rubric via the retrieval tool.
- **H-FR3** The subagent runs generate→evaluate→regenerate to a hard cap (default 3), then either returns passed copy or escalates a specific sticking point. It never ships an invariant failure and never loops past the cap.
- **H-FR4** `tools/eval.py` runs deterministic checks (banned-phrase blacklist, length bands, passive-voice rate, fabricated-stat scan) and returns JSON. Judgment criteria (voice, hook, flow) are scored by the subagent against the rubric.
- **H-FR5** `tools/trace.py` persists a decision trace per run: per-criterion prediction + confidence, alternatives, rationale, iteration count.
- **H-FR6** Retrieval is available behind the `Retriever` interface; V1 backing is grep with scope narrowing. Empty results are tolerated by all callers.
- **H-FR7** Revise mode: given current copy + a normalized performance artifact, the subagent diagnoses by funnel stage (top→title/meta/hook, mid→message-match, bottom→CTA/offer), proposes targeted edits, runs them through the same loop, and traces each edit to its triggering signal.
- **H-FR8** Manual ingestion converts a GSC or GA4 export into the normalized performance artifact. CSV is pure-Python; screenshot ingestion is agent-assisted (vision) and emits the same artifact. CSV is source of truth; screenshots are a lossy fallback.
- **H-FR9** Shipped copy is persisted to episodic memory so a later revision can diff published-vs-performed.
- **H-FR10** Operator reviews via CLI: approve / edit / reject.
- **H-FR11** Operator can switch client context by name, loading that client's full profile.

## 7. Non-Functional Requirements

- **H-NFR1** Runs inside Claude Code on the Claude subscription. No external service dependency in V1.
- **H-NFR2** Single machine (WSL2 / RTX 3080), single operator, single session.
- **H-NFR3** Working tree and `memory/` on ext4 (`/home/...`), not the Windows mount, for git and file reliability.
- **H-NFR4** `memory/` is git-tracked; any remote is private or local-only (client data stays local; cf. existing NFR12).
- **H-NFR5** The loop's hard cap doubles as a subscription-budget guard.
- **H-NFR6** No live API calls or secrets in V1; `.env` convention established (git-ignored, never logged; cf. existing NFR8) for when analytics/publishing APIs arrive.
- **H-NFR7** Iteration speed is prioritized over reliability guarantees — this is a proving ground, and prompt-driven loop nondeterminism is an accepted trade, bounded by deterministic checks, the cap, and escalation.

## 8. Interfaces (the four seams)

Use the provided `interfaces/retrieval.py`, `interfaces/performance.py`, `interfaces/delegation.py` as the fixed contracts. Agent files follow `.claude/agents/_TEMPLATE.md`. Adding a workflow = dropping in one agent file; only Role, tool allowlist, and which rubric it loads change.

## 9. Acceptance Criteria (validation gate)

1. **Compounding:** across a run of pages for one client, operator edit rate trends down.
2. **Teeth:** the evaluator catches and regenerates invariant failures _before_ copy reaches the operator, unprompted.
3. **Grounded:** every claim in generated copy traces to research or intelligence, not invention.
4. **Revise works:** a real GSC/GA4 export maps to the correct funnel-stage action, with each edit traced to its signal.
5. **Substrate present:** a decision trace is captured on every run and is inspectable.

If these hold, the reasoning design is validated and workflow #2 (and the deployable harness) can build on a proven engine.

## 10. Build Sequence

1. Memory layout + onboarding command (produces the seed profiles + rubric).
2. Loop skill + `tools/eval.py` + `tools/trace.py` (deterministic spine).
3. Grep retrieval behind the interface.
4. Web copy generate mode end-to-end on one client.
5. Manual ingestion + revise mode.
6. Confirm calibration _capture_ works (traces + artifacts join by page); leave tuning deferred.

## 11. Risks

| Risk                                          | Mitigation                                                               |
| --------------------------------------------- | ------------------------------------------------------------------------ |
| Prompt-driven loop nondeterminism             | Deterministic checks in Python; hard cap; mandatory escalation           |
| Calibration "learns" from low-volume noise    | Capture only in V1; no auto-tuning; `sample_warning` respected in revise |
| Scope creep into social/blog                  | Explicit validation gate before any workflow #2                          |
| Drift from the deployable harness's reasoning | Shared reasoning-artifact schemas are the contract; review them jointly  |

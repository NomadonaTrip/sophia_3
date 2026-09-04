# SDD ledger — plan: docs/superpowers/plans/2026-09-04-sophia-internal.md

Spec: `docs/superpowers/specs/2026-09-04-sophia-internal-design.md` (read, binding authority)
Branch: `build/sophia-internal` off `main` (tracks `origin/main` = github.com/NomadonaTrip/sophia_3, confirmed private)
Repo: `/home/nomad/sophia-internal` (ext4, per H-NFR3)

## Pre-flight scan

### Cross-task: shared files and interfaces

| Producer | Consumer | Produces → consumes | Finding |
|---|---|---|---|
| T1 pyproject (`pythonpath=["."]`) | all test files | package import path | clean |
| T2 `retrieval.py` CLI | T11 research-first, T12 onboard/client | `python -m interfaces.retrieval --client --query [--scope]` | clean; `--query ""` is a match-all idiom, grep -F handles it |
| T3 `load_rubric`/`Rubric`/`RubricError` | T4 `eval.py` imports | signatures match | clean |
| T3 fixture `rubric_valid.md` | T4 CLI tests, T13 e2e | invariant=fabricated_stat_scan, tunable=banned_phrases | clean — T13's passing draft has no digits, failing draft has `40%` → only `no-fabricated-stats` fails, invariant |
| T5 `run_dir`/`new_run_id`/`find_latest_shipped` | T6, T9, T13 | same signatures throughout | clean |
| T7 `build_artifact`/`empty_stage_signals`/`write_artifact` | T8 ingestors | positional `(client, source, period, pages)` | clean |
| T7 `weak_stage` | T13 e2e | funnel table | clean — verified against `gsc_export.csv`: `/services/tree-surgery`→top, `/`→None, `/contact`→None |
| T8 `gsc_export.csv` fixture | T13 e2e | column contract | clean |
| T9 `approve.py` | T12 webcopy/revise commands | CLI flags cited in prose | clean |
| T10 `.claude/agents/*` | T12 `CLAUDE.md` delegation CLI | `--validate` | clean |
| T11 skills | T10 `webcopy.md`, T12 commands | skill names `gen-eval-loop`, `voice-match`, `research-first` | clean |

### Per-task: internal self-consistency (tests vs code the same task specifies)

| Task | Finding |
|---|---|
| T1 | clean |
| T2 | **Q** — CLI test used `subprocess.run` without `cwd`, while T10's equivalent passes `cwd=REPO_ROOT`; `-m` resolution depends on cwd. Also `REPO_ROOT` was undefined in the file. |
| T3 | clean — regex, YAML-error, and duplicate-id paths all reachable from the tests given |
| T4 | **P** — the `sys.path` shim is described in a note *after* the `eval.py` code block, not inside it. An implementer transcribing the block drops it, and every subprocess test fails on `import tools.rubric`. Applies to `trace.py`, `approve.py`, `ingest_gsc.py`, `ingest_ga4.py` too. |
| T4 | verified by hand: `passive_rate` fixture yields 2/4 (`was cut`/`was sent` are irregular, correctly unmatched) → 0.5 > 0.15, test holds |
| T4 | verified: `fabricated_stat_scan` year-filter lets `2026` through, flags `12,000` and `40%` |
| T5 | clean |
| T6 | clean |
| T7 | verified: `sample_warning` AND-logic satisfies all six of its own tests |
| T8 | clean |
| T9 | clean |
| T10 | **AJ** — "Expected: 20 passed" is wrong; the listed tests total 17 (5 + 4 params + 5 params + 1 + 2). Other tasks' counts spot-checked: T11=13 ✓, T12=18 ✓, T2=11 ✓. |
| T11 | verified every string assertion against the SKILL.md text it ships: `never ships`, `exit code 2`, `never invent`, `adjective`/`marker` all present |
| T12 | **H** — `test_onboard_refuses_without_seed_material` asserts `"cannot bootstrap" or "never invent"`, but the `onboard.md` text the same task ships says "Voice cannot be bootstrapped from nothing" and never "never invent". Neither substring present → test fails as written. |
| T13 | clean |
| T14 | operator-driven by design; not an agent task |

## Rulings

Ruling: H — amended the plan's `onboard.md` text to "You cannot bootstrap voice from nothing", rather than loosening the test. Why: the spec (§7) makes the refusal the point of the command, so the assertion is the load-bearing half; the wording is not. Cost if wrong: a slightly stiffer sentence in an operator-facing prompt.

Ruling: Q — added `cwd=REPO_ROOT` and the `REPO_ROOT` constant to T2's CLI test, matching T10. Why: `python -m` resolves against cwd, so without it the test passes or fails on where pytest happened to be invoked from. Cost if wrong: none; it is strictly more deterministic.

Ruling: P — the `sys.path` shim stays a note, but every affected dispatch (T4, T6, T8, T9) will carry it as an explicit requirement in the dispatch prompt. Why: inlining it into five code blocks in the plan risks transcription drift between them; the dispatch is the reliable channel. Cost if wrong: an implementer misses it, subprocess tests fail loudly and immediately — cheap to catch.

Ruling: AJ — "Expected: N passed" lines are indicative, not binding; the requirement is that every test in the task passes. Every dispatch will say so. Why: I derived those counts by hand and at least one is wrong; an implementer treating them as spec would invent tests to hit a number. Cost if wrong: none — the real gate is a green suite.

## Progress

Task 1: complete (commits 973d73e..1b9a841, review clean)
Task 1: minor (deferred): pyproject `packages = ["interfaces","tools"]` is a hardcoded list; a future top-level package must be added by hand or `pip install -e .` silently omits it.

Task 2: review found 2 Important + 3 Minor, all plan-mandated (implementer transcribed my reference code verbatim).
Task 2: Ruling: exit-code-2 discards valid matches — FIX. grep returning 2 (one unreadable file) still writes real matches to stdout; dropping them silently zeroes unrelated results. Parse stdout regardless of return code, still never raise. Why: "never raises" was the constraint, "returns nothing on partial failure" was my sloppy reading of it. Cost if wrong: none — strictly more data, same exception surface.
Task 2: Ruling: limit truncation order unprincipled + its test asserts only length — FIX BOTH. Sort hits by (path, line) before truncating; strengthen the test to assert which hit survives. Why: reviewer is right that the test would pass against a wrong implementation. Cost if wrong: a sort on a bounded list.
Task 2: Ruling: CLI rejects a leading-dash query — DOCUMENT, not fix. argparse treats `-x` as a flag before search() is reached; there is no clean argparse fix. Add the `--query=-x` form to the flag's help text. Why: the alternative is hand-rolling argument parsing for a rare input on an internal tool. Cost if wrong: a subagent passing a dash-led phrase gets a loud argparse error, not silence.
Task 2: minor (deferred): binary-file matches are silently dropped (grep emits no line number). Correct for a markdown corpus; untested and undocumented.
Task 2: fix round 1/5 (3 addressed, 0 open; commits 089a463..8433d10)
Task 2: complete (commits 1b9a841..8433d10, review clean)

Task 3: review found 1 Critical + 2 Minor. Critical is plan-mandated (my `_SECTION_RE`).
Task 3: Ruling: `_SECTION_RE` unbounded lazy match crosses `##` headings — FIX. With an empty `## Invariant` it captures Tunable's fence and marks those criteria invariant; with two fenced blocks under one heading it parses the first and silently drops the real criteria. Bound the search to the next `##` heading. Why: the spec makes invariance structural, and a regex that leaks across sections makes the guarantee decorative — this is the exact failure I told the reviewer to hunt for. Cost if wrong: a stricter parser rejects an exotic-but-valid rubric layout, loudly.
Task 3: minor (deferred): `Criterion.config` is a mutable dict on a frozen dataclass; distinct per criterion today, but nothing stops a later stage mutating a held reference.
Task 3: minor (deferred): the "entries must be mappings" error cannot name a criterion id (none parsed yet), so it is less specific than sibling messages.
Task 3: fix round 1/5 (1 addressed, 1 new Important from the fix diff — `##` YAML comment at column 0 truncates the section; commits 086b4d9..383dde6)
Task 3: fix round 2/5 (1 addressed, 1 new Important from the fix diff — fence toggle is a `'```' in line` substring check, so a nested 3-backtick line closes a 4-backtick fence early; commits 383dde6..bdb7ae5)
Task 3: fix round 3/5 (1 addressed, 0 open, no new breakage; commits bdb7ae5..6ae6f3a)
Task 3: complete (commits 8433d10..6ae6f3a, review clean)
Task 3: minor (deferred): the fence-open check widened to `'yaml' in line`, so an info string like ```notyaml would match. Pre-existing style, not probed.
Note: interpreter on this machine is `python3`, not `python`. Carry this in every remaining dispatch.

Task 4: review found 1 Critical + 1 Important + 2 Minor, all plan-mandated.
Task 4: Ruling: an exception escaping a check (malformed `config`, e.g. `length_bands: {h1: 5}`) exits 1 with a traceback — FIX. The spec makes exit 0 vs 2 the loop's entire control flow; a third undocumented state is exactly the ambiguity the design exists to remove. Map any unexpected exception to exit 2, stderr, empty stdout. Cost if wrong: a genuine bug in a check surfaces as "spine failure" rather than a traceback — still stops the loop, which is the safe direction.
Task 4: Ruling: `banned_phrases` misses a multi-word phrase split across a newline, and misses phrases whose edges are non-word characters — FIX. Both are silent false negatives, i.e. banned copy shipping undetected, which is the one failure mode this check exists to prevent. Cost if wrong: slightly broader matching on phrases containing punctuation.
Task 4: minor (deferred): an inverted length band (min > max) always fails rather than erroring cleanly.
Task 4: minor (deferred): a duplicate `<!-- section: X -->` marker concatenates both chunks' word counts rather than erroring.
Task 4: fix round 1/5 (2 addressed, 0 open, no new breakage; commits 27e92ab..77c1243)
Task 4: complete (commits 6ae6f3a..77c1243, review clean)
Task 4: minor (deferred): an empty-string entry in a rubric's `phrases` list matches everything. Pre-existing, not a regression.
Task 4: minor (deferred): `banned_phrases` does not match inflected forms ("leverage" misses "leveraged"). Whole-word anchoring is deliberate; noting it so rubric authors know to list stems explicitly.

Task 5: review found 1 Critical + 1 Important + 5 Minor, all plan-mandated.
Task 5: Ruling: `find_latest_shipped` matches with `endswith(f"-{slug}")`, so looking up `home` returns `new-home`'s shipped copy — FIX. Two real pages silently cross-contaminate and a revision starts from the wrong live copy, with no error anywhere. Match on the run id's dash-delimited slug component instead. Cost if wrong: a stricter matcher misses a legitimately odd run-id shape, and returns None rather than the wrong page — the safe direction.
Task 5: Ruling: empty slug — FIX alongside the above. `slugify("///")` yields "", producing a trailing-dash run id and a lookup target that would match everything once the matcher is tightened. Reject an empty slug at `new_run_id`. Cost if wrong: a caller passing a punctuation-only page name gets a loud error instead of a silently malformed id.
Task 5: Ruling: `new_run_id` stamps `Z` on a naive datetime — FIX. The constraint says timestamps are UTC; labelling an unknown wall-clock as UTC is a lie the trace then carries. Cost if wrong: a caller passing naive datetimes must now be explicit.
Task 5: minor (deferred): `slugify` strips non-ASCII ("Café Déjà" -> "caf-d-j"), which can collide for non-ASCII page names.
Task 5: minor (deferred): `run_dir` does not sanitize `client`/`run_id`, so `..` escapes the memory root. Single-operator local tool, no untrusted input path in V1.
Task 5: minor (deferred): two runs in the same second share a run id and silently overwrite. Inherited from the mandated %Y%m%dT%H%M%SZ format; a counter would complicate the reverse-sort contract.
Task 5: fix round 1/5 (3 addressed, 0 open, no new breakage; commits 1347ef9..6edc306)
Task 5: complete (commits 77c1243..6edc306, review clean)
Task 5: Ruling: a workflow name containing a dash breaks `find_latest_shipped`'s maxsplit=2 component split (`web-copy` yields slug "copy-home"). Rather than reopen Task 5, enforce dash-free workflow names in Task 10's agent-file validator, where workflow names are actually defined. Why: the constraint belongs at the point of declaration, not the point of consumption. Cost if wrong: a future workflow cannot be named with a dash — an underscore or a single word works.
Task 5: minor (deferred): `test_new_run_id_converts_non_utc_aware_datetime` uses +05:00 at 13:05, which does not cross a date boundary despite its comment saying so. Conversion verified correct independently; the test just proves less than it claims.
Task 6: complete (commits 6edc306..91de38d, review clean — 1 Minor deferred)
Task 6: minor (deferred): `validate_trace` accepts `confidence: True/False`, since bool subclasses int and `0.0 <= True <= 1.0` holds. Pre-existing in the brief's code. Worth triaging at final review — the trace is the calibration substrate, so a boolean confidence would poison it silently.

Task 7: review found 3 Important + 2 Minor, all plan-mandated.
Task 7: Ruling: `validate_artifact` and `_sum_metric` raise raw TypeError on malformed shapes (`pages: null`, non-dict `stage_signals`, a string metric) — FIX. A validator whose whole job is to reject malformed input must not itself crash on it; the ingestors call this on freshly parsed CSV, which is exactly where malformed shapes arrive. Cost if wrong: none — same rejection, better error.
Task 7: Ruling: path traversal via `client` (`client="../../evil"` escapes memory_root) — DEFER, paired with the identical Task 5 `run_dir` finding. Why: V1 is single-operator and local with no untrusted input path, and the spec explicitly scopes out multi-tenancy; fixing it here alone would leave the sibling module inconsistent. Both go to the final review to triage together. Cost if wrong: an operator typo in a client name writes outside memory/ — visible, local, recoverable.
Task 7: minor (deferred): extra/unexpected keys silently accepted at artifact, page and stage level. Defensible as forward-compatible, but undocumented.
Task 7: minor (deferred): two artifacts for the same client+source in the same second collide on filename and the second silently overwrites. Same class as the Task 5 same-second run-id collision.
Task 7: fix round 1/5 (2 addressed, 0 open, no new breakage; commits 24aa15c..adda3dc)
Task 7: complete (commits 91de38d..adda3dc, review clean)
Task 8: complete (commits adda3dc..097f2d3, review clean — no findings)
Task 8: minor (deferred): `--source screenshot` is tested directly only for GSC; GA4 shares the identical run_ingest path so it is structurally guaranteed but not separately asserted.
Task 9: complete (commits 097f2d3..296909f, review clean — 2 Minor deferred)
Task 9: minor (deferred): `edit_magnitude` is silently null when draft.md is absent, so "loop never wrote a draft" is indistinguishable from a clean approve. Spec-compliant; worth a warning line later.
Task 9: minor (deferred): no atomicity between writing shipped.md and decision.json — a failure between them leaves shipped copy with no decision record. Surfaced loudly (exit 2) and a retry is idempotent.

Task 10: review found 1 Important + 2 Minor, all plan-mandated.
Task 10: Ruling: section detection is a naive `f"## {s}" in body` substring, so `### Role`, `## Roles`, `## Role and scope`, and a `## Role` inside a fenced block all satisfy the requirement — FIX. The seam's entire justification is catching a malformed agent file before a run does; a check that passes on four kinds of non-section does not do that. Anchor to a line-start `##` with exact heading text, ignoring fenced regions. Cost if wrong: a stricter validator rejects an agent file with an unconventional heading, loudly, at --validate time.
Task 10: Ruling: `--validate` on a nonexistent agents dir exits 0 with empty JSON — FIX alongside. A validator that reports success when pointed at nothing is worse than useless; a typo'd --agents-dir should fail. Cost if wrong: a caller relying on empty-on-missing gets an error instead.
Task 10: minor (deferred): the report claimed the _TEMPLATE.md name-constraint line sits beside the `name` field; it is actually appended after the Escalation section. Substance present, placement claim misleading — folded into the fix dispatch as a move.
Task 10: fix round 1/5 (3 addressed, 0 open, no new breakage; commits d556e91..f823d34)
Task 10: complete (commits 296909f..f823d34, review clean)
Task 10: minor (deferred): `_get_fence_length` in interfaces/delegation.py is a byte-for-byte copy of the helper in tools/rubric.py. Two fence trackers that must stay in step. Candidate for extraction at final review.
Task 10: minor (deferred): `parse_agent(_TEMPLATE.md)` raises a YAML error because the template's frontmatter holds `<placeholder>` values. Harmless today (load_workflows skips underscore files, and the template test does a raw substring check), but it means the template itself is never validated by the validator it documents.

Task 11: implementer returned DONE_WITH_CONCERNS; two concerns are correctness bugs in prompt text that agents execute. Addressing before review.
Task 11: Ruling: `test_research_first_cites_the_real_retrieval_cli` asserts the literal `"python -m interfaces.retrieval"`, but `python` is not on PATH here — only `python3`. So the test forces the skill to instruct an unrunnable command. FIX the assertion to `-m interfaces.retrieval` (interpreter-agnostic, which is what it was actually testing) and use `python3` in the skill text. Why: the assertion's intent was "the skill cites the real retrieval CLI", not "the skill uses this interpreter". Cost if wrong: none — the test still catches skill/tool drift, which is its job.
Task 11: Ruling: gen-eval-loop's payload description omits `mode`, `started_at` and `signal_links`, all of which `tools/trace.py` requires — FIX. An agent following the skill as written would build an invalid payload and get exit 2 on every run, so the loop's "trace, always" step would fail always. Cost if wrong: a slightly longer field list in the skill.
Task 11: minor (deferred): the brief's own skill text said "Exit code 2" while its test matched case-sensitively on lowercase; implementer lowercased that one word. Correct call.
Task 11: review found 2 Important, both plan-mandated (my skill text).
Task 11: Ruling: the gen-eval-loop decision table is not self-consistent at N == cap with an invariant failure — row 1 (regenerate) and row 4 (escalate) both apply and contradict. FIX. The prose below the table resolves it correctly and unhedged, but the table is the part an agent skims, and this is the exact branch the whole design is trying to make unrationalizable. Make the rows mutually exclusive. Cost if wrong: a slightly wordier table.
Task 11: Ruling: research-first cannot distinguish "input missing" from "my query term did not match" — retrieval returns [] for both. FIX. An agent following it literally can escalate on a present-but-poorly-queried voice profile, which blocks generation entirely. Presence is a file check, not a search. Cost if wrong: one extra step in the gate.
Task 11: fix round 1/5 (2 addressed, 1 residual table overlap surfaced; commits f45cee4..cf24138)
Task 11: fix round 2/5 (1 addressed, 0 open, no new breakage; commits cf24138..81f44a9)
Task 11: complete (commits f823d34..81f44a9, review clean)
Task 12: complete (commits 81f44a9..39a1527, review clean — 2 Minor deferred)
Task 12: minor (deferred): `weak_stage`'s mid_healthy gate for the bottom check tests only bounce_rate, not engagement, so with low impressions "bottom" can fire while engagement is unchecked — mildly contradicting the revise.md table's "Engagement healthy" wording for that row.
Task 12: minor (deferred): onboard.md's Tunable rubric section is prose-only while Invariant is literal YAML, so an agent must translate prose to YAML. Reviewer's translation parsed cleanly, but it is an asymmetry worth closing later.

Task 13: review found 2 Minor; both fixed rather than deferred (cheap, and one is decorative-test).
Task 13: Ruling: the e2e test's `find_latest_shipped` assertion survives removing the slug filter entirely — the workspace holds only one shipped run, so it proves nothing about slug matching. FIX by adding a second run with a colliding slug. Why: Task 13 exists to prove wiring, and an assertion that cannot fail is not proof; the Task 5 unit tests cover the function, but the integration claim was unbacked. Cost if wrong: one more fixture run in a test.
Task 13: Ruling: docs/acceptance.md's edit-rate snippet invokes `python -c`, which does not exist here (python3 only). FIX. The operator copy-pastes this to read the project's headline metric; a snippet that errors is worse than none. Cost if wrong: none.
Task 13: fix round 1/5 (2 addressed, 0 open, no new breakage; commits 31013ed..ff7a747)
Task 13: complete (commits 39a1527..ff7a747, review clean)
Task 14: readiness gate green (218 passed, delegation --validate exit 0, tree clean). Task 14 is operator-driven by design — /onboard requires Tayo's real Orban Forest seed material and refuses without it. Handing back rather than proceeding.

FINAL REVIEW (opus, whole branch): 1 Critical, 6 Important, ~8 Minor. Verdict: merge with named fixes first.
Through-line: the Python spine is well tested and the prompt layer is well written, but three tested functions (new_run_id, find_latest_shipped, weak_stage) and two encoding conventions ([source: ...], <!-- section: -->) have no bridge between them. Per-task reviews could not see it — each half was correct in isolation.
Ruling: dispatching ONE fix wave covering C1, I2, I3, I4, I5, I6, I7. Why: these are the blocking set plus two cheap ones on the same through-line. Cost if wrong: rework visible in one commit.
Ruling: NOT taking the reviewer's client_root() consolidation (6 call sites) in this wave, despite agreeing it is the right shape. Why: a refactor across six modules in a final fix wave with only one scoped re-review left is how regressions land. Recorded as the top follow-up. Cost if wrong: the `Orban-Forest` vs `orban-forest` typo case stays open — a second client tree that retrieval never sees.
Ruling: accepting the reviewer's disagreement on I7 (boolean confidence). They are right: performance.py already carries the exact guard, the fix is one line, and the trace is the artifact whose whole purpose is being trustworthy later. Reversing my Task 6 deferral.
Final fix wave: 7 addressed (C1, I2, I3, I4, I5, I6, I7), 0 open, no new breakage; commits ff7a747..81d27c3. Suite 233 passed, tree clean.

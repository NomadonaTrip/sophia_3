# Sophia-Internal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Claude-Code-native internal content system whose web-copy subagent runs a generate→evaluate→regenerate loop against a client-specific rubric, capturing a decision trace on every run.

**Architecture:** The main Claude session is the coordinator, delegating to subagents defined in `.claude/agents/*.md`. The generate→evaluate loop lives once in a skill (`.claude/skills/gen-eval-loop/`); agent files are thin roles that invoke it. A deterministic Python spine (`tools/*.py`) runs machine-checkable criteria and writes traces, invoked from Bash with CLI-in / JSON-out signatures. Memory is markdown under `memory/`, git-tracked, retrieved via grep behind a `Retriever` interface.

**Tech Stack:** Python 3.12 (stdlib + PyYAML only), pytest, git, Claude Code (agents / commands / skills as markdown).

**Spec:** `docs/superpowers/specs/2026-09-04-sophia-internal-design.md`

## Global Constraints

- **Repo root is `/home/nomad/sophia-internal`** (ext4). Never create project files under `/mnt/e` — H-NFR3.
- **Python 3.12.** Only dependency beyond stdlib is `PyYAML`. No network calls, no external services (H-NFR1).
- **All `tools/*.py` are CLI-in / JSON-out.** JSON to stdout, human-readable errors to stderr, non-zero exit on failure.
- **Retrieval never raises on absent paths.** Empty result is `[]` (H-FR6).
- **Absent metrics are `null`, never `0`** in the performance artifact.
- **A criterion's invariant status derives from its rubric section** (`## Invariant` vs `## Tunable`). It is never a field any code or generation step sets.
- **Unknown `check:` names are hard errors**, never skipped criteria.
- **`memory/` is git-tracked; `.env` is git-ignored and never logged** (H-NFR4, H-NFR6).
- **`schema_version` is the string `"1"`** in both the performance artifact and the trace.
- **Timestamps are UTC ISO-8601 with `Z` suffix**, e.g. `2026-09-04T00:00:00Z`.
- Test command throughout: `python -m pytest`. Run from repo root.

---

## File Structure

| File | Responsibility |
|---|---|
| `pyproject.toml` | Package metadata, PyYAML dep, pytest config |
| `interfaces/retrieval.py` | `Hit`, `Retriever` protocol, `GrepRetriever`, module CLI |
| `interfaces/performance.py` | Artifact schema, `StageSignals`/`PageRow`/`PerformanceArtifact`, validator, writer, sample-warning floor |
| `interfaces/delegation.py` | `WorkflowSpec`, agent-frontmatter parser, template validator, `--validate` CLI |
| `tools/rubric.py` | Rubric parsing — shared by `eval.py` and onboarding checks |
| `tools/eval.py` | Deterministic check dispatch table + CLI |
| `tools/trace.py` | Trace schema validation + persistence |
| `tools/ingest_common.py` | Shared CSV→artifact plumbing for both ingestors |
| `tools/ingest_gsc.py` | GSC CSV → normalized artifact |
| `tools/ingest_ga4.py` | GA4 CSV → normalized artifact |
| `tools/approve.py` | Operator decision + shipped-copy persistence + edit magnitude |
| `tools/episodic.py` | Run-directory naming and resolution (shared by trace/approve/revise) |
| `.claude/agents/_TEMPLATE.md` | Agent-file convention |
| `.claude/agents/webcopy.md` | Web copy workflow role |
| `.claude/skills/research-first/SKILL.md` | Pre-generation input gate |
| `.claude/skills/voice-match/SKILL.md` | Voice extraction + matching method |
| `.claude/skills/gen-eval-loop/SKILL.md` | The loop |
| `.claude/commands/*.md` | `onboard`, `webcopy`, `revise`, `client` |
| `CLAUDE.md` | Routing doc |
| `docs/acceptance.md` | §9 acceptance evidence log |

`tools/rubric.py`, `tools/episodic.py`, and `tools/ingest_common.py` are not in the spec's tree but fall out of the responsibilities it assigns: rubric parsing is needed by more than `eval.py`, run-directory naming by three tools, and the two ingestors are otherwise near-duplicates. Splitting them keeps each file to one job.

---

## Task 1: Project skeleton and packaging

**Files:**
- Create: `pyproject.toml`
- Create: `interfaces/__init__.py`, `tools/__init__.py`, `tests/__init__.py`
- Create: `.env.example`
- Create: `tests/test_packaging.py`

**Interfaces:**
- Consumes: nothing
- Produces: importable `interfaces` and `tools` packages; `python -m pytest` runs from repo root

- [ ] **Step 1: Write the failing test**

Create `tests/test_packaging.py`:

```python
"""The package skeleton must be importable and declare its one dependency."""
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_interfaces_package_importable():
    import interfaces  # noqa: F401


def test_tools_package_importable():
    import tools  # noqa: F401


def test_pyyaml_is_declared_and_importable():
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())
    deps = data["project"]["dependencies"]
    assert any(d.lower().startswith("pyyaml") for d in deps), deps
    import yaml  # noqa: F401


def test_env_example_exists_and_env_is_ignored():
    assert (REPO_ROOT / ".env.example").is_file()
    ignored = (REPO_ROOT / ".gitignore").read_text().splitlines()
    assert ".env" in ignored
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_packaging.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'interfaces'`

- [ ] **Step 3: Write minimal implementation**

Create `pyproject.toml`:

```toml
[project]
name = "sophia-internal"
version = "0.1.0"
description = "Internal content system for Orban Forest"
requires-python = ">=3.12"
dependencies = ["PyYAML>=6.0"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools]
packages = ["interfaces", "tools"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
```

Create three empty files: `interfaces/__init__.py`, `tools/__init__.py`, `tests/__init__.py`.

Create `.env.example`:

```
# No secrets are used in V1. This file establishes the convention
# for when analytics or publishing APIs arrive (H-NFR6).
# Copy to .env (git-ignored) and never log its contents.
# GSC_API_KEY=
# GA4_PROPERTY_ID=
```

- [ ] **Step 4: Install the dependency and run the tests**

Run:
```bash
python -m pip install --quiet PyYAML pytest
python -m pytest tests/test_packaging.py -v
```
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml interfaces tools tests .env.example
git commit -m "feat: project skeleton with PyYAML dependency and pytest config"
```

---

## Task 2: Retrieval seam

**Files:**
- Create: `interfaces/retrieval.py`
- Test: `tests/test_retrieval.py`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `Hit` — frozen dataclass with fields `path: str`, `line: int`, `text: str`, `scope: str`
  - `SCOPES: tuple[str, ...]` = `("voice", "business", "icp", "evals", "episodic", "performance")`
  - `Retriever` — Protocol with `search(self, query: str, *, client: str, scope: str | None = None, limit: int = 20) -> list[Hit]`
  - `GrepRetriever(memory_root: Path)` — implements `Retriever`
  - CLI: `python -m interfaces.retrieval --client C --query Q [--scope S] [--limit N]` → JSON list of hit objects

- [ ] **Step 1: Write the failing test**

Create `tests/test_retrieval.py`:

```python
import json
import subprocess
import sys
from pathlib import Path

import pytest

from interfaces.retrieval import SCOPES, GrepRetriever, Hit

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def memory_root(tmp_path: Path) -> Path:
    client = tmp_path / "clients" / "orban-forest"
    (client / "evals").mkdir(parents=True)
    (client / "episodic").mkdir(parents=True)
    (client / "voice.md").write_text(
        "# Voice\nShort sentences. Plain words.\nNever says 'leverage'.\n"
    )
    (client / "business.md").write_text("# Business\nTree surgery in Kent.\n")
    (client / "evals" / "webcopy.md").write_text("# Rubric\nleverage is banned\n")
    return tmp_path


def test_finds_match_across_client_memory(memory_root):
    hits = GrepRetriever(memory_root).search("leverage", client="orban-forest")
    assert len(hits) == 2
    assert {Path(h.path).name for h in hits} == {"voice.md", "webcopy.md"}
    assert all(isinstance(h, Hit) for h in hits)


def test_scope_narrows_to_one_area(memory_root):
    hits = GrepRetriever(memory_root).search(
        "leverage", client="orban-forest", scope="evals"
    )
    assert len(hits) == 1
    assert hits[0].scope == "evals"
    assert Path(hits[0].path).name == "webcopy.md"


def test_hit_carries_line_number_and_text(memory_root):
    hits = GrepRetriever(memory_root).search(
        "Tree surgery", client="orban-forest", scope="business"
    )
    assert hits[0].line == 2
    assert "Tree surgery in Kent." in hits[0].text


def test_no_match_returns_empty_list(memory_root):
    assert GrepRetriever(memory_root).search("nonexistent", client="orban-forest") == []


def test_missing_client_returns_empty_not_error(memory_root):
    """H-FR6: empty results are tolerated; absence is the caller's call to make."""
    assert GrepRetriever(memory_root).search("anything", client="no-such-client") == []


def test_empty_scope_directory_returns_empty(memory_root):
    assert (
        GrepRetriever(memory_root).search(
            "anything", client="orban-forest", scope="episodic"
        )
        == []
    )


def test_limit_caps_results(memory_root):
    hits = GrepRetriever(memory_root).search(
        "leverage", client="orban-forest", limit=1
    )
    assert len(hits) == 1


def test_unknown_scope_is_an_error(memory_root):
    with pytest.raises(ValueError, match="unknown scope"):
        GrepRetriever(memory_root).search("x", client="orban-forest", scope="bogus")


def test_regex_metacharacters_are_matched_literally(memory_root):
    """A query is a phrase, not a pattern; '.' must not match every character."""
    assert (
        GrepRetriever(memory_root).search("Plain.words", client="orban-forest") == []
    )


def test_scopes_tuple_matches_spec():
    assert SCOPES == ("voice", "business", "icp", "evals", "episodic", "performance")


def test_module_cli_emits_json(memory_root):
    proc = subprocess.run(
        [
            sys.executable, "-m", "interfaces.retrieval",
            "--memory-root", str(memory_root),
            "--client", "orban-forest",
            "--query", "leverage",
        ],
        capture_output=True, text=True, check=True, cwd=REPO_ROOT,
    )
    payload = json.loads(proc.stdout)
    assert len(payload) == 2
    assert set(payload[0]) == {"path", "line", "text", "scope"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_retrieval.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'interfaces.retrieval'`

- [ ] **Step 3: Write minimal implementation**

Create `interfaces/retrieval.py`:

```python
"""Retrieval seam. V1 backing is grep over markdown memory.

Per H-FR6 every caller must tolerate empty results, so absence of a client
directory or a scope directory is an empty list, never an exception. Deciding
whether absence is fatal belongs to the caller -- the research-first gate
treats it as fatal; a background lookup does not.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

SCOPES: tuple[str, ...] = (
    "voice", "business", "icp", "evals", "episodic", "performance",
)

# Scopes that name a single file rather than a directory.
_FILE_SCOPES = {"voice": "voice.md", "business": "business.md", "icp": "icp.md"}

DEFAULT_MEMORY_ROOT = Path(__file__).resolve().parent.parent / "memory"


@dataclass(frozen=True)
class Hit:
    path: str
    line: int
    text: str
    scope: str


class Retriever(Protocol):
    def search(
        self, query: str, *, client: str,
        scope: str | None = None, limit: int = 20,
    ) -> list[Hit]: ...


class GrepRetriever:
    """Grep over ``memory/clients/<client>/`` with optional scope narrowing."""

    def __init__(self, memory_root: Path = DEFAULT_MEMORY_ROOT) -> None:
        self.memory_root = Path(memory_root)

    def search(
        self, query: str, *, client: str,
        scope: str | None = None, limit: int = 20,
    ) -> list[Hit]:
        if scope is not None and scope not in SCOPES:
            raise ValueError(f"unknown scope: {scope!r}; expected one of {SCOPES}")

        target = self._target(client, scope)
        if target is None or not target.exists():
            return []

        # -F: fixed string, so a query is a phrase and not a regex.
        # -r: recurse (harmless on a file target). -n: line numbers.
        proc = subprocess.run(
            ["grep", "-rFn", "--", query, str(target)],
            capture_output=True, text=True,
        )
        if proc.returncode not in (0, 1):  # 1 == no match, which is not an error
            return []

        hits: list[Hit] = []
        client_root = self.memory_root / "clients" / client
        for raw in proc.stdout.splitlines():
            parsed = self._parse_grep_line(raw, target)
            if parsed is None:
                continue
            path, line, text = parsed
            hits.append(
                Hit(
                    path=path, line=line, text=text,
                    scope=scope or self._infer_scope(Path(path), client_root),
                )
            )
            if len(hits) >= limit:
                break
        return hits

    def _target(self, client: str, scope: str | None) -> Path | None:
        client_root = self.memory_root / "clients" / client
        if scope is None:
            return client_root
        if scope in _FILE_SCOPES:
            return client_root / _FILE_SCOPES[scope]
        return client_root / scope

    @staticmethod
    def _parse_grep_line(raw: str, target: Path) -> tuple[str, int, str] | None:
        """grep prints ``path:line:text`` for directories, ``line:text`` for files."""
        if target.is_file():
            line_str, _, text = raw.partition(":")
            if not line_str.isdigit():
                return None
            return str(target), int(line_str), text
        path, _, rest = raw.partition(":")
        line_str, _, text = rest.partition(":")
        if not line_str.isdigit():
            return None
        return path, int(line_str), text

    @staticmethod
    def _infer_scope(path: Path, client_root: Path) -> str:
        try:
            rel = path.resolve().relative_to(client_root.resolve())
        except ValueError:
            return "unknown"
        head = rel.parts[0]
        for scope, filename in _FILE_SCOPES.items():
            if head == filename:
                return scope
        return head if head in SCOPES else "unknown"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Search client memory.")
    parser.add_argument("--client", required=True)
    parser.add_argument("--query", required=True)
    parser.add_argument("--scope", choices=SCOPES, default=None)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--memory-root", type=Path, default=DEFAULT_MEMORY_ROOT)
    args = parser.parse_args(argv)

    hits = GrepRetriever(args.memory_root).search(
        args.query, client=args.client, scope=args.scope, limit=args.limit
    )
    print(json.dumps([asdict(h) for h in hits], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_retrieval.py -v`
Expected: 11 passed

- [ ] **Step 5: Commit**

```bash
git add interfaces/retrieval.py tests/test_retrieval.py
git commit -m "feat: grep retrieval behind the Retriever interface"
```

---

## Task 3: Rubric parsing

**Files:**
- Create: `tools/rubric.py`
- Test: `tests/test_rubric.py`
- Create: `tests/fixtures/rubric_valid.md`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `Criterion` — frozen dataclass: `id: str`, `type: str` (`"deterministic"`|`"judgment"`), `invariant: bool`, `check: str | None`, `config: dict`, `criterion: str | None`
  - `Rubric` — frozen dataclass: `criteria: list[Criterion]`, with `deterministic()` and `judgment()` returning filtered lists
  - `load_rubric(path: Path) -> Rubric`
  - `RubricError(Exception)`

- [ ] **Step 1: Write the failing test**

Create `tests/fixtures/rubric_valid.md`:

````markdown
# Web Copy Rubric — orban-forest

## Invariant

```yaml
- id: campfire-voice
  type: judgment
  criterion: >
    Reads as one person talking to another by a fire.
- id: no-fabricated-stats
  type: deterministic
  check: fabricated_stat_scan
```

## Tunable

```yaml
- id: banned-phrases
  type: deterministic
  check: banned_phrases
  config:
    phrases: ["leverage", "unlock"]
- id: hook-strength
  type: judgment
  criterion: The first line earns the second.
```
````

Create `tests/test_rubric.py`:

```python
from pathlib import Path

import pytest

from tools.rubric import Rubric, RubricError, load_rubric

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def rubric() -> Rubric:
    return load_rubric(FIXTURES / "rubric_valid.md")


def test_loads_all_criteria(rubric):
    assert [c.id for c in rubric.criteria] == [
        "campfire-voice", "no-fabricated-stats", "banned-phrases", "hook-strength",
    ]


def test_invariance_derives_from_section_not_a_field(rubric):
    by_id = {c.id: c for c in rubric.criteria}
    assert by_id["campfire-voice"].invariant is True
    assert by_id["no-fabricated-stats"].invariant is True
    assert by_id["banned-phrases"].invariant is False
    assert by_id["hook-strength"].invariant is False


def test_config_is_parsed(rubric):
    by_id = {c.id: c for c in rubric.criteria}
    assert by_id["banned-phrases"].config == {"phrases": ["leverage", "unlock"]}


def test_config_defaults_to_empty_dict(rubric):
    by_id = {c.id: c for c in rubric.criteria}
    assert by_id["no-fabricated-stats"].config == {}


def test_partitions_by_type(rubric):
    assert [c.id for c in rubric.deterministic()] == [
        "no-fabricated-stats", "banned-phrases",
    ]
    assert [c.id for c in rubric.judgment()] == ["campfire-voice", "hook-strength"]


def test_an_invariant_yaml_field_cannot_override_the_section(tmp_path):
    """Invariance is structural. A criterion that claims otherwise is rejected."""
    path = tmp_path / "r.md"
    path.write_text(
        "## Invariant\n\n```yaml\n- id: a\n  type: judgment\n  invariant: false\n"
        "  criterion: x\n```\n\n## Tunable\n\n```yaml\n[]\n```\n"
    )
    with pytest.raises(RubricError, match="invariant"):
        load_rubric(path)


def test_missing_invariant_section_is_an_error(tmp_path):
    path = tmp_path / "r.md"
    path.write_text("## Tunable\n\n```yaml\n[]\n```\n")
    with pytest.raises(RubricError, match="Invariant"):
        load_rubric(path)


def test_missing_tunable_section_is_an_error(tmp_path):
    path = tmp_path / "r.md"
    path.write_text("## Invariant\n\n```yaml\n[]\n```\n")
    with pytest.raises(RubricError, match="Tunable"):
        load_rubric(path)


def test_deterministic_criterion_without_check_is_an_error(tmp_path):
    path = tmp_path / "r.md"
    path.write_text(
        "## Invariant\n\n```yaml\n- id: a\n  type: deterministic\n```\n\n"
        "## Tunable\n\n```yaml\n[]\n```\n"
    )
    with pytest.raises(RubricError, match="check"):
        load_rubric(path)


def test_unknown_type_is_an_error(tmp_path):
    path = tmp_path / "r.md"
    path.write_text(
        "## Invariant\n\n```yaml\n- id: a\n  type: vibes\n```\n\n"
        "## Tunable\n\n```yaml\n[]\n```\n"
    )
    with pytest.raises(RubricError, match="type"):
        load_rubric(path)


def test_duplicate_ids_are_an_error(tmp_path):
    path = tmp_path / "r.md"
    path.write_text(
        "## Invariant\n\n```yaml\n- id: a\n  type: judgment\n  criterion: x\n```\n\n"
        "## Tunable\n\n```yaml\n- id: a\n  type: judgment\n  criterion: y\n```\n"
    )
    with pytest.raises(RubricError, match="duplicate"):
        load_rubric(path)


def test_missing_file_is_an_error(tmp_path):
    with pytest.raises(RubricError, match="not found"):
        load_rubric(tmp_path / "nope.md")


def test_malformed_yaml_is_an_error(tmp_path):
    path = tmp_path / "r.md"
    path.write_text(
        "## Invariant\n\n```yaml\n- id: [unclosed\n```\n\n"
        "## Tunable\n\n```yaml\n[]\n```\n"
    )
    with pytest.raises(RubricError, match="YAML"):
        load_rubric(path)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_rubric.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tools.rubric'`

- [ ] **Step 3: Write minimal implementation**

Create `tools/rubric.py`:

```python
"""Rubric parsing.

The rubric is the operator's control surface: check configuration lives in
markdown, not in Python, so tuning never means editing code. A criterion's
invariance derives from which section it sits in -- never from a field, which
is why a YAML ``invariant`` key is rejected rather than honoured.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

VALID_TYPES = ("deterministic", "judgment")

_SECTION_RE = r"^##\s+{name}\s*$.*?```yaml\s*$(?P<body>.*?)^```\s*$"


class RubricError(Exception):
    """Raised for any malformed or missing rubric. Never recovered from."""


@dataclass(frozen=True)
class Criterion:
    id: str
    type: str
    invariant: bool
    check: str | None = None
    config: dict = field(default_factory=dict)
    criterion: str | None = None


@dataclass(frozen=True)
class Rubric:
    criteria: list[Criterion]

    def deterministic(self) -> list[Criterion]:
        return [c for c in self.criteria if c.type == "deterministic"]

    def judgment(self) -> list[Criterion]:
        return [c for c in self.criteria if c.type == "judgment"]


def load_rubric(path: Path) -> Rubric:
    path = Path(path)
    if not path.is_file():
        raise RubricError(f"rubric not found: {path}")
    text = path.read_text()

    criteria: list[Criterion] = []
    seen: set[str] = set()
    for section, invariant in (("Invariant", True), ("Tunable", False)):
        for entry in _section_entries(text, section, path):
            crit = _build(entry, invariant=invariant, section=section, path=path)
            if crit.id in seen:
                raise RubricError(f"{path}: duplicate criterion id {crit.id!r}")
            seen.add(crit.id)
            criteria.append(crit)
    return Rubric(criteria=criteria)


def _section_entries(text: str, section: str, path: Path) -> list[dict]:
    match = re.search(
        _SECTION_RE.format(name=section), text, re.MULTILINE | re.DOTALL
    )
    if match is None:
        raise RubricError(
            f"{path}: missing '## {section}' section with a fenced yaml block"
        )
    try:
        parsed = yaml.safe_load(match.group("body"))
    except yaml.YAMLError as exc:
        raise RubricError(f"{path}: malformed YAML in '{section}': {exc}") from exc
    if parsed is None:
        return []
    if not isinstance(parsed, list):
        raise RubricError(f"{path}: '{section}' must be a YAML list, got {type(parsed).__name__}")
    return parsed


def _build(entry: object, *, invariant: bool, section: str, path: Path) -> Criterion:
    if not isinstance(entry, dict):
        raise RubricError(f"{path}: '{section}' entries must be mappings, got {entry!r}")
    if "invariant" in entry:
        raise RubricError(
            f"{path}: criterion {entry.get('id')!r} sets 'invariant' explicitly; "
            "invariance is structural and derives from the section it sits in"
        )
    cid = entry.get("id")
    if not cid:
        raise RubricError(f"{path}: '{section}' contains a criterion with no id")
    ctype = entry.get("type")
    if ctype not in VALID_TYPES:
        raise RubricError(
            f"{path}: criterion {cid!r} has type {ctype!r}; expected one of {VALID_TYPES}"
        )
    check = entry.get("check")
    if ctype == "deterministic" and not check:
        raise RubricError(f"{path}: deterministic criterion {cid!r} has no 'check'")
    return Criterion(
        id=cid,
        type=ctype,
        invariant=invariant,
        check=check,
        config=entry.get("config") or {},
        criterion=entry.get("criterion"),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_rubric.py -v`
Expected: 14 passed

- [ ] **Step 5: Commit**

```bash
git add tools/rubric.py tests/test_rubric.py tests/fixtures/rubric_valid.md
git commit -m "feat: rubric parsing with structural invariance"
```

---

## Task 4: Deterministic checks and `eval.py`

**Files:**
- Create: `tools/eval.py`
- Test: `tests/test_eval.py`

**Interfaces:**
- Consumes: `tools.rubric.load_rubric`, `Criterion`, `Rubric`, `RubricError`
- Produces:
  - `CHECKS: dict[str, Callable[[str, dict], tuple[bool, str]]]` — name → `(copy_text, config) -> (passed, detail)`
  - `banned_phrases`, `length_bands`, `passive_rate`, `fabricated_stat_scan` — the four check functions
  - `evaluate(copy_text: str, rubric: Rubric) -> dict` — returns `{"criteria": [...], "invariant_failed": bool}`
  - `UnknownCheckError(Exception)`
  - CLI: `python tools/eval.py --client C --workflow W --copy PATH [--memory-root P]` → JSON to stdout, exit 0 on success (regardless of pass/fail), exit 2 on spine failure

**Length-band semantics:** `length_bands` config maps a section name to `[min_words, max_words]`. Sections in the copy are located by markdown heading comment markers of the form `<!-- section: h1 -->` on the line before the content. A section named in config but absent from the copy is a failure; a section present in the copy but not named in config is ignored.

- [ ] **Step 1: Write the failing test**

Create `tests/test_eval.py`:

```python
import json
import subprocess
import sys
from pathlib import Path

import pytest

from tools.eval import (
    CHECKS,
    UnknownCheckError,
    banned_phrases,
    evaluate,
    fabricated_stat_scan,
    length_bands,
    passive_rate,
)
from tools.rubric import Criterion, Rubric, load_rubric

FIXTURES = Path(__file__).parent / "fixtures"
REPO_ROOT = Path(__file__).resolve().parent.parent


# --- banned_phrases ---

def test_banned_phrases_passes_when_absent():
    passed, detail = banned_phrases("Plain honest words.", {"phrases": ["leverage"]})
    assert passed is True
    assert detail == ""


def test_banned_phrases_fails_and_names_the_phrase():
    passed, detail = banned_phrases(
        "We leverage synergy.", {"phrases": ["leverage", "unlock"]}
    )
    assert passed is False
    assert "leverage" in detail
    assert "unlock" not in detail


def test_banned_phrases_is_case_insensitive():
    passed, _ = banned_phrases("We Leverage things.", {"phrases": ["leverage"]})
    assert passed is False


def test_banned_phrases_matches_whole_words_only():
    """'unlock' must not fire on 'unlockable' being absent -- nor on 'lock'."""
    passed, _ = banned_phrases("The lock is old.", {"phrases": ["unlock"]})
    assert passed is True


# --- length_bands ---

def test_length_bands_passes_within_band():
    copy = "<!-- section: h1 -->\nWe climb trees in Kent\n"
    passed, detail = length_bands(copy, {"h1": [3, 12]})
    assert passed is True, detail


def test_length_bands_fails_when_too_short():
    copy = "<!-- section: h1 -->\nTrees\n"
    passed, detail = length_bands(copy, {"h1": [3, 12]})
    assert passed is False
    assert "h1" in detail and "1" in detail


def test_length_bands_fails_when_too_long():
    copy = "<!-- section: h1 -->\n" + " ".join(["word"] * 20) + "\n"
    passed, detail = length_bands(copy, {"h1": [3, 12]})
    assert passed is False


def test_length_bands_fails_when_named_section_missing():
    passed, detail = length_bands("<!-- section: h1 -->\nHello there now\n", {"hero_subhead": [10, 30]})
    assert passed is False
    assert "hero_subhead" in detail and "missing" in detail.lower()


def test_length_bands_ignores_unnamed_sections():
    copy = "<!-- section: h1 -->\nWe climb trees in Kent\n<!-- section: footer -->\nx\n"
    passed, _ = length_bands(copy, {"h1": [3, 12]})
    assert passed is True


# --- passive_rate ---

def test_passive_rate_passes_on_active_prose():
    copy = "We climb the tree. We cut the branch. We clear the site."
    passed, detail = passive_rate(copy, {"max_rate": 0.15})
    assert passed is True, detail


def test_passive_rate_fails_on_passive_prose():
    copy = (
        "The tree was climbed by us. The branch was cut. "
        "The site was cleared. The invoice was sent."
    )
    passed, detail = passive_rate(copy, {"max_rate": 0.15})
    assert passed is False
    assert "0." in detail


def test_passive_rate_on_empty_copy_passes():
    passed, _ = passive_rate("", {"max_rate": 0.15})
    assert passed is True


# --- fabricated_stat_scan ---

def test_fabricated_stat_scan_passes_when_stat_is_cited():
    copy = "Storm damage rose 40% last year [source: Kent Council 2025]."
    passed, detail = fabricated_stat_scan(copy, {})
    assert passed is True, detail


def test_fabricated_stat_scan_flags_uncited_percentage():
    passed, detail = fabricated_stat_scan("Storm damage rose 40% last year.", {})
    assert passed is False
    assert "40%" in detail


def test_fabricated_stat_scan_flags_uncited_large_number():
    passed, detail = fabricated_stat_scan("We have served 12,000 homeowners.", {})
    assert passed is False
    assert "12,000" in detail


def test_fabricated_stat_scan_ignores_small_bare_numbers():
    """Prices, counts and years are not statistical claims."""
    passed, detail = fabricated_stat_scan(
        "Call us on day 2 of the job in 2026 for 3 quotes.", {}
    )
    assert passed is True, detail


# --- dispatch table ---

def test_checks_table_holds_exactly_the_four_checks():
    assert set(CHECKS) == {
        "banned_phrases", "length_bands", "passive_rate", "fabricated_stat_scan",
    }


# --- evaluate ---

def _rubric(*criteria: Criterion) -> Rubric:
    return Rubric(criteria=list(criteria))


def test_evaluate_reports_each_deterministic_criterion():
    rubric = _rubric(
        Criterion(id="banned-phrases", type="deterministic", invariant=False,
                  check="banned_phrases", config={"phrases": ["leverage"]}),
    )
    result = evaluate("Plain words.", rubric)
    assert result["criteria"] == [
        {"id": "banned-phrases", "type": "deterministic", "invariant": False,
         "status": "pass", "detail": ""}
    ]
    assert result["invariant_failed"] is False


def test_evaluate_skips_judgment_criteria():
    """Judgment criteria are scored by the subagent, not by this tool."""
    rubric = _rubric(
        Criterion(id="campfire-voice", type="judgment", invariant=True,
                  criterion="warm"),
    )
    assert evaluate("anything", rubric)["criteria"] == []


def test_evaluate_sets_invariant_failed_on_invariant_failure():
    rubric = _rubric(
        Criterion(id="no-fabricated-stats", type="deterministic", invariant=True,
                  check="fabricated_stat_scan", config={}),
    )
    result = evaluate("Damage rose 40% last year.", rubric)
    assert result["criteria"][0]["status"] == "fail"
    assert result["invariant_failed"] is True


def test_evaluate_tunable_failure_does_not_set_invariant_failed():
    rubric = _rubric(
        Criterion(id="banned-phrases", type="deterministic", invariant=False,
                  check="banned_phrases", config={"phrases": ["leverage"]}),
    )
    result = evaluate("We leverage things.", rubric)
    assert result["criteria"][0]["status"] == "fail"
    assert result["invariant_failed"] is False


def test_unknown_check_is_a_hard_error_not_a_skipped_criterion():
    rubric = _rubric(
        Criterion(id="x", type="deterministic", invariant=False, check="vibes_check"),
    )
    with pytest.raises(UnknownCheckError, match="vibes_check"):
        evaluate("anything", rubric)


# --- CLI ---

@pytest.fixture
def memory_root(tmp_path: Path) -> Path:
    evals = tmp_path / "clients" / "orban-forest" / "evals"
    evals.mkdir(parents=True)
    (evals / "webcopy.md").write_text((FIXTURES / "rubric_valid.md").read_text())
    return tmp_path


def _run_cli(memory_root: Path, copy_path: Path):
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / "tools" / "eval.py"),
         "--client", "orban-forest", "--workflow", "webcopy",
         "--copy", str(copy_path), "--memory-root", str(memory_root)],
        capture_output=True, text=True,
    )


def test_cli_emits_json_and_exits_zero_on_passing_copy(memory_root, tmp_path):
    copy_path = tmp_path / "copy.md"
    copy_path.write_text("We climb trees. We cut branches.\n")
    proc = _run_cli(memory_root, copy_path)
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["invariant_failed"] is False


def test_cli_exits_zero_when_copy_fails_a_criterion(memory_root, tmp_path):
    """A failing evaluation is a successful run of the tool."""
    copy_path = tmp_path / "copy.md"
    copy_path.write_text("We leverage synergy.\n")
    proc = _run_cli(memory_root, copy_path)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["invariant_failed"] is False


def test_cli_exits_two_on_missing_rubric(tmp_path):
    copy_path = tmp_path / "copy.md"
    copy_path.write_text("x\n")
    proc = _run_cli(tmp_path, copy_path)
    assert proc.returncode == 2
    assert "rubric not found" in proc.stderr
    assert proc.stdout == ""


def test_cli_exits_two_on_missing_copy_file(memory_root, tmp_path):
    proc = _run_cli(memory_root, tmp_path / "absent.md")
    assert proc.returncode == 2
    assert "copy not found" in proc.stderr
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_eval.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tools.eval'`

- [ ] **Step 3: Write minimal implementation**

Create `tools/eval.py`:

```python
#!/usr/bin/env python3
"""Deterministic evaluation of copy against a client rubric (H-FR4).

Machine-checkable criteria only. Judgment criteria are scored by the subagent
against the rubric text and are deliberately absent from the output here.

Exit codes: 0 = the evaluation ran (pass or fail); 2 = the spine failed
(missing rubric, missing copy, unknown check). A spine failure must stop the
loop -- never fall back to judging deterministic criteria by eye.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from tools.rubric import Rubric, RubricError, load_rubric

DEFAULT_MEMORY_ROOT = Path(__file__).resolve().parent.parent / "memory"

_SECTION_MARKER = re.compile(r"^<!--\s*section:\s*(?P<name>[\w-]+)\s*-->\s*$")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_PASSIVE = re.compile(
    r"\b(?:am|is|are|was|were|be|been|being)\b\s+(?:\w+ly\s+)?\w+(?:ed|en)\b",
    re.IGNORECASE,
)
_CITATION = re.compile(r"\[source:[^\]]+\]", re.IGNORECASE)
_PERCENT = re.compile(r"\b\d+(?:\.\d+)?%")
_LARGE_NUMBER = re.compile(r"\b\d{1,3}(?:,\d{3})+\b|\b\d{4,}\b")
_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")


class UnknownCheckError(Exception):
    """A rubric named a check that does not exist. Never silently skipped."""


class SpineError(Exception):
    """Any failure that must stop the loop rather than degrade it."""


# --- checks -----------------------------------------------------------------

def banned_phrases(copy_text: str, config: dict) -> tuple[bool, str]:
    found = [
        p for p in config.get("phrases", [])
        if re.search(rf"\b{re.escape(p)}\b", copy_text, re.IGNORECASE)
    ]
    if found:
        return False, f"banned phrases present: {', '.join(sorted(found))}"
    return True, ""


def length_bands(copy_text: str, config: dict) -> tuple[bool, str]:
    sections = _split_sections(copy_text)
    problems: list[str] = []
    for name, band in config.items():
        low, high = band
        if name not in sections:
            problems.append(f"{name}: missing from copy")
            continue
        count = len(sections[name].split())
        if count < low or count > high:
            problems.append(f"{name}: {count} words, band is {low}-{high}")
    if problems:
        return False, "; ".join(problems)
    return True, ""


def passive_rate(copy_text: str, config: dict) -> tuple[bool, str]:
    max_rate = config.get("max_rate", 0.15)
    sentences = [s for s in _SENTENCE_SPLIT.split(copy_text.strip()) if s.strip()]
    if not sentences:
        return True, ""
    passive = sum(1 for s in sentences if _PASSIVE.search(s))
    rate = passive / len(sentences)
    if rate > max_rate:
        return False, f"passive rate {rate:.2f} exceeds {max_rate:.2f} ({passive}/{len(sentences)})"
    return True, ""


def fabricated_stat_scan(copy_text: str, config: dict) -> tuple[bool, str]:
    """Flag statistical claims with no adjacent citation.

    Deliberately narrow: percentages and numbers of four digits or more, minus
    anything that reads as a year. Prices and small counts are not claims.
    """
    uncited: list[str] = []
    for sentence in _SENTENCE_SPLIT.split(copy_text):
        if _CITATION.search(sentence):
            continue
        candidates = _PERCENT.findall(sentence) + [
            m for m in _LARGE_NUMBER.findall(sentence) if not _YEAR.fullmatch(m)
        ]
        uncited.extend(candidates)
    if uncited:
        return False, f"uncited statistics: {', '.join(uncited)}"
    return True, ""


CHECKS = {
    "banned_phrases": banned_phrases,
    "length_bands": length_bands,
    "passive_rate": passive_rate,
    "fabricated_stat_scan": fabricated_stat_scan,
}


def _split_sections(copy_text: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in copy_text.splitlines():
        marker = _SECTION_MARKER.match(line)
        if marker:
            current = marker.group("name")
            sections.setdefault(current, [])
            continue
        if current is not None:
            sections[current].append(line)
    return {name: "\n".join(lines).strip() for name, lines in sections.items()}


# --- evaluation -------------------------------------------------------------

def evaluate(copy_text: str, rubric: Rubric) -> dict:
    results = []
    invariant_failed = False
    for criterion in rubric.deterministic():
        check = CHECKS.get(criterion.check or "")
        if check is None:
            raise UnknownCheckError(
                f"criterion {criterion.id!r} names unknown check {criterion.check!r}; "
                f"known checks: {', '.join(sorted(CHECKS))}"
            )
        passed, detail = check(copy_text, criterion.config)
        if not passed and criterion.invariant:
            invariant_failed = True
        results.append({
            "id": criterion.id,
            "type": criterion.type,
            "invariant": criterion.invariant,
            "status": "pass" if passed else "fail",
            "detail": detail,
        })
    return {"criteria": results, "invariant_failed": invariant_failed}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate copy against a rubric.")
    parser.add_argument("--client", required=True)
    parser.add_argument("--workflow", required=True)
    parser.add_argument("--copy", required=True, type=Path)
    parser.add_argument("--memory-root", type=Path, default=DEFAULT_MEMORY_ROOT)
    args = parser.parse_args(argv)

    try:
        if not args.copy.is_file():
            raise SpineError(f"copy not found: {args.copy}")
        rubric_path = (
            args.memory_root / "clients" / args.client / "evals" / f"{args.workflow}.md"
        )
        rubric = load_rubric(rubric_path)
        result = evaluate(args.copy.read_text(), rubric)
    except (SpineError, RubricError, UnknownCheckError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Note: the CLI is run as a script in tests, so `tools/eval.py` must resolve `tools.rubric`. Add to the top of `main()`'s module — before the `from tools.rubric import` line — nothing extra is needed *if* pytest's `pythonpath = ["."]` is set (Task 1) **and** the subprocess inherits the repo root on `sys.path`. It does not by default. So `tools/eval.py` begins with:

```python
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))
```

placed immediately after the docstring and before the `from tools.rubric` import. Apply the same three lines to every `tools/*.py` that is executed as a script and imports a sibling module.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_eval.py -v`
Expected: 27 passed

- [ ] **Step 5: Commit**

```bash
git add tools/eval.py tests/test_eval.py
git commit -m "feat: deterministic checks and eval.py CLI"
```

---

## Task 5: Episodic run directories

**Files:**
- Create: `tools/episodic.py`
- Test: `tests/test_episodic.py`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `new_run_id(workflow: str, slug: str, *, now: datetime | None = None) -> str` — returns `"<ts>-<workflow>-<slug>"` with `ts` as `%Y%m%dT%H%M%SZ`
  - `run_dir(memory_root: Path, client: str, run_id: str, *, create: bool = False) -> Path`
  - `find_latest_shipped(memory_root: Path, client: str, slug: str) -> Path | None`
  - `slugify(text: str) -> str`

- [ ] **Step 1: Write the failing test**

Create `tests/test_episodic.py`:

```python
from datetime import datetime, timezone
from pathlib import Path

from tools.episodic import find_latest_shipped, new_run_id, run_dir, slugify


def test_slugify_lowercases_and_hyphenates():
    assert slugify("Services / Tree Surgery") == "services-tree-surgery"


def test_slugify_collapses_repeats_and_trims():
    assert slugify("  --Hello___World!!  ") == "hello-world"


def test_new_run_id_shape():
    now = datetime(2026, 9, 4, 13, 5, 0, tzinfo=timezone.utc)
    assert new_run_id("webcopy", "home", now=now) == "20260904T130500Z-webcopy-home"


def test_run_dir_does_not_create_by_default(tmp_path):
    path = run_dir(tmp_path, "orban-forest", "20260904T130500Z-webcopy-home")
    assert not path.exists()
    assert path == (
        tmp_path / "clients" / "orban-forest" / "episodic"
        / "20260904T130500Z-webcopy-home"
    )


def test_run_dir_creates_when_asked(tmp_path):
    path = run_dir(tmp_path, "orban-forest", "r1", create=True)
    assert path.is_dir()


def test_find_latest_shipped_returns_none_when_absent(tmp_path):
    assert find_latest_shipped(tmp_path, "orban-forest", "home") is None


def test_find_latest_shipped_ignores_runs_without_shipped_copy(tmp_path):
    d = run_dir(tmp_path, "orban-forest", "20260901T000000Z-webcopy-home", create=True)
    (d / "trace.json").write_text("{}")
    assert find_latest_shipped(tmp_path, "orban-forest", "home") is None


def test_find_latest_shipped_picks_most_recent_matching_slug(tmp_path):
    for run_id in (
        "20260901T000000Z-webcopy-home",
        "20260903T000000Z-webcopy-home",
        "20260904T000000Z-webcopy-services",
    ):
        d = run_dir(tmp_path, "orban-forest", run_id, create=True)
        (d / "shipped.md").write_text(run_id)
    found = find_latest_shipped(tmp_path, "orban-forest", "home")
    assert found is not None
    assert found.read_text() == "20260903T000000Z-webcopy-home"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_episodic.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tools.episodic'`

- [ ] **Step 3: Write minimal implementation**

Create `tools/episodic.py`:

```python
"""Episodic run directories.

One directory per run holds run.md, trace.json, shipped.md and decision.json.
Run ids sort lexicographically by time, which is what lets 'most recent shipped
copy for this page' be a sort rather than a scan of file mtimes.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

_TS_FORMAT = "%Y%m%dT%H%M%SZ"
_NON_SLUG = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    return _NON_SLUG.sub("-", text.strip().lower()).strip("-")


def new_run_id(workflow: str, slug: str, *, now: datetime | None = None) -> str:
    stamp = (now or datetime.now(timezone.utc)).strftime(_TS_FORMAT)
    return f"{stamp}-{workflow}-{slugify(slug)}"


def run_dir(
    memory_root: Path, client: str, run_id: str, *, create: bool = False
) -> Path:
    path = Path(memory_root) / "clients" / client / "episodic" / run_id
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def find_latest_shipped(memory_root: Path, client: str, slug: str) -> Path | None:
    """Most recent approved copy for a page, or None if it was never shipped."""
    episodic = Path(memory_root) / "clients" / client / "episodic"
    if not episodic.is_dir():
        return None
    target = slugify(slug)
    candidates = [
        d / "shipped.md"
        for d in sorted(episodic.iterdir(), reverse=True)
        if d.is_dir() and d.name.endswith(f"-{target}") and (d / "shipped.md").is_file()
    ]
    return candidates[0] if candidates else None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_episodic.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add tools/episodic.py tests/test_episodic.py
git commit -m "feat: episodic run directory naming and lookup"
```

---

## Task 6: Trace persistence

**Files:**
- Create: `tools/trace.py`
- Test: `tests/test_trace.py`

**Interfaces:**
- Consumes: `tools.episodic.run_dir`
- Produces:
  - `TRACE_SCHEMA_VERSION = "1"`
  - `validate_trace(payload: dict) -> None` — raises `TraceError` on any violation
  - `write_trace(memory_root: Path, client: str, run_id: str, payload: dict) -> Path`
  - `TraceError(Exception)`
  - CLI: `python tools/trace.py write --client C --run-id ID --payload PATH|-` → JSON `{"written": "<path>"}`, exit 2 on invalid payload

- [ ] **Step 1: Write the failing test**

Create `tests/test_trace.py`:

```python
import json
import subprocess
import sys
from pathlib import Path

import pytest

from tools.trace import TRACE_SCHEMA_VERSION, TraceError, validate_trace, write_trace

REPO_ROOT = Path(__file__).resolve().parent.parent


def valid_payload(**overrides) -> dict:
    payload = {
        "schema_version": TRACE_SCHEMA_VERSION,
        "run_id": "20260904T130500Z-webcopy-home",
        "client": "orban-forest",
        "workflow": "webcopy",
        "mode": "generate",
        "started_at": "2026-09-04T13:05:00Z",
        "iterations": [
            {
                "n": 1,
                "criteria": [
                    {"id": "campfire-voice", "verdict": "fail",
                     "confidence": 0.7, "rationale": "Reads like a brochure."}
                ],
                "deterministic": {"criteria": [], "invariant_failed": False},
                "alternatives_considered": ["Open on the storm instead."],
                "decision": "regenerate",
                "reason": "Invariant voice criterion failed.",
            }
        ],
        "outcome": "passed",
        "iteration_count": 1,
        "escalation": None,
        "signal_links": [],
    }
    payload.update(overrides)
    return payload


def test_valid_payload_passes_validation():
    validate_trace(valid_payload())


def test_missing_required_key_is_rejected():
    payload = valid_payload()
    del payload["outcome"]
    with pytest.raises(TraceError, match="outcome"):
        validate_trace(payload)


def test_wrong_schema_version_is_rejected():
    with pytest.raises(TraceError, match="schema_version"):
        validate_trace(valid_payload(schema_version="2"))


def test_unknown_outcome_is_rejected():
    with pytest.raises(TraceError, match="outcome"):
        validate_trace(valid_payload(outcome="mostly fine"))


def test_unknown_mode_is_rejected():
    with pytest.raises(TraceError, match="mode"):
        validate_trace(valid_payload(mode="freestyle"))


def test_escalated_outcome_requires_a_sticking_point():
    with pytest.raises(TraceError, match="sticking_point"):
        validate_trace(valid_payload(outcome="escalated", escalation=None))


def test_escalated_outcome_with_sticking_point_is_valid():
    validate_trace(
        valid_payload(outcome="escalated", escalation={"sticking_point": "Voice."})
    )


def test_iterations_must_not_be_empty():
    with pytest.raises(TraceError, match="iterations"):
        validate_trace(valid_payload(iterations=[]))


def test_iteration_count_must_match_iterations_length():
    with pytest.raises(TraceError, match="iteration_count"):
        validate_trace(valid_payload(iteration_count=3))


def test_criterion_confidence_must_be_between_zero_and_one():
    payload = valid_payload()
    payload["iterations"][0]["criteria"][0]["confidence"] = 1.7
    with pytest.raises(TraceError, match="confidence"):
        validate_trace(payload)


def test_criterion_requires_a_rationale():
    payload = valid_payload()
    del payload["iterations"][0]["criteria"][0]["rationale"]
    with pytest.raises(TraceError, match="rationale"):
        validate_trace(payload)


def test_signal_links_entries_need_edit_and_signal():
    with pytest.raises(TraceError, match="signal"):
        validate_trace(valid_payload(signal_links=[{"edit": "Tightened the title."}]))


def test_write_trace_persists_to_the_run_directory(tmp_path):
    payload = valid_payload()
    written = write_trace(tmp_path, "orban-forest", payload["run_id"], payload)
    assert written == (
        tmp_path / "clients" / "orban-forest" / "episodic" / payload["run_id"]
        / "trace.json"
    )
    assert json.loads(written.read_text())["client"] == "orban-forest"


def test_write_trace_rejects_invalid_payload_without_writing(tmp_path):
    payload = valid_payload(outcome="nope")
    with pytest.raises(TraceError):
        write_trace(tmp_path, "orban-forest", payload["run_id"], payload)
    assert not (tmp_path / "clients").exists()


def test_cli_writes_from_a_file(tmp_path):
    payload_path = tmp_path / "payload.json"
    payload_path.write_text(json.dumps(valid_payload()))
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "tools" / "trace.py"), "write",
         "--client", "orban-forest",
         "--run-id", "20260904T130500Z-webcopy-home",
         "--payload", str(payload_path),
         "--memory-root", str(tmp_path)],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert Path(json.loads(proc.stdout)["written"]).is_file()


def test_cli_reads_payload_from_stdin(tmp_path):
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "tools" / "trace.py"), "write",
         "--client", "orban-forest",
         "--run-id", "20260904T130500Z-webcopy-home",
         "--payload", "-",
         "--memory-root", str(tmp_path)],
        input=json.dumps(valid_payload()), capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr


def test_cli_exits_two_on_invalid_payload(tmp_path):
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "tools" / "trace.py"), "write",
         "--client", "orban-forest", "--run-id", "r1", "--payload", "-",
         "--memory-root", str(tmp_path)],
        input=json.dumps(valid_payload(outcome="nope")),
        capture_output=True, text=True,
    )
    assert proc.returncode == 2
    assert "outcome" in proc.stderr
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_trace.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tools.trace'`

- [ ] **Step 3: Write minimal implementation**

Create `tools/trace.py`:

```python
#!/usr/bin/env python3
"""Decision-trace persistence (H-FR5).

Every run emits a trace, pass or escalation, even though nothing consumes it
yet. Validation is strict on purpose: a trace that records the wrong thing is
worse than no trace, because it will be trusted later.
"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))

import argparse
import json
import sys
from pathlib import Path

from tools.episodic import run_dir

TRACE_SCHEMA_VERSION = "1"

_REQUIRED = (
    "schema_version", "run_id", "client", "workflow", "mode", "started_at",
    "iterations", "outcome", "iteration_count", "signal_links",
)
_MODES = ("generate", "revise")
_OUTCOMES = ("passed", "escalated")
_VERDICTS = ("pass", "fail")
_DECISIONS = ("regenerate", "pass", "escalate")


class TraceError(Exception):
    """The trace payload is malformed. Never written."""


def validate_trace(payload: dict) -> None:
    if not isinstance(payload, dict):
        raise TraceError(f"trace must be an object, got {type(payload).__name__}")

    missing = [k for k in _REQUIRED if k not in payload]
    if missing:
        raise TraceError(f"trace missing required keys: {', '.join(missing)}")

    if payload["schema_version"] != TRACE_SCHEMA_VERSION:
        raise TraceError(
            f"schema_version must be {TRACE_SCHEMA_VERSION!r}, "
            f"got {payload['schema_version']!r}"
        )
    if payload["mode"] not in _MODES:
        raise TraceError(f"mode must be one of {_MODES}, got {payload['mode']!r}")
    if payload["outcome"] not in _OUTCOMES:
        raise TraceError(
            f"outcome must be one of {_OUTCOMES}, got {payload['outcome']!r}"
        )

    iterations = payload["iterations"]
    if not isinstance(iterations, list) or not iterations:
        raise TraceError("iterations must be a non-empty list")
    if payload["iteration_count"] != len(iterations):
        raise TraceError(
            f"iteration_count is {payload['iteration_count']} but there are "
            f"{len(iterations)} iterations"
        )
    for iteration in iterations:
        _validate_iteration(iteration)

    if payload["outcome"] == "escalated":
        escalation = payload.get("escalation") or {}
        if not escalation.get("sticking_point"):
            raise TraceError(
                "an escalated outcome requires escalation.sticking_point"
            )

    for link in payload["signal_links"]:
        if not isinstance(link, dict) or "edit" not in link or "signal" not in link:
            raise TraceError(f"signal_links entries need 'edit' and 'signal': {link!r}")


def _validate_iteration(iteration: object) -> None:
    if not isinstance(iteration, dict):
        raise TraceError(f"iteration must be an object, got {iteration!r}")
    for key in ("n", "criteria", "deterministic", "decision", "reason"):
        if key not in iteration:
            raise TraceError(f"iteration missing required key: {key}")
    if iteration["decision"] not in _DECISIONS:
        raise TraceError(
            f"iteration decision must be one of {_DECISIONS}, "
            f"got {iteration['decision']!r}"
        )
    for criterion in iteration["criteria"]:
        for key in ("id", "verdict", "confidence", "rationale"):
            if key not in criterion:
                raise TraceError(f"trace criterion missing required key: {key}")
        if criterion["verdict"] not in _VERDICTS:
            raise TraceError(
                f"criterion verdict must be one of {_VERDICTS}, "
                f"got {criterion['verdict']!r}"
            )
        confidence = criterion["confidence"]
        if not isinstance(confidence, (int, float)) or not 0.0 <= confidence <= 1.0:
            raise TraceError(
                f"criterion confidence must be between 0 and 1, got {confidence!r}"
            )


def write_trace(
    memory_root: Path, client: str, run_id: str, payload: dict
) -> Path:
    validate_trace(payload)
    target = run_dir(memory_root, client, run_id, create=True) / "trace.json"
    target.write_text(json.dumps(payload, indent=2) + "\n")
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Persist a decision trace.")
    sub = parser.add_subparsers(dest="command", required=True)
    write = sub.add_parser("write")
    write.add_argument("--client", required=True)
    write.add_argument("--run-id", required=True)
    write.add_argument("--payload", required=True, help="path to JSON, or - for stdin")
    write.add_argument(
        "--memory-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "memory",
    )
    args = parser.parse_args(argv)

    try:
        raw = sys.stdin.read() if args.payload == "-" else Path(args.payload).read_text()
        payload = json.loads(raw)
        written = write_trace(args.memory_root, args.client, args.run_id, payload)
    except (TraceError, json.JSONDecodeError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(json.dumps({"written": str(written)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_trace.py -v`
Expected: 17 passed

- [ ] **Step 5: Commit**

```bash
git add tools/trace.py tests/test_trace.py
git commit -m "feat: decision-trace validation and persistence"
```

---

## Task 7: Performance artifact seam

**Files:**
- Create: `interfaces/performance.py`
- Test: `tests/test_performance.py`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `ARTIFACT_SCHEMA_VERSION = "1"`
  - `MIN_IMPRESSIONS = 100`, `MIN_SESSIONS = 30`
  - `STAGES = ("top", "mid", "bottom")`
  - `TOP_KEYS`, `MID_KEYS`, `BOTTOM_KEYS` — the metric names per stage
  - `empty_stage_signals() -> dict` — all stages present, every metric `None`
  - `build_artifact(client, source, period, pages, *, min_impressions=MIN_IMPRESSIONS, min_sessions=MIN_SESSIONS, now=None) -> dict`
  - `validate_artifact(payload: dict) -> None` raising `ArtifactError`
  - `write_artifact(memory_root: Path, artifact: dict) -> Path`
  - `weak_stage(page: dict) -> str | None` — the funnel-mapping lookup used by revise mode
  - `ArtifactError(Exception)`

**Funnel mapping** (spec §8), evaluated top-down; the first weak stage wins:

| Condition | Returns |
|---|---|
| `top.impressions >= min_impressions` and `top.ctr < 0.02` | `"top"` |
| `top.ctr >= 0.02` and (`mid.bounce_rate > 0.70` or `mid.avg_engagement_s < 15`) | `"mid"` |
| `mid.bounce_rate <= 0.70` and `bottom.conversion_rate < 0.01` | `"bottom"` |
| otherwise | `None` |

Any comparison involving a `None` metric is skipped — an unmeasured stage is never diagnosed as weak.

- [ ] **Step 1: Write the failing test**

Create `tests/test_performance.py`:

```python
import json
from pathlib import Path

import pytest

from interfaces.performance import (
    ARTIFACT_SCHEMA_VERSION,
    MIN_IMPRESSIONS,
    MIN_SESSIONS,
    ArtifactError,
    build_artifact,
    empty_stage_signals,
    validate_artifact,
    weak_stage,
    write_artifact,
)

PERIOD = {"start": "2026-08-01", "end": "2026-08-31"}


def page(url="/home", *, top=None, mid=None, bottom=None, confidence="high") -> dict:
    signals = empty_stage_signals()
    signals["top"].update(top or {})
    signals["mid"].update(mid or {})
    signals["bottom"].update(bottom or {})
    return {"url": url, "row_confidence": confidence, "stage_signals": signals}


# --- shape ---

def test_empty_stage_signals_has_every_stage_with_null_metrics():
    signals = empty_stage_signals()
    assert set(signals) == {"top", "mid", "bottom"}
    assert signals["top"] == {"impressions": None, "ctr": None, "avg_position": None}
    assert signals["mid"] == {
        "sessions": None, "bounce_rate": None, "avg_engagement_s": None
    }
    assert signals["bottom"] == {"conversions": None, "conversion_rate": None}


def test_build_artifact_sets_schema_version_and_timestamp():
    artifact = build_artifact("orban-forest", "gsc", PERIOD, [page()])
    assert artifact["schema_version"] == ARTIFACT_SCHEMA_VERSION
    assert artifact["ingested_at"].endswith("Z")
    assert artifact["client"] == "orban-forest"
    assert artifact["source"] == "gsc"


# --- sample_warning ---

def test_sample_warning_true_below_impression_floor():
    artifact = build_artifact(
        "orban-forest", "gsc", PERIOD,
        [page(top={"impressions": MIN_IMPRESSIONS - 1})],
    )
    assert artifact["sample_warning"] is True


def test_sample_warning_false_above_impression_floor():
    artifact = build_artifact(
        "orban-forest", "gsc", PERIOD,
        [page(top={"impressions": MIN_IMPRESSIONS})],
    )
    assert artifact["sample_warning"] is False


def test_sample_warning_false_above_session_floor():
    artifact = build_artifact(
        "orban-forest", "ga4", PERIOD, [page(mid={"sessions": MIN_SESSIONS})]
    )
    assert artifact["sample_warning"] is False


def test_sample_warning_sums_across_pages():
    artifact = build_artifact(
        "orban-forest", "gsc", PERIOD,
        [page("/a", top={"impressions": 60}), page("/b", top={"impressions": 60})],
    )
    assert artifact["sample_warning"] is False


def test_sample_warning_true_when_all_volume_metrics_are_null():
    artifact = build_artifact("orban-forest", "screenshot", PERIOD, [page()])
    assert artifact["sample_warning"] is True


def test_floors_are_overridable():
    artifact = build_artifact(
        "orban-forest", "gsc", PERIOD, [page(top={"impressions": 5})],
        min_impressions=1,
    )
    assert artifact["sample_warning"] is False


# --- validation ---

def test_valid_artifact_passes():
    validate_artifact(build_artifact("orban-forest", "gsc", PERIOD, [page()]))


def test_unknown_source_is_rejected():
    artifact = build_artifact("orban-forest", "gsc", PERIOD, [page()])
    artifact["source"] = "guesswork"
    with pytest.raises(ArtifactError, match="source"):
        validate_artifact(artifact)


def test_missing_stage_is_rejected():
    artifact = build_artifact("orban-forest", "gsc", PERIOD, [page()])
    del artifact["pages"][0]["stage_signals"]["mid"]
    with pytest.raises(ArtifactError, match="mid"):
        validate_artifact(artifact)


def test_unknown_row_confidence_is_rejected():
    artifact = build_artifact(
        "orban-forest", "gsc", PERIOD, [page(confidence="probably")]
    )
    with pytest.raises(ArtifactError, match="row_confidence"):
        validate_artifact(artifact)


def test_zero_is_not_conflated_with_absent():
    """A page with tracked zero conversions differs from one with no tracking."""
    tracked = page(bottom={"conversions": 0, "conversion_rate": 0.0})
    untracked = page()
    assert tracked["stage_signals"]["bottom"]["conversions"] == 0
    assert untracked["stage_signals"]["bottom"]["conversions"] is None


# --- funnel mapping ---

def test_weak_stage_top_when_impressions_healthy_and_ctr_low():
    assert weak_stage(page(top={"impressions": 5000, "ctr": 0.008})) == "top"


def test_weak_stage_mid_when_ctr_healthy_and_bounce_high():
    assert (
        weak_stage(page(top={"impressions": 5000, "ctr": 0.05},
                        mid={"bounce_rate": 0.85, "avg_engagement_s": 40}))
        == "mid"
    )


def test_weak_stage_mid_when_engagement_low():
    assert (
        weak_stage(page(top={"impressions": 5000, "ctr": 0.05},
                        mid={"bounce_rate": 0.4, "avg_engagement_s": 6}))
        == "mid"
    )


def test_weak_stage_bottom_when_engagement_healthy_and_conversion_low():
    assert (
        weak_stage(page(top={"impressions": 5000, "ctr": 0.05},
                        mid={"bounce_rate": 0.3, "avg_engagement_s": 90},
                        bottom={"conversion_rate": 0.002}))
        == "bottom"
    )


def test_weak_stage_none_when_everything_is_healthy():
    assert (
        weak_stage(page(top={"impressions": 5000, "ctr": 0.05},
                        mid={"bounce_rate": 0.3, "avg_engagement_s": 90},
                        bottom={"conversion_rate": 0.04}))
        is None
    )


def test_weak_stage_ignores_stages_with_no_data():
    """An unmeasured stage is never diagnosed as weak."""
    assert weak_stage(page(top={"impressions": 5000, "ctr": 0.05})) is None


def test_weak_stage_none_when_impressions_below_floor():
    assert weak_stage(page(top={"impressions": 3, "ctr": 0.001})) is None


# --- writing ---

def test_write_artifact_persists_under_client_performance(tmp_path):
    artifact = build_artifact("orban-forest", "gsc", PERIOD, [page()])
    written = write_artifact(tmp_path, artifact)
    assert written.parent == tmp_path / "clients" / "orban-forest" / "performance"
    assert written.suffix == ".json"
    assert json.loads(written.read_text())["client"] == "orban-forest"


def test_write_artifact_rejects_invalid_without_writing(tmp_path):
    artifact = build_artifact("orban-forest", "gsc", PERIOD, [page()])
    artifact["source"] = "guesswork"
    with pytest.raises(ArtifactError):
        write_artifact(tmp_path, artifact)
    assert not (tmp_path / "clients").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_performance.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'interfaces.performance'`

- [ ] **Step 3: Write minimal implementation**

Create `interfaces/performance.py`:

```python
"""Performance-artifact seam.

Every ingestion path emits this one shape, keyed to funnel stage, so revise
mode's diagnosis is a lookup rather than a fresh judgment each time.

Absent metrics are None, never 0: a page with no conversion tracking must not
read as a page with zero conversions.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ARTIFACT_SCHEMA_VERSION = "1"

# Volume floors below which a read is statistically untrustworthy. Revise mode
# must surface the warning rather than suppress the diagnosis (PRD section 11).
MIN_IMPRESSIONS = 100
MIN_SESSIONS = 30

STAGES = ("top", "mid", "bottom")
TOP_KEYS = ("impressions", "ctr", "avg_position")
MID_KEYS = ("sessions", "bounce_rate", "avg_engagement_s")
BOTTOM_KEYS = ("conversions", "conversion_rate")
_STAGE_KEYS = {"top": TOP_KEYS, "mid": MID_KEYS, "bottom": BOTTOM_KEYS}

SOURCES = ("gsc", "ga4", "screenshot")
ROW_CONFIDENCE = ("high", "low")

# Funnel thresholds.
_CTR_FLOOR = 0.02
_BOUNCE_CEILING = 0.70
_ENGAGEMENT_FLOOR_S = 15
_CONVERSION_FLOOR = 0.01


class ArtifactError(Exception):
    """The performance artifact is malformed. Never written, never diagnosed."""


def empty_stage_signals() -> dict:
    return {stage: {key: None for key in keys} for stage, keys in _STAGE_KEYS.items()}


def build_artifact(
    client: str,
    source: str,
    period: dict,
    pages: list[dict],
    *,
    min_impressions: int = MIN_IMPRESSIONS,
    min_sessions: int = MIN_SESSIONS,
    now: datetime | None = None,
) -> dict:
    total_impressions = _sum_metric(pages, "top", "impressions")
    total_sessions = _sum_metric(pages, "mid", "sessions")
    sample_warning = (
        total_impressions < min_impressions and total_sessions < min_sessions
    )
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "client": client,
        "source": source,
        "ingested_at": stamp,
        "period": period,
        "sample_warning": sample_warning,
        "pages": pages,
    }


def _sum_metric(pages: list[dict], stage: str, key: str) -> float:
    total = 0.0
    for page in pages:
        value = page.get("stage_signals", {}).get(stage, {}).get(key)
        if value is not None:
            total += value
    return total


def validate_artifact(payload: dict) -> None:
    if not isinstance(payload, dict):
        raise ArtifactError(f"artifact must be an object, got {type(payload).__name__}")
    for key in (
        "schema_version", "client", "source", "ingested_at",
        "period", "sample_warning", "pages",
    ):
        if key not in payload:
            raise ArtifactError(f"artifact missing required key: {key}")
    if payload["schema_version"] != ARTIFACT_SCHEMA_VERSION:
        raise ArtifactError(
            f"schema_version must be {ARTIFACT_SCHEMA_VERSION!r}, "
            f"got {payload['schema_version']!r}"
        )
    if payload["source"] not in SOURCES:
        raise ArtifactError(f"source must be one of {SOURCES}, got {payload['source']!r}")
    for key in ("start", "end"):
        if key not in payload["period"]:
            raise ArtifactError(f"period missing '{key}'")
    for page in payload["pages"]:
        _validate_page(page)


def _validate_page(page: object) -> None:
    if not isinstance(page, dict):
        raise ArtifactError(f"page must be an object, got {page!r}")
    for key in ("url", "row_confidence", "stage_signals"):
        if key not in page:
            raise ArtifactError(f"page missing required key: {key}")
    if page["row_confidence"] not in ROW_CONFIDENCE:
        raise ArtifactError(
            f"row_confidence must be one of {ROW_CONFIDENCE}, "
            f"got {page['row_confidence']!r}"
        )
    signals = page["stage_signals"]
    for stage, keys in _STAGE_KEYS.items():
        if stage not in signals:
            raise ArtifactError(f"page {page['url']!r} missing stage {stage!r}")
        for key in keys:
            if key not in signals[stage]:
                raise ArtifactError(
                    f"page {page['url']!r} stage {stage!r} missing metric {key!r}"
                )


def weak_stage(page: dict) -> str | None:
    """The funnel stage to act on, or None if nothing is diagnosably weak.

    Evaluated top-down; the earliest weak stage wins, because a page nobody
    clicks cannot have a message-match problem worth diagnosing. Comparisons
    involving a None metric are skipped -- an unmeasured stage is never weak.
    """
    signals = page.get("stage_signals", {})
    top, mid, bottom = signals.get("top", {}), signals.get("mid", {}), signals.get("bottom", {})

    impressions, ctr = top.get("impressions"), top.get("ctr")
    bounce, engagement = mid.get("bounce_rate"), mid.get("avg_engagement_s")
    conversion_rate = bottom.get("conversion_rate")

    if impressions is not None and ctr is not None:
        if impressions >= MIN_IMPRESSIONS and ctr < _CTR_FLOOR:
            return "top"

    ctr_healthy = ctr is not None and ctr >= _CTR_FLOOR
    if ctr_healthy:
        if bounce is not None and bounce > _BOUNCE_CEILING:
            return "mid"
        if engagement is not None and engagement < _ENGAGEMENT_FLOOR_S:
            return "mid"

    mid_healthy = bounce is not None and bounce <= _BOUNCE_CEILING
    if mid_healthy and conversion_rate is not None:
        if conversion_rate < _CONVERSION_FLOOR:
            return "bottom"

    return None


def write_artifact(memory_root: Path, artifact: dict) -> Path:
    validate_artifact(artifact)
    directory = (
        Path(memory_root) / "clients" / artifact["client"] / "performance"
    )
    directory.mkdir(parents=True, exist_ok=True)
    stamp = artifact["ingested_at"].replace(":", "").replace("-", "")
    target = directory / f"{stamp}-{artifact['source']}.json"
    target.write_text(json.dumps(artifact, indent=2) + "\n")
    return target
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_performance.py -v`
Expected: 22 passed

- [ ] **Step 5: Commit**

```bash
git add interfaces/performance.py tests/test_performance.py
git commit -m "feat: performance artifact schema, sample warning and funnel mapping"
```

---

## Task 8: GSC and GA4 ingestion

**Files:**
- Create: `tools/ingest_common.py`
- Create: `tools/ingest_gsc.py`
- Create: `tools/ingest_ga4.py`
- Test: `tests/test_ingest.py`
- Create: `tests/fixtures/gsc_export.csv`, `tests/fixtures/ga4_export.csv`

**Interfaces:**
- Consumes: `interfaces.performance.build_artifact`, `empty_stage_signals`, `write_artifact`, `ArtifactError`
- Produces:
  - `tools.ingest_common.IngestError(Exception)`
  - `tools.ingest_common.read_rows(csv_path: Path, required: tuple[str, ...]) -> list[dict]`
  - `tools.ingest_common.parse_number(raw: str | None) -> float | None`
  - `tools.ingest_common.parse_percent(raw: str | None) -> float | None`
  - `tools.ingest_common.run_ingest(argv, *, source_default, required_columns, to_page) -> int` — shared CLI body
  - `tools.ingest_gsc.to_page(row: dict) -> dict`
  - `tools.ingest_ga4.to_page(row: dict) -> dict`
  - CLI for both: `--client C --csv PATH [--period START:END] [--source screenshot] [--memory-root P]` → JSON `{"written": path, "pages": N, "sample_warning": bool}`, exit 2 on failure

**Column contracts.** GSC export: `Page,Clicks,Impressions,CTR,Position`. GA4 export: `Page path,Sessions,Bounce rate,Average engagement time,Conversions`. Percent columns accept `"2.5%"` or `"0.025"`; a value with `%` is divided by 100. Empty cells become `None`.

- [ ] **Step 1: Write the failing test**

Create `tests/fixtures/gsc_export.csv`:

```csv
Page,Clicks,Impressions,CTR,Position
/,120,5000,2.4%,8.1
/services/tree-surgery,15,4200,0.36%,14.2
/contact,,,,
```

Create `tests/fixtures/ga4_export.csv`:

```csv
Page path,Sessions,Bounce rate,Average engagement time,Conversions
/,900,32.5%,95,36
/services/tree-surgery,410,81.0%,9,2
/contact,50,,,
```

Create `tests/test_ingest.py`:

```python
import json
import subprocess
import sys
from pathlib import Path

import pytest

from tools.ingest_common import IngestError, parse_number, parse_percent, read_rows
from tools.ingest_ga4 import to_page as ga4_to_page
from tools.ingest_gsc import to_page as gsc_to_page

FIXTURES = Path(__file__).parent / "fixtures"
REPO_ROOT = Path(__file__).resolve().parent.parent


# --- parsing helpers ---

def test_parse_number_handles_thousands_separators():
    assert parse_number("5,000") == 5000.0


def test_parse_number_returns_none_for_blank():
    assert parse_number("") is None
    assert parse_number(None) is None


def test_parse_number_rejects_garbage():
    with pytest.raises(IngestError, match="number"):
        parse_number("about five")


def test_parse_percent_converts_percentage_sign():
    assert parse_percent("2.4%") == pytest.approx(0.024)


def test_parse_percent_passes_through_a_ratio():
    assert parse_percent("0.024") == pytest.approx(0.024)


def test_parse_percent_returns_none_for_blank():
    assert parse_percent("") is None


def test_read_rows_requires_declared_columns(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("Page,Clicks\n/,1\n")
    with pytest.raises(IngestError, match="Impressions"):
        read_rows(path, ("Page", "Clicks", "Impressions"))


def test_read_rows_reports_a_missing_file(tmp_path):
    with pytest.raises(IngestError, match="not found"):
        read_rows(tmp_path / "absent.csv", ("Page",))


def test_read_rows_rejects_an_empty_file(tmp_path):
    path = tmp_path / "empty.csv"
    path.write_text("")
    with pytest.raises(IngestError, match="empty"):
        read_rows(path, ("Page",))


# --- row mapping ---

def test_gsc_row_maps_to_top_stage_only():
    rows = read_rows(FIXTURES / "gsc_export.csv",
                     ("Page", "Clicks", "Impressions", "CTR", "Position"))
    page = gsc_to_page(rows[0])
    assert page["url"] == "/"
    assert page["stage_signals"]["top"] == {
        "impressions": 5000.0, "ctr": pytest.approx(0.024), "avg_position": 8.1
    }
    assert page["stage_signals"]["mid"]["sessions"] is None
    assert page["stage_signals"]["bottom"]["conversions"] is None


def test_gsc_blank_row_becomes_all_none_not_zero():
    rows = read_rows(FIXTURES / "gsc_export.csv",
                     ("Page", "Clicks", "Impressions", "CTR", "Position"))
    page = gsc_to_page(rows[2])
    assert page["url"] == "/contact"
    assert page["stage_signals"]["top"] == {
        "impressions": None, "ctr": None, "avg_position": None
    }


def test_ga4_row_maps_to_mid_and_bottom_stages():
    rows = read_rows(
        FIXTURES / "ga4_export.csv",
        ("Page path", "Sessions", "Bounce rate", "Average engagement time",
         "Conversions"),
    )
    page = ga4_to_page(rows[0])
    assert page["url"] == "/"
    assert page["stage_signals"]["mid"] == {
        "sessions": 900.0, "bounce_rate": pytest.approx(0.325),
        "avg_engagement_s": 95.0,
    }
    assert page["stage_signals"]["bottom"]["conversions"] == 36.0
    assert page["stage_signals"]["bottom"]["conversion_rate"] == pytest.approx(0.04)


def test_ga4_conversion_rate_is_none_without_sessions():
    page = ga4_to_page({
        "Page path": "/x", "Sessions": "", "Bounce rate": "",
        "Average engagement time": "", "Conversions": "3",
    })
    assert page["stage_signals"]["bottom"]["conversion_rate"] is None


def test_row_confidence_defaults_to_high():
    rows = read_rows(FIXTURES / "gsc_export.csv",
                     ("Page", "Clicks", "Impressions", "CTR", "Position"))
    assert gsc_to_page(rows[0])["row_confidence"] == "high"


# --- CLI ---

def _ingest(tool: str, csv_path: Path, memory_root: Path, *extra: str):
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / "tools" / tool),
         "--client", "orban-forest", "--csv", str(csv_path),
         "--period", "2026-08-01:2026-08-31",
         "--memory-root", str(memory_root), *extra],
        capture_output=True, text=True,
    )


def test_gsc_cli_writes_an_artifact(tmp_path):
    proc = _ingest("ingest_gsc.py", FIXTURES / "gsc_export.csv", tmp_path)
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["pages"] == 3
    artifact = json.loads(Path(result["written"]).read_text())
    assert artifact["source"] == "gsc"
    assert artifact["period"] == {"start": "2026-08-01", "end": "2026-08-31"}
    assert artifact["sample_warning"] is False


def test_ga4_cli_writes_an_artifact(tmp_path):
    proc = _ingest("ingest_ga4.py", FIXTURES / "ga4_export.csv", tmp_path)
    assert proc.returncode == 0, proc.stderr
    artifact = json.loads(Path(json.loads(proc.stdout)["written"]).read_text())
    assert artifact["source"] == "ga4"


def test_screenshot_source_marks_every_row_low_confidence(tmp_path):
    """Screenshots are a lossy fallback; the hierarchy lives in the data."""
    proc = _ingest(
        "ingest_gsc.py", FIXTURES / "gsc_export.csv", tmp_path,
        "--source", "screenshot",
    )
    assert proc.returncode == 0, proc.stderr
    artifact = json.loads(Path(json.loads(proc.stdout)["written"]).read_text())
    assert artifact["source"] == "screenshot"
    assert {p["row_confidence"] for p in artifact["pages"]} == {"low"}


def test_cli_exits_two_on_missing_columns(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("Page,Clicks\n/,1\n")
    proc = _ingest("ingest_gsc.py", bad, tmp_path)
    assert proc.returncode == 2
    assert "Impressions" in proc.stderr
    assert proc.stdout == ""


def test_cli_exits_two_on_malformed_period(tmp_path):
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "tools" / "ingest_gsc.py"),
         "--client", "orban-forest", "--csv", str(FIXTURES / "gsc_export.csv"),
         "--period", "August", "--memory-root", str(tmp_path)],
        capture_output=True, text=True,
    )
    assert proc.returncode == 2
    assert "period" in proc.stderr
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ingest.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tools.ingest_common'`

- [ ] **Step 3: Write minimal implementation**

Create `tools/ingest_common.py`:

```python
"""Shared CSV-to-artifact plumbing for the ingestors (H-FR8).

CSV is the source of truth. Screenshot ingestion reuses this exact path with
--source screenshot, which marks every row low-confidence, so the lossiness is
visible in the data rather than asserted in a document.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Callable

from interfaces.performance import ArtifactError, build_artifact, write_artifact

DEFAULT_MEMORY_ROOT = Path(__file__).resolve().parent.parent / "memory"


class IngestError(Exception):
    """The export could not be read. Never partially ingested."""


def parse_number(raw: str | None) -> float | None:
    if raw is None:
        return None
    text = raw.strip().replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError as exc:
        raise IngestError(f"expected a number, got {raw!r}") from exc


def parse_percent(raw: str | None) -> float | None:
    if raw is None:
        return None
    text = raw.strip()
    if not text:
        return None
    if text.endswith("%"):
        value = parse_number(text[:-1])
        return None if value is None else value / 100.0
    return parse_number(text)


def read_rows(csv_path: Path, required: tuple[str, ...]) -> list[dict]:
    path = Path(csv_path)
    if not path.is_file():
        raise IngestError(f"export not found: {path}")
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise IngestError(f"export is empty: {path}")
        missing = [c for c in required if c not in reader.fieldnames]
        if missing:
            raise IngestError(
                f"{path}: export missing required columns: {', '.join(missing)}"
            )
        return list(reader)


def parse_period(raw: str | None) -> dict:
    if not raw:
        return {"start": None, "end": None}
    start, sep, end = raw.partition(":")
    if not sep or not start.strip() or not end.strip():
        raise IngestError(f"period must be START:END, got {raw!r}")
    return {"start": start.strip(), "end": end.strip()}


def run_ingest(
    argv: list[str] | None,
    *,
    source_default: str,
    required_columns: tuple[str, ...],
    to_page: Callable[[dict], dict],
) -> int:
    parser = argparse.ArgumentParser(
        description=f"Ingest a {source_default.upper()} export into a performance artifact."
    )
    parser.add_argument("--client", required=True)
    parser.add_argument("--csv", required=True, type=Path)
    parser.add_argument("--period", default=None, help="START:END, e.g. 2026-08-01:2026-08-31")
    parser.add_argument("--source", choices=[source_default, "screenshot"], default=source_default)
    parser.add_argument("--memory-root", type=Path, default=DEFAULT_MEMORY_ROOT)
    args = parser.parse_args(argv)

    try:
        period = parse_period(args.period)
        rows = read_rows(args.csv, required_columns)
        pages = [to_page(row) for row in rows]
        if args.source == "screenshot":
            for page in pages:
                page["row_confidence"] = "low"
        artifact = build_artifact(args.client, args.source, period, pages)
        written = write_artifact(args.memory_root, artifact)
    except (IngestError, ArtifactError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(json.dumps({
        "written": str(written),
        "pages": len(pages),
        "sample_warning": artifact["sample_warning"],
    }, indent=2))
    return 0
```

Create `tools/ingest_gsc.py`:

```python
#!/usr/bin/env python3
"""Google Search Console CSV -> normalized performance artifact.

GSC sees the top of the funnel only: impressions, click-through, position.
Mid and bottom stages stay null rather than zero.
"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))

from interfaces.performance import empty_stage_signals
from tools.ingest_common import parse_number, parse_percent, run_ingest

REQUIRED_COLUMNS = ("Page", "Clicks", "Impressions", "CTR", "Position")


def to_page(row: dict) -> dict:
    signals = empty_stage_signals()
    signals["top"] = {
        "impressions": parse_number(row.get("Impressions")),
        "ctr": parse_percent(row.get("CTR")),
        "avg_position": parse_number(row.get("Position")),
    }
    return {
        "url": row["Page"].strip(),
        "row_confidence": "high",
        "stage_signals": signals,
    }


if __name__ == "__main__":
    raise SystemExit(
        run_ingest(
            None,
            source_default="gsc",
            required_columns=REQUIRED_COLUMNS,
            to_page=to_page,
        )
    )
```

Create `tools/ingest_ga4.py`:

```python
#!/usr/bin/env python3
"""Google Analytics 4 CSV -> normalized performance artifact.

GA4 sees mid and bottom: sessions, bounce, engagement, conversions. Conversion
rate is derived, and stays null when sessions are unknown rather than dividing
by an assumed denominator.
"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))

from interfaces.performance import empty_stage_signals
from tools.ingest_common import parse_number, parse_percent, run_ingest

REQUIRED_COLUMNS = (
    "Page path", "Sessions", "Bounce rate", "Average engagement time", "Conversions",
)


def to_page(row: dict) -> dict:
    sessions = parse_number(row.get("Sessions"))
    conversions = parse_number(row.get("Conversions"))
    conversion_rate = (
        conversions / sessions
        if sessions not in (None, 0) and conversions is not None
        else None
    )
    signals = empty_stage_signals()
    signals["mid"] = {
        "sessions": sessions,
        "bounce_rate": parse_percent(row.get("Bounce rate")),
        "avg_engagement_s": parse_number(row.get("Average engagement time")),
    }
    signals["bottom"] = {
        "conversions": conversions,
        "conversion_rate": conversion_rate,
    }
    return {
        "url": row["Page path"].strip(),
        "row_confidence": "high",
        "stage_signals": signals,
    }


if __name__ == "__main__":
    raise SystemExit(
        run_ingest(
            None,
            source_default="ga4",
            required_columns=REQUIRED_COLUMNS,
            to_page=to_page,
        )
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_ingest.py -v`
Expected: 19 passed

- [ ] **Step 5: Commit**

```bash
git add tools/ingest_common.py tools/ingest_gsc.py tools/ingest_ga4.py \
        tests/test_ingest.py tests/fixtures/gsc_export.csv tests/fixtures/ga4_export.csv
git commit -m "feat: GSC and GA4 ingestion into the normalized artifact"
```

---

## Task 9: Approval and shipped-copy persistence

**Files:**
- Create: `tools/approve.py`
- Test: `tests/test_approve.py`

**Interfaces:**
- Consumes: `tools.episodic.run_dir`
- Produces:
  - `DECISIONS = ("approve", "edit", "reject")`
  - `edit_magnitude(draft: str, final: str) -> int` — changed lines via `difflib`
  - `record_decision(memory_root, client, run_id, decision, *, copy_path=None, note=None, now=None) -> dict`
  - `ApprovalError(Exception)`
  - CLI: `python tools/approve.py --client C --run-id ID --decision D [--copy PATH] [--note TEXT]` → JSON of the decision record, exit 2 on failure

**Semantics.** `approve` and `edit` both require `--copy` and both write `shipped.md` (H-FR9) — an edited draft is still shipped copy. `reject` must not supply `--copy` and writes no `shipped.md`. `edit_magnitude` is computed against `draft.md` in the run directory, which the loop writes before handing copy to the operator; it is `null` for `approve` and `reject`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_approve.py`:

```python
import json
import subprocess
import sys
from pathlib import Path

import pytest

from tools.approve import ApprovalError, edit_magnitude, record_decision
from tools.episodic import run_dir

REPO_ROOT = Path(__file__).resolve().parent.parent
RUN_ID = "20260904T130500Z-webcopy-home"


@pytest.fixture
def staged(tmp_path: Path) -> Path:
    d = run_dir(tmp_path, "orban-forest", RUN_ID, create=True)
    (d / "draft.md").write_text("One\nTwo\nThree\n")
    return tmp_path


# --- edit magnitude ---

def test_edit_magnitude_zero_when_identical():
    assert edit_magnitude("a\nb\n", "a\nb\n") == 0


def test_edit_magnitude_counts_changed_lines():
    assert edit_magnitude("a\nb\nc\n", "a\nB\nc\n") == 2  # one removed, one added


def test_edit_magnitude_counts_pure_additions():
    assert edit_magnitude("a\n", "a\nb\n") == 1


# --- record_decision ---

def test_approve_writes_shipped_copy(staged):
    copy_path = staged / "final.md"
    copy_path.write_text("One\nTwo\nThree\n")
    record = record_decision(
        staged, "orban-forest", RUN_ID, "approve", copy_path=copy_path
    )
    shipped = run_dir(staged, "orban-forest", RUN_ID) / "shipped.md"
    assert shipped.read_text() == "One\nTwo\nThree\n"
    assert record["decision"] == "approve"
    assert record["edit_magnitude"] is None
    assert record["decided_at"].endswith("Z")


def test_edit_writes_shipped_copy_and_records_magnitude(staged):
    copy_path = staged / "final.md"
    copy_path.write_text("One\nTWO\nThree\n")
    record = record_decision(
        staged, "orban-forest", RUN_ID, "edit", copy_path=copy_path,
        note="Tightened the second line.",
    )
    assert (run_dir(staged, "orban-forest", RUN_ID) / "shipped.md").is_file()
    assert record["edit_magnitude"] == 2
    assert record["note"] == "Tightened the second line."


def test_reject_writes_no_shipped_copy(staged):
    record = record_decision(
        staged, "orban-forest", RUN_ID, "reject", note="Wrong angle entirely."
    )
    assert not (run_dir(staged, "orban-forest", RUN_ID) / "shipped.md").exists()
    assert record["decision"] == "reject"
    assert record["edit_magnitude"] is None


def test_decision_record_is_persisted(staged):
    copy_path = staged / "final.md"
    copy_path.write_text("One\nTwo\nThree\n")
    record_decision(staged, "orban-forest", RUN_ID, "approve", copy_path=copy_path)
    persisted = json.loads(
        (run_dir(staged, "orban-forest", RUN_ID) / "decision.json").read_text()
    )
    assert persisted["run_id"] == RUN_ID
    assert persisted["client"] == "orban-forest"


def test_edit_magnitude_is_null_when_no_draft_exists(tmp_path):
    run_dir(tmp_path, "orban-forest", RUN_ID, create=True)
    copy_path = tmp_path / "final.md"
    copy_path.write_text("x\n")
    record = record_decision(
        tmp_path, "orban-forest", RUN_ID, "edit", copy_path=copy_path
    )
    assert record["edit_magnitude"] is None


def test_unknown_decision_is_rejected(staged):
    with pytest.raises(ApprovalError, match="decision"):
        record_decision(staged, "orban-forest", RUN_ID, "maybe")


def test_approve_without_copy_is_rejected(staged):
    with pytest.raises(ApprovalError, match="requires --copy"):
        record_decision(staged, "orban-forest", RUN_ID, "approve")


def test_reject_with_copy_is_rejected(staged):
    copy_path = staged / "final.md"
    copy_path.write_text("x\n")
    with pytest.raises(ApprovalError, match="reject"):
        record_decision(
            staged, "orban-forest", RUN_ID, "reject", copy_path=copy_path
        )


def test_missing_run_directory_is_rejected(tmp_path):
    copy_path = tmp_path / "final.md"
    copy_path.write_text("x\n")
    with pytest.raises(ApprovalError, match="run directory"):
        record_decision(
            tmp_path, "orban-forest", "no-such-run", "approve", copy_path=copy_path
        )


# --- CLI ---

def test_cli_records_an_approval(staged):
    copy_path = staged / "final.md"
    copy_path.write_text("One\nTwo\nThree\n")
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "tools" / "approve.py"),
         "--client", "orban-forest", "--run-id", RUN_ID,
         "--decision", "approve", "--copy", str(copy_path),
         "--memory-root", str(staged)],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["decision"] == "approve"


def test_cli_exits_two_on_bad_input(staged):
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "tools" / "approve.py"),
         "--client", "orban-forest", "--run-id", RUN_ID,
         "--decision", "approve", "--memory-root", str(staged)],
        capture_output=True, text=True,
    )
    assert proc.returncode == 2
    assert "requires --copy" in proc.stderr
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_approve.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tools.approve'`

- [ ] **Step 3: Write minimal implementation**

Create `tools/approve.py`:

```python
#!/usr/bin/env python3
"""Operator decision and shipped-copy persistence (H-FR9, H-FR10).

Judgment stays conversational in the Claude session; this tool only persists
what was decided. Edit magnitude is captured here because acceptance criterion
9.1 ('operator edit rate trends down') is unmeasurable after the fact if the
size of the edit is not recorded at the moment of approval.
"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))

import argparse
import difflib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from tools.episodic import run_dir

DECISIONS = ("approve", "edit", "reject")
_SHIPPING = ("approve", "edit")


class ApprovalError(Exception):
    """The decision could not be recorded. Nothing is written."""


def edit_magnitude(draft: str, final: str) -> int:
    """Lines changed between the delivered draft and what the operator shipped."""
    diff = difflib.ndiff(draft.splitlines(), final.splitlines())
    return sum(1 for line in diff if line.startswith(("+ ", "- ")))


def record_decision(
    memory_root: Path,
    client: str,
    run_id: str,
    decision: str,
    *,
    copy_path: Path | None = None,
    note: str | None = None,
    now: datetime | None = None,
) -> dict:
    if decision not in DECISIONS:
        raise ApprovalError(
            f"decision must be one of {DECISIONS}, got {decision!r}"
        )

    directory = run_dir(memory_root, client, run_id)
    if not directory.is_dir():
        raise ApprovalError(f"run directory does not exist: {directory}")

    if decision in _SHIPPING and copy_path is None:
        raise ApprovalError(f"decision {decision!r} requires --copy")
    if decision == "reject" and copy_path is not None:
        raise ApprovalError("decision 'reject' must not supply --copy")

    magnitude: int | None = None
    if decision in _SHIPPING:
        copy_path = Path(copy_path)
        if not copy_path.is_file():
            raise ApprovalError(f"copy not found: {copy_path}")
        final = copy_path.read_text()
        if decision == "edit":
            draft_path = directory / "draft.md"
            if draft_path.is_file():
                magnitude = edit_magnitude(draft_path.read_text(), final)
        (directory / "shipped.md").write_text(final)

    record = {
        "run_id": run_id,
        "client": client,
        "decision": decision,
        "decided_at": (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "edit_magnitude": magnitude,
        "note": note,
    }
    (directory / "decision.json").write_text(json.dumps(record, indent=2) + "\n")
    return record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Record an operator decision.")
    parser.add_argument("--client", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--decision", required=True, choices=DECISIONS)
    parser.add_argument("--copy", type=Path, default=None)
    parser.add_argument("--note", default=None)
    parser.add_argument(
        "--memory-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "memory",
    )
    args = parser.parse_args(argv)

    try:
        record = record_decision(
            args.memory_root, args.client, args.run_id, args.decision,
            copy_path=args.copy, note=args.note,
        )
    except ApprovalError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(json.dumps(record, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_approve.py -v`
Expected: 14 passed

- [ ] **Step 5: Commit**

```bash
git add tools/approve.py tests/test_approve.py
git commit -m "feat: approval, shipped-copy persistence and edit magnitude"
```

---

## Task 10: Agent template and the delegation seam

**Files:**
- Create: `.claude/agents/_TEMPLATE.md`
- Create: `.claude/agents/webcopy.md`
- Create: `interfaces/delegation.py`
- Test: `tests/test_delegation.py`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `REQUIRED_SECTIONS = ("Role", "Memory to load", "Rubric", "Loop", "Escalation")`
  - `REQUIRED_FRONTMATTER = ("name", "description", "tools", "model")`
  - `WorkflowSpec` — frozen dataclass: `name`, `description`, `agent_file`, `rubric_path`, `modes: list[str]`, `tools: list[str]`
  - `parse_agent(path: Path) -> WorkflowSpec`
  - `load_workflows(agents_dir: Path) -> list[WorkflowSpec]` — skips files whose name starts with `_`
  - `DelegationError(Exception)`
  - CLI: `python -m interfaces.delegation --validate [--agents-dir P]` → JSON list of specs, exit 2 on any malformed agent file

**Frontmatter contract.** YAML between `---` fences at the top of the file. `tools` and `modes` are YAML lists. `rubric_path` is a path relative to `memory/clients/<client>/`, e.g. `evals/webcopy.md`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_delegation.py`:

```python
import json
import subprocess
import sys
from pathlib import Path

import pytest

from interfaces.delegation import (
    REQUIRED_FRONTMATTER,
    REQUIRED_SECTIONS,
    DelegationError,
    load_workflows,
    parse_agent,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
AGENTS_DIR = REPO_ROOT / ".claude" / "agents"

GOOD_AGENT = """---
name: sample
description: A sample workflow.
tools: [Read, Write, Bash]
model: opus
modes: [generate, revise]
rubric_path: evals/sample.md
---

## Role

Do the sample thing.

## Memory to load

voice.md, business.md, icp.md

## Rubric

evals/sample.md

## Loop

Invoke the gen-eval-loop skill.

## Escalation

Escalate at the cap.
"""


def test_real_webcopy_agent_parses():
    spec = parse_agent(AGENTS_DIR / "webcopy.md")
    assert spec.name == "webcopy"
    assert spec.rubric_path == "evals/webcopy.md"
    assert "generate" in spec.modes and "revise" in spec.modes
    assert spec.tools


def test_template_declares_every_required_section():
    text = (AGENTS_DIR / "_TEMPLATE.md").read_text()
    for section in REQUIRED_SECTIONS:
        assert f"## {section}" in text, section


def test_load_workflows_skips_underscore_files():
    names = [s.name for s in load_workflows(AGENTS_DIR)]
    assert "webcopy" in names
    assert not any(n.startswith("_") for n in names)


def test_parse_agent_reads_frontmatter(tmp_path):
    path = tmp_path / "sample.md"
    path.write_text(GOOD_AGENT)
    spec = parse_agent(path)
    assert spec.description == "A sample workflow."
    assert spec.tools == ["Read", "Write", "Bash"]
    assert spec.agent_file == str(path)


def test_missing_frontmatter_is_an_error(tmp_path):
    path = tmp_path / "sample.md"
    path.write_text("## Role\n\nNo frontmatter here.\n")
    with pytest.raises(DelegationError, match="frontmatter"):
        parse_agent(path)


@pytest.mark.parametrize("field", REQUIRED_FRONTMATTER)
def test_each_required_frontmatter_field_is_enforced(tmp_path, field):
    lines = [ln for ln in GOOD_AGENT.splitlines() if not ln.startswith(f"{field}:")]
    path = tmp_path / "sample.md"
    path.write_text("\n".join(lines))
    with pytest.raises(DelegationError, match=field):
        parse_agent(path)


@pytest.mark.parametrize("section", REQUIRED_SECTIONS)
def test_each_required_section_is_enforced(tmp_path, section):
    path = tmp_path / "sample.md"
    path.write_text(GOOD_AGENT.replace(f"## {section}", "## Something Else"))
    with pytest.raises(DelegationError, match=section):
        parse_agent(path)


def test_tools_must_be_a_list(tmp_path):
    path = tmp_path / "sample.md"
    path.write_text(GOOD_AGENT.replace("tools: [Read, Write, Bash]", "tools: Read"))
    with pytest.raises(DelegationError, match="tools"):
        parse_agent(path)


def test_cli_validate_emits_specs_and_exits_zero():
    proc = subprocess.run(
        [sys.executable, "-m", "interfaces.delegation", "--validate",
         "--agents-dir", str(AGENTS_DIR)],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    assert proc.returncode == 0, proc.stderr
    assert "webcopy" in {s["name"] for s in json.loads(proc.stdout)}


def test_cli_validate_exits_two_on_a_malformed_agent(tmp_path):
    (tmp_path / "broken.md").write_text("no frontmatter\n")
    proc = subprocess.run(
        [sys.executable, "-m", "interfaces.delegation", "--validate",
         "--agents-dir", str(tmp_path)],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    assert proc.returncode == 2
    assert "frontmatter" in proc.stderr
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_delegation.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'interfaces.delegation'`

- [ ] **Step 3: Write minimal implementation**

Create `.claude/agents/_TEMPLATE.md`:

```markdown
---
name: <workflow-name>
description: <one line: what this workflow produces>
tools: [Read, Write, Edit, Bash, Grep, Glob]
model: opus
modes: [generate]
rubric_path: evals/<workflow-name>.md
---

## Role

<What this agent produces, for whom, and what "done" means. One paragraph.>

## Memory to load

Load, via `python -m interfaces.retrieval`:

- `voice.md` — how this client sounds
- `business.md` — what they do and what they sell
- `icp.md` — who is reading
- `<rubric_path>` — the criteria this work is judged against

## Rubric

`memory/clients/<client>/<rubric_path>`

Invariant criteria can never be regenerated away or tuned away. A criterion's
invariance derives from the section it sits in, never from a field.

## Loop

Invoke the `gen-eval-loop` skill. Do not restate or re-derive the loop here —
it lives in one place so every workflow runs the same one.

## Escalation

Escalate rather than ship when: any required input is missing; the spine fails;
or the iteration cap is reached. Name the specific criterion and what was tried.
```

Create `.claude/agents/webcopy.md`:

```markdown
---
name: webcopy
description: Generates and revises web page copy for a client, judged against their web-copy rubric.
tools: [Read, Write, Edit, Bash, Grep, Glob]
model: opus
modes: [generate, revise]
rubric_path: evals/webcopy.md
---

## Role

Produce web page copy for one client that reads as though they wrote it, makes
only claims grounded in research or client intelligence, and passes their
web-copy rubric. "Done" means every invariant criterion passes and the operator
has copy in front of them — or a named sticking point explaining why they do not.

## Memory to load

Load, via `python -m interfaces.retrieval`:

- `voice.md` — how this client sounds
- `business.md` — what they do and what they sell
- `icp.md` — who is reading
- `evals/webcopy.md` — the criteria this work is judged against

In revise mode, also load the performance artifact named by the command and the
most recent `shipped.md` for the page.

## Rubric

`memory/clients/<client>/evals/webcopy.md`

Invariant criteria can never be regenerated away or tuned away. A criterion's
invariance derives from the section it sits in, never from a field.

## Loop

Invoke the `gen-eval-loop` skill. Do not restate or re-derive the loop here —
it lives in one place so every workflow runs the same one.

## Escalation

Escalate rather than ship when: any of voice, intelligence, research or rubric
is missing; `tools/eval.py` exits non-zero; or the iteration cap is reached.
Name the specific criterion and what was tried across iterations.
```

Create `interfaces/delegation.py`:

```python
"""Coordinator seam.

Not a router -- the coordinator is the main Claude session plus a routing doc.
This is the enumeration a router would consume, and it earns its place today by
validating agent files against the template before a run discovers the problem.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import yaml

REQUIRED_FRONTMATTER = ("name", "description", "tools", "model")
REQUIRED_SECTIONS = ("Role", "Memory to load", "Rubric", "Loop", "Escalation")

DEFAULT_AGENTS_DIR = Path(__file__).resolve().parent.parent / ".claude" / "agents"

_FRONTMATTER_RE = re.compile(r"\A---\s*$(?P<body>.*?)^---\s*$", re.MULTILINE | re.DOTALL)


class DelegationError(Exception):
    """An agent file does not honour the convention. Never silently accepted."""


@dataclass(frozen=True)
class WorkflowSpec:
    name: str
    description: str
    agent_file: str
    rubric_path: str
    modes: list[str]
    tools: list[str]


def parse_agent(path: Path) -> WorkflowSpec:
    path = Path(path)
    if not path.is_file():
        raise DelegationError(f"agent file not found: {path}")
    text = path.read_text()

    match = _FRONTMATTER_RE.search(text)
    if match is None:
        raise DelegationError(f"{path}: missing YAML frontmatter")
    try:
        front = yaml.safe_load(match.group("body")) or {}
    except yaml.YAMLError as exc:
        raise DelegationError(f"{path}: malformed frontmatter YAML: {exc}") from exc

    missing = [f for f in REQUIRED_FRONTMATTER if not front.get(f)]
    if missing:
        raise DelegationError(
            f"{path}: frontmatter missing required fields: {', '.join(missing)}"
        )
    if not isinstance(front["tools"], list):
        raise DelegationError(f"{path}: 'tools' must be a YAML list")

    body = text[match.end():]
    absent = [s for s in REQUIRED_SECTIONS if f"## {s}" not in body]
    if absent:
        raise DelegationError(
            f"{path}: missing required sections: {', '.join(absent)}"
        )

    return WorkflowSpec(
        name=front["name"],
        description=front["description"],
        agent_file=str(path),
        rubric_path=front.get("rubric_path", f"evals/{front['name']}.md"),
        modes=list(front.get("modes") or ["generate"]),
        tools=list(front["tools"]),
    )


def load_workflows(agents_dir: Path = DEFAULT_AGENTS_DIR) -> list[WorkflowSpec]:
    directory = Path(agents_dir)
    if not directory.is_dir():
        return []
    return [
        parse_agent(p)
        for p in sorted(directory.glob("*.md"))
        if not p.name.startswith("_")
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Enumerate and validate workflows.")
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--agents-dir", type=Path, default=DEFAULT_AGENTS_DIR)
    args = parser.parse_args(argv)

    try:
        specs = load_workflows(args.agents_dir)
    except DelegationError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(json.dumps([asdict(s) for s in specs], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_delegation.py -v`
Expected: 20 passed

- [ ] **Step 5: Commit**

```bash
git add interfaces/delegation.py .claude/agents tests/test_delegation.py
git commit -m "feat: agent-file convention and delegation seam with validation"
```

---

## Task 11: The skills — research-first, voice-match, gen-eval-loop

**Files:**
- Create: `.claude/skills/research-first/SKILL.md`
- Create: `.claude/skills/voice-match/SKILL.md`
- Create: `.claude/skills/gen-eval-loop/SKILL.md`
- Test: `tests/test_skills.py`

**Interfaces:**
- Consumes: `interfaces.delegation.REQUIRED_SECTIONS` (pattern only), the CLI signatures from Tasks 2, 4, 6
- Produces: the three skills, invoked by name from agent files and commands

These are prompt artifacts, so the tests assert structural properties — that the loop's hard edges are stated, and that the CLI invocations the skills tell Claude to run actually match the tools built in earlier tasks. That is a real class of drift and it is cheap to catch.

- [ ] **Step 1: Write the failing test**

Create `tests/test_skills.py`:

```python
import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS = REPO_ROOT / ".claude" / "skills"
SKILL_NAMES = ("research-first", "voice-match", "gen-eval-loop")


@pytest.mark.parametrize("name", SKILL_NAMES)
def test_skill_exists_with_frontmatter(name):
    path = SKILLS / name / "SKILL.md"
    assert path.is_file(), path
    match = re.search(r"\A---\s*$(.*?)^---\s*$", path.read_text(), re.MULTILINE | re.DOTALL)
    assert match is not None, f"{name} has no frontmatter"
    front = yaml.safe_load(match.group(1))
    assert front["name"] == name
    assert front["description"].strip()


@pytest.fixture
def loop_text() -> str:
    return (SKILLS / "gen-eval-loop" / "SKILL.md").read_text()


def test_loop_states_the_default_cap(loop_text):
    assert "3" in loop_text
    assert "cap" in loop_text.lower()


def test_loop_states_that_an_invariant_failure_never_ships(loop_text):
    lowered = loop_text.lower()
    assert "never ship" in lowered or "never ships" in lowered
    assert "invariant" in lowered


def test_loop_requires_a_trace_on_every_outcome(loop_text):
    assert "tools/trace.py" in loop_text
    assert "escalat" in loop_text.lower()


def test_loop_forbids_eyeballing_deterministic_criteria_on_spine_failure(loop_text):
    assert "exit code 2" in loop_text or "exits 2" in loop_text
    assert "stop" in loop_text.lower()


def test_loop_invokes_the_research_first_gate(loop_text):
    assert "research-first" in loop_text


def test_loop_cites_the_real_eval_cli_signature(loop_text):
    """Skills drift from tools. Assert the invocation still matches Task 4."""
    assert "tools/eval.py" in loop_text
    for flag in ("--client", "--workflow", "--copy"):
        assert flag in loop_text, flag


def test_research_first_names_all_four_required_inputs():
    text = (SKILLS / "research-first" / "SKILL.md").read_text().lower()
    for required in ("voice", "business", "icp", "rubric", "research"):
        assert required in text, required


def test_research_first_forbids_inventing_missing_inputs():
    text = (SKILLS / "research-first" / "SKILL.md").read_text().lower()
    assert "escalate" in text
    assert "never invent" in text or "do not invent" in text


def test_research_first_cites_the_real_retrieval_cli():
    text = (SKILLS / "research-first" / "SKILL.md").read_text()
    assert "python -m interfaces.retrieval" in text
    assert "--client" in text


def test_voice_match_requires_observable_markers_not_adjectives():
    text = (SKILLS / "voice-match" / "SKILL.md").read_text().lower()
    assert "adjective" in text
    assert "marker" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_skills.py -v`
Expected: FAIL — `AssertionError` on the missing `SKILL.md` files

- [ ] **Step 3: Write minimal implementation**

Create `.claude/skills/research-first/SKILL.md`:

```markdown
---
name: research-first
description: Use before generating any content - verifies voice, client intelligence, research and rubric are all present, and escalates rather than inventing what is missing.
---

# Research-First Gate

No content is generated without all four inputs. This runs before the first
token, not as a check afterward.

## The four inputs

| Input | Where | Why it is required |
|---|---|---|
| Voice profile | `voice.md` | Copy that does not sound like the client fails an invariant criterion |
| Client intelligence | `business.md`, `icp.md` | Claims about what they sell and who buys must be grounded |
| Research | The brief, plus anything the operator supplied for this page | Every factual claim traces here or to intelligence |
| Rubric | `evals/<workflow>.md` | Without it there is nothing to evaluate against |

## How to check

```bash
python -m interfaces.retrieval --client <client> --query "<term>" --scope voice
python -m interfaces.retrieval --client <client> --query "<term>" --scope business
python -m interfaces.retrieval --client <client> --query "<term>" --scope icp
python -m interfaces.retrieval --client <client> --query "<term>" --scope evals
```

Retrieval returns `[]` for anything absent and never raises. Absence is not an
error to retrieval — it is a decision for this gate to make, and here it is fatal.

## When something is missing

Escalate to the operator, naming exactly which input is absent and what you
would need to proceed. **Never invent** a voice, a customer, a statistic, or a
criterion. Do not proceed on a partial profile and flag it afterward; the point
of a gate is that nothing passes it.

Research that is thin is not the same as research that is missing. Thin research
proceeds, and every claim it cannot support simply does not get made.
```

Create `.claude/skills/voice-match/SKILL.md`:

```markdown
---
name: voice-match
description: Use when extracting a voice profile from client samples or matching generated copy to one - captures observable markers rather than adjectives.
---

# Voice Matching

A voice profile is only useful if two different runs read it the same way.
Adjectives do not survive that test: "warm, professional, approachable"
describes almost any client and constrains almost nothing.

## Capture observable markers

| Marker | What to record | Example |
|---|---|---|
| Sentence length | Typical and maximum word counts | "Mostly 8-14 words. Rarely over 20." |
| Rhythm | How sentences vary | "Short declarative, then a longer one that explains." |
| Person and address | Who speaks, who is spoken to | "First person plural. Addresses the reader as 'you'." |
| Vocabulary used | Words the client actually reaches for | "job, crew, site, gear" |
| Vocabulary avoided | Words absent across every sample | "solutions, leverage, bespoke" |
| Constructions | Recurring shapes | "Opens on a concrete scene, not a claim." |
| Contractions | Present or absent | "Always contracts: we'll, don't, it's." |
| Punctuation | Habits worth copying | "Em dashes for asides. No exclamation marks." |

Each marker must be checkable against a sample. If you cannot point at a line
that shows it, it is not a marker — it is a guess.

## Extracting from samples (onboarding)

1. Read every sample the operator supplied.
2. Fill the marker table, quoting a line for each.
3. List phrases absent from all samples — these seed the rubric's banned list.
4. Measure section lengths — these seed the rubric's length bands.
5. Note anything you could not determine. An unknown is recorded as unknown,
   never filled with a plausible default.

## Matching during generation

Read the marker table and write against it directly. Then check the draft
marker by marker: does the sentence-length distribution match? Are any avoided
words present? Is the opening the shape this client uses?

"It feels right" is not a check. Name the marker.
```

Create `.claude/skills/gen-eval-loop/SKILL.md`:

```markdown
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
python tools/eval.py --client <client> --workflow <workflow> --copy <path-to-draft>
```

Exit 0 means the evaluation ran, whether or not the copy passed. **Exit code 2
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
python tools/trace.py write --client <client> --run-id <run-id> --payload -
```

The payload is the trace schema: `schema_version` `"1"`, the run identifiers,
one entry in `iterations` per iteration actually run (each with its criteria,
the deterministic output, alternatives considered, the decision and the reason),
`outcome`, `iteration_count`, and `escalation.sticking_point` when escalated.

An escalation names the criterion and what was tried across iterations. "Could
not get the voice right" is not a sticking point. "Campfire-voice failed three
times; every opening reads as a claim rather than a scene, and the samples give
no example of an opening for a services page" is.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_skills.py -v`
Expected: 13 passed

- [ ] **Step 5: Commit**

```bash
git add .claude/skills tests/test_skills.py
git commit -m "feat: research-first, voice-match and gen-eval-loop skills"
```

---

## Task 12: Commands and the routing doc

**Files:**
- Create: `.claude/commands/onboard.md`, `webcopy.md`, `revise.md`, `client.md`
- Create: `CLAUDE.md`
- Test: `tests/test_commands.py`

**Interfaces:**
- Consumes: all CLI signatures from Tasks 2, 4, 6, 8, 9; the skills from Task 11
- Produces: the four operator entry points and the coordinator routing doc

- [ ] **Step 1: Write the failing test**

Create `tests/test_commands.py`:

```python
import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
COMMANDS = REPO_ROOT / ".claude" / "commands"
COMMAND_NAMES = ("onboard", "webcopy", "revise", "client")


@pytest.mark.parametrize("name", COMMAND_NAMES)
def test_command_exists_with_a_description(name):
    path = COMMANDS / f"{name}.md"
    assert path.is_file(), path
    match = re.search(r"\A---\s*$(.*?)^---\s*$", path.read_text(), re.MULTILINE | re.DOTALL)
    assert match is not None, f"{name} has no frontmatter"
    assert yaml.safe_load(match.group(1))["description"].strip()


@pytest.fixture
def onboard() -> str:
    return (COMMANDS / "onboard.md").read_text()


def test_onboard_refuses_without_seed_material(onboard):
    lowered = onboard.lower()
    assert "seed material" in lowered
    assert "refuse" in lowered or "stop" in lowered
    assert "cannot bootstrap" in lowered or "never invent" in lowered


def test_onboard_writes_all_four_artifacts(onboard):
    for artifact in ("business.md", "icp.md", "voice.md", "evals/webcopy.md"):
        assert artifact in onboard, artifact


def test_onboard_seeds_both_rubric_sections(onboard):
    assert "## Invariant" in onboard
    assert "## Tunable" in onboard


def test_onboard_uses_the_voice_match_skill(onboard):
    assert "voice-match" in onboard


@pytest.fixture
def revise() -> str:
    return (COMMANDS / "revise.md").read_text()


def test_revise_reads_shipped_copy_and_escalates_without_it(revise):
    assert "shipped.md" in revise
    assert "escalate" in revise.lower()


def test_revise_documents_the_funnel_mapping(revise):
    for stage in ("top", "mid", "bottom"):
        assert stage in revise.lower()
    assert "message-match" in revise.lower()


def test_revise_surfaces_the_sample_warning(revise):
    assert "sample_warning" in revise
    assert "provisional" in revise.lower()


def test_revise_cites_both_ingestors(revise):
    assert "tools/ingest_gsc.py" in revise
    assert "tools/ingest_ga4.py" in revise


def test_revise_routes_screenshots_through_the_same_ingestor(revise):
    assert "--source screenshot" in revise


def test_revise_runs_edits_through_the_same_loop(revise):
    assert "gen-eval-loop" in revise


def test_revise_links_each_edit_to_its_signal(revise):
    assert "signal_links" in revise


@pytest.fixture
def webcopy() -> str:
    return (COMMANDS / "webcopy.md").read_text()


def test_webcopy_delegates_to_the_agent_and_persists_the_decision(webcopy):
    assert "webcopy" in webcopy
    assert "tools/approve.py" in webcopy
    for decision in ("approve", "edit", "reject"):
        assert decision in webcopy


def test_client_command_switches_context():
    text = (COMMANDS / "client.md").read_text()
    assert "voice.md" in text and "business.md" in text and "icp.md" in text


def test_routing_doc_names_the_workflows_and_invariants():
    text = (REPO_ROOT / "CLAUDE.md").read_text()
    assert "webcopy" in text
    assert "invariant" in text.lower()
    assert "/onboard" in text and "/revise" in text and "/client" in text


def test_routing_doc_states_the_delegation_boundary():
    text = (REPO_ROOT / "CLAUDE.md").read_text().lower()
    assert "delegat" in text
    assert "propose" in text  # propose, don't apply
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_commands.py -v`
Expected: FAIL — `AssertionError` on the missing command files

- [ ] **Step 3: Write minimal implementation**

Create `.claude/commands/onboard.md`:

```markdown
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
python -m interfaces.retrieval --client $1 --query "" --scope voice
python tools/eval.py --client $1 --workflow webcopy --copy <one-of-the-samples>
```

The samples should mostly pass their own rubric. If a sample fails an invariant
criterion, the rubric is wrong — fix it with the operator before finishing.
```

Create `.claude/commands/webcopy.md`:

```markdown
---
description: Generate web page copy for a client and take an approve / edit / reject decision.
argument-hint: <client-name> <page-brief>
---

# Web copy for $1

Delegate to the `webcopy` agent in generate mode. Pass it the client, the brief,
and a page slug for the run id.

The agent runs the `gen-eval-loop` skill and returns either copy that passed
every criterion, or an escalation naming a specific sticking point.

## Present the result

**On a pass:** show the copy in full. Then show what the loop did — how many
iterations, which criteria failed on the way, what changed. The operator is
judging the copy, but the trace is how they learn whether to trust the loop.

**On an escalation:** show the sticking point, the drafts, and what was tried.
Do not present an escalated draft as though it passed.

## Take the decision

Ask for one of: **approve**, **edit**, or **reject**.

- **approve** — the copy ships as written
- **edit** — the operator supplies a changed version; that version ships
- **reject** — nothing ships; capture why

Then persist it:

```bash
python tools/approve.py --client $1 --run-id <run-id> \
    --decision approve --copy <path-to-final>

python tools/approve.py --client $1 --run-id <run-id> \
    --decision edit --copy <path-to-operator-version> --note "<what changed and why>"

python tools/approve.py --client $1 --run-id <run-id> \
    --decision reject --note "<why>"
```

On `edit`, the tool measures the change against `draft.md` in the run
directory. That number is the compounding signal — the acceptance gate reads
it — so record the operator's actual version, not a summary of their notes.
```

Create `.claude/commands/revise.md`:

```markdown
---
description: Diagnose a live page against GSC or GA4 data and revise it by funnel stage.
argument-hint: <client-name> <page-slug>
---

# Revise $2 for $1

## 1. Ingest the performance data

CSV is the source of truth:

```bash
python tools/ingest_gsc.py --client $1 --csv <path> --period 2026-08-01:2026-08-31
python tools/ingest_ga4.py --client $1 --csv <path> --period 2026-08-01:2026-08-31
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
```

Create `.claude/commands/client.md`:

```markdown
---
description: Switch the active client and load their full profile.
argument-hint: <client-name>
---

# Switch to $1

Load and summarise the client's profile so the rest of the session has it:

```bash
python -m interfaces.retrieval --client $1 --query "" --scope voice
python -m interfaces.retrieval --client $1 --query "" --scope business
python -m interfaces.retrieval --client $1 --query "" --scope icp
```

Read `memory/clients/$1/voice.md`, `business.md`, `icp.md`, and
`evals/webcopy.md` directly — retrieval is for searching, not for loading a
whole profile.

Report:

- What this client does, and who they sell to
- The voice in three or four markers, not adjectives
- What the rubric holds invariant
- The last few runs in `episodic/`, and how they were decided

**If the client directory does not exist, say so and offer `/onboard $1`.**
Do not infer a profile from the client's name.
```

Create `CLAUDE.md`:

```markdown
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

`python -m interfaces.delegation --validate` lists them and checks each agent
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
python -m interfaces.retrieval --client C --query Q [--scope S]
python -m interfaces.delegation --validate
python tools/eval.py     --client C --workflow W --copy PATH
python tools/trace.py    write --client C --run-id ID --payload PATH|-
python tools/ingest_gsc.py --client C --csv PATH [--period S:E] [--source screenshot]
python tools/ingest_ga4.py --client C --csv PATH [--period S:E] [--source screenshot]
python tools/approve.py  --client C --run-id ID --decision approve|edit|reject
```

## Memory

`memory/clients/<client>/` — `business.md`, `icp.md`, `voice.md`,
`evals/webcopy.md`, `episodic/`, `performance/`. Git-tracked, ext4, local only.
Client data does not leave this machine.

## Tests

`python -m pytest` from the repo root. The spine is tested; the loop is
validated by `docs/acceptance.md`.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_commands.py -v`
Expected: 18 passed

- [ ] **Step 5: Commit**

```bash
git add .claude/commands CLAUDE.md tests/test_commands.py
git commit -m "feat: operator commands and coordinator routing doc"
```

---

## Task 13: End-to-end wiring check and acceptance log

**Files:**
- Create: `tests/test_end_to_end.py`
- Create: `docs/acceptance.md`
- Create: `memory/.gitkeep`

**Interfaces:**
- Consumes: every module built above
- Produces: a test proving the tools compose into one run, and the log the §9 gate is recorded in

This is the task that catches integration drift the unit tests cannot: that a rubric written by onboarding is readable by `eval.py`, that a run directory made by `trace.py` is found by `approve.py`, and that an ingested artifact diagnoses to the stage the funnel table promises.

- [ ] **Step 1: Write the failing test**

Create `tests/test_end_to_end.py`:

```python
"""The spine composes into one run.

Unit tests prove each tool; this proves they agree about paths, ids and shapes.
The prompt-driven loop is deliberately absent -- it is validated by
docs/acceptance.md, not by pytest.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from interfaces.performance import weak_stage
from tools.episodic import find_latest_shipped, new_run_id

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).parent / "fixtures"
CLIENT = "orban-forest"


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """A memory root with a real rubric, as onboarding would leave it."""
    evals = tmp_path / "clients" / CLIENT / "evals"
    evals.mkdir(parents=True)
    (evals / "webcopy.md").write_text((FIXTURES / "rubric_valid.md").read_text())
    return tmp_path


def run(script: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / "tools" / script), *args],
        capture_output=True, text=True,
    )


def trace_payload(run_id: str, deterministic: dict) -> dict:
    return {
        "schema_version": "1", "run_id": run_id, "client": CLIENT,
        "workflow": "webcopy", "mode": "generate",
        "started_at": "2026-09-04T13:05:00Z",
        "iterations": [{
            "n": 1,
            "criteria": [{"id": "campfire-voice", "verdict": "pass",
                          "confidence": 0.8, "rationale": "Opens on a scene."}],
            "deterministic": deterministic,
            "alternatives_considered": [],
            "decision": "pass", "reason": "All criteria passed.",
        }],
        "outcome": "passed", "iteration_count": 1,
        "escalation": None, "signal_links": [],
    }


def test_generate_run_composes_end_to_end(workspace, tmp_path):
    run_id = new_run_id("webcopy", "home")
    draft = tmp_path / "draft.md"
    draft.write_text("We climb trees in Kent. We clear the site before we leave.\n")

    # 1. The rubric onboarding wrote is readable by eval.py.
    evaluated = run("eval.py", "--client", CLIENT, "--workflow", "webcopy",
                    "--copy", str(draft), "--memory-root", str(workspace))
    assert evaluated.returncode == 0, evaluated.stderr
    deterministic = json.loads(evaluated.stdout)
    assert deterministic["invariant_failed"] is False

    # 2. The trace lands in the run directory named by that run id.
    traced = subprocess.run(
        [sys.executable, str(REPO_ROOT / "tools" / "trace.py"), "write",
         "--client", CLIENT, "--run-id", run_id, "--payload", "-",
         "--memory-root", str(workspace)],
        input=json.dumps(trace_payload(run_id, deterministic)),
        capture_output=True, text=True,
    )
    assert traced.returncode == 0, traced.stderr
    run_directory = Path(json.loads(traced.stdout)["written"]).parent

    # 3. approve.py finds that same directory and ships the copy.
    (run_directory / "draft.md").write_text(draft.read_text())
    approved = run("approve.py", "--client", CLIENT, "--run-id", run_id,
                   "--decision", "approve", "--copy", str(draft),
                   "--memory-root", str(workspace))
    assert approved.returncode == 0, approved.stderr

    # 4. Episodic lookup finds the shipped copy a revision would start from.
    shipped = find_latest_shipped(workspace, CLIENT, "home")
    assert shipped is not None
    assert shipped.read_text() == draft.read_text()
    assert (run_directory / "trace.json").is_file()


def test_an_invariant_failure_is_visible_to_the_loop(workspace, tmp_path):
    """The teeth: uncited statistics fail an invariant criterion, not a tunable one."""
    draft = tmp_path / "draft.md"
    draft.write_text("Storm damage rose 40% across Kent last year.\n")
    evaluated = run("eval.py", "--client", CLIENT, "--workflow", "webcopy",
                    "--copy", str(draft), "--memory-root", str(workspace))
    assert evaluated.returncode == 0, evaluated.stderr
    result = json.loads(evaluated.stdout)
    assert result["invariant_failed"] is True
    failed = [c for c in result["criteria"] if c["status"] == "fail"]
    assert [c["id"] for c in failed] == ["no-fabricated-stats"]


def test_ingested_data_diagnoses_to_the_expected_stage(workspace):
    """A real-shaped GSC export maps to the funnel stage the table promises."""
    ingested = run("ingest_gsc.py", "--client", CLIENT,
                   "--csv", str(FIXTURES / "gsc_export.csv"),
                   "--period", "2026-08-01:2026-08-31",
                   "--memory-root", str(workspace))
    assert ingested.returncode == 0, ingested.stderr
    artifact = json.loads(Path(json.loads(ingested.stdout)["written"]).read_text())
    by_url = {p["url"]: p for p in artifact["pages"]}

    # 4200 impressions at 0.36% CTR: plenty of demand, nobody clicking.
    assert weak_stage(by_url["/services/tree-surgery"]) == "top"
    # 5000 impressions at 2.4%: healthy, and GSC cannot see further down.
    assert weak_stage(by_url["/"]) is None
    # No data at all is never a diagnosis.
    assert weak_stage(by_url["/contact"]) is None


def test_spine_failure_is_distinguishable_from_a_failing_evaluation(tmp_path):
    """Exit 2 means stop; exit 0 with failures means regenerate. Never confused."""
    draft = tmp_path / "draft.md"
    draft.write_text("anything\n")
    missing_rubric = run("eval.py", "--client", CLIENT, "--workflow", "webcopy",
                         "--copy", str(draft), "--memory-root", str(tmp_path))
    assert missing_rubric.returncode == 2
    assert missing_rubric.stdout == ""
    assert "rubric not found" in missing_rubric.stderr
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_end_to_end.py -v`
Expected: FAIL — the fixtures compose but `docs/acceptance.md` and `memory/` do not exist yet; if the tests pass at this point, they are still the deliverable, so proceed to step 3.

- [ ] **Step 3: Write the acceptance log and memory root**

Create `memory/.gitkeep` (empty file) so the tracked memory root exists.

Create `docs/acceptance.md`:

```markdown
# Acceptance Log

The §9 validation gate from `prd.md`. The spine is covered by `python -m pytest`;
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
  | sort | xargs -I{} sh -c 'python -c "
import json,sys; d=json.load(open(sys.argv[1]));
print(d[\"run_id\"], d[\"decision\"], d[\"edit_magnitude\"])" {}'
```

| Page # | Run | Decision | Edit magnitude |
|---|---|---|---|
| | | | |

**Gate:** if 9.1 through 9.5 hold, the reasoning design is validated and
workflow #2 can build on it. Until then, no workflow #2.
```

- [ ] **Step 4: Run the whole suite**

Run: `python -m pytest -v`
Expected: all tests pass across every test file. Also confirm the seam validator runs clean:

```bash
python -m interfaces.delegation --validate
```
Expected: JSON listing the `webcopy` workflow, exit 0.

- [ ] **Step 5: Commit**

```bash
git add tests/test_end_to_end.py docs/acceptance.md memory/.gitkeep
git commit -m "test: end-to-end spine composition and acceptance log"
```

---

## Task 14: Onboard Orban Forest

**Files:**
- Create: `memory/clients/orban-forest/business.md`, `icp.md`, `voice.md`, `evals/webcopy.md`

This task is **operator-driven and cannot be completed by an agent working alone.** It runs `/onboard orban-forest` as a conversation with Tayo, who supplies the seed material. An agent executing this plan should stop here and hand back.

- [ ] **Step 1: Confirm the system is ready**

```bash
python -m pytest
python -m interfaces.delegation --validate
```
Both must be clean before onboarding a real client.

- [ ] **Step 2: Hand back to the operator**

Report that the build is complete and tested, and that `/onboard orban-forest`
needs their seed material — existing Orban Forest copy, past pages, or samples
they wrote or approved. The command refuses to proceed without it by design.

- [ ] **Step 3: Run `/onboard orban-forest`** (operator session)

- [ ] **Step 4: Verify the seeded rubric accepts the client's own copy**

```bash
python tools/eval.py --client orban-forest --workflow webcopy --copy <a-sample>
```
A sample that fails an invariant criterion means the rubric is wrong, not the
sample. Fix it with the operator.

- [ ] **Step 5: Commit**

```bash
git add memory/clients/orban-forest
git commit -m "feat: onboard orban-forest with operator-supplied seed material"
```

---

## Self-Review

**Spec coverage:**

| Spec section | Task |
|---|---|
| §2 Repository layout | 1, 12, 13 |
| §3.1 Retrieval seam (H-FR6) | 2 |
| §3.2 Performance artifact | 7 |
| §3.3 Agent-file convention | 10 |
| §3.4 Coordinator contract | 10 |
| §4.1–4.2 Memory | 5, 13, 14 |
| §4.3 Rubric (H-FR4 config) | 3, 12 |
| §5 The loop (H-FR2, H-FR3) | 11 |
| §6 Spine (H-FR4, H-FR5, H-FR8) | 4, 6, 8 |
| §6 Edit magnitude (§9.1) | 9 |
| §7 Commands (H-FR1, H-FR10, H-FR11) | 12 |
| §8 Revise mode (H-FR7) | 7 (mapping), 12 (command) |
| §9 Error handling | 4, 6, 8, 9 (exit 2); 11, 12 (loop behavior) |
| §10 Testing | every task; 13 for integration |
| §11 Build order | task order |
| §12 Open item | 13 (`docs/acceptance.md`), 14 |

H-FR9 (shipped copy persisted) is Task 9. H-NFR3 (ext4) is a global constraint. H-NFR4 (`memory/` tracked) is Task 13's `.gitkeep`. H-NFR6 (`.env` convention) is Task 1. H-NFR5 (cap as budget guard) is stated in Task 11's skill.

**Placeholder scan:** no TBDs. `<client>`, `$1`, `<run-id>` in command and skill files are argument placeholders in prompt text, which is what those files are for — not deferred work.

**Type consistency:** `run_dir`/`new_run_id`/`find_latest_shipped` (Task 5) are used with matching signatures in Tasks 6, 9, 13. `empty_stage_signals` and `build_artifact` (Task 7) match their use in Task 8. `load_rubric`/`Rubric.deterministic()` (Task 3) match Task 4. `weak_stage` (Task 7) is used in Task 13. Every `tools/*.py` executed as a script carries the three `sys.path` lines noted in Task 4.

**One known gap:** Task 4's `fabricated_stat_scan` is deliberately narrow — percentages and four-plus-digit numbers minus years. It will miss "most homeowners" and flag an uncited price of £1,200. The rubric's judgment criterion `client-brief-adherence` is what catches the rest; the deterministic check is a floor, not a ceiling. Widening it is a rubric-tuning exercise once real copy exists, not a build task.

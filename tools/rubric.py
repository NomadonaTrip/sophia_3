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

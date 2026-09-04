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
    """Extract YAML entries from a section, bounded by section headings.

    The section body extends from the section heading to the next ## heading (or EOF).
    This prevents regex from crossing section boundaries and leaking criteria.
    """
    # Find the section heading
    section_pattern = r"^##\s+" + re.escape(section) + r"\s*$"
    section_match = re.search(section_pattern, text, re.MULTILINE)
    if section_match is None:
        raise RubricError(
            f"{path}: missing '## {section}' section with a fenced yaml block"
        )

    # Section body: from end of heading to the next ## heading (or EOF)
    body_start = section_match.end()
    next_section_match = re.search(r"^##\s+", text[body_start:], re.MULTILINE)
    if next_section_match:
        body_end = body_start + next_section_match.start()
    else:
        body_end = len(text)

    section_body = text[body_start:body_end]

    # Look for all YAML fences within this section body
    yaml_matches = list(re.finditer(r"```yaml\s*$(?P<body>.*?)^```\s*$", section_body, re.MULTILINE | re.DOTALL))
    if len(yaml_matches) == 0:
        raise RubricError(
            f"{path}: missing '## {section}' section with a fenced yaml block"
        )
    if len(yaml_matches) > 1:
        raise RubricError(
            f"{path}: '## {section}' contains multiple fenced yaml blocks; expected exactly one"
        )

    yaml_match = yaml_matches[0]
    try:
        parsed = yaml.safe_load(yaml_match.group("body"))
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

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


def _get_fence_length(line: str) -> int | None:
    """Get the backtick fence length for a line, or None if not a fence line.

    A fence line is one whose first non-whitespace run is 3+ backticks.
    Returns the length of the backtick run, or None if not a fence.
    """
    stripped = line.lstrip()
    if not stripped.startswith('`'):
        return None

    # Count consecutive backticks at the start
    count = 0
    for char in stripped:
        if char == '`':
            count += 1
        else:
            break

    return count if count >= 3 else None


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

    The section body extends from the section heading to the next ## heading (or EOF),
    but respects fence boundaries — a ## inside a code fence is not a section heading.
    This prevents regex from crossing section boundaries and leaking criteria.
    """
    # Find the section heading
    section_pattern = r"^##\s+" + re.escape(section) + r"\s*$"
    section_match = re.search(section_pattern, text, re.MULTILINE)
    if section_match is None:
        raise RubricError(
            f"{path}: missing '## {section}' section with a fenced yaml block"
        )

    # Section body: from end of heading to the next ## heading (or EOF), respecting fences
    body_start = section_match.end()
    remaining_text = text[body_start:]

    # Find next section heading while respecting fence boundaries
    lines = remaining_text.split('\n')
    in_fence = False
    fence_length = 0  # Track the opening fence's backtick count
    body_end = len(remaining_text)  # Default to end of text
    line_pos = 0

    for line in lines:
        line_fence_len = _get_fence_length(line)

        if line_fence_len is not None:
            if not in_fence:
                # Opening a fence
                in_fence = True
                fence_length = line_fence_len
            elif line_fence_len >= fence_length:
                # Closing a fence (only if backtick count >= opening)
                in_fence = False
                fence_length = 0
            # else: shorter fence inside an open fence is content, do nothing

        # Check for section heading only if not in a fence
        if not in_fence and re.match(r"^##\s+", line):
            body_end = line_pos
            break

        line_pos += len(line) + 1  # +1 for the newline character

    section_body = remaining_text[:body_end]

    # Extract YAML blocks from section body using line-by-line fence tracking
    body_lines = section_body.split('\n')
    in_fence = False
    fence_length = 0  # Track the opening fence's backtick count
    yaml_blocks = []
    yaml_start = -1

    for i, line in enumerate(body_lines):
        line_fence_len = _get_fence_length(line)

        if line_fence_len is not None and 'yaml' in line and not in_fence:
            in_fence = True
            fence_length = line_fence_len
            yaml_start = i + 1
            continue

        if line_fence_len is not None and in_fence and line_fence_len >= fence_length:
            yaml_blocks.append('\n'.join(body_lines[yaml_start:i]))
            in_fence = False
            fence_length = 0
            continue

    if len(yaml_blocks) == 0:
        raise RubricError(
            f"{path}: missing '## {section}' section with a fenced yaml block"
        )
    if len(yaml_blocks) > 1:
        raise RubricError(
            f"{path}: '## {section}' contains multiple fenced yaml blocks; expected exactly one"
        )

    yaml_content = yaml_blocks[0]
    try:
        parsed = yaml.safe_load(yaml_content)
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

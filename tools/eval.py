#!/usr/bin/env python3
"""Deterministic evaluation of copy against a client rubric (H-FR4).

Machine-checkable criteria only. Judgment criteria are scored by the subagent
against the rubric text and are deliberately absent from the output here.

Exit codes: 0 = the evaluation ran (pass or fail); 2 = the spine failed
(missing rubric, missing copy, unknown check). A spine failure must stop the
loop -- never fall back to judging deterministic criteria by eye.
"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))

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

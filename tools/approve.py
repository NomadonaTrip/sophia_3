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

DEFAULT_MEMORY_ROOT = Path(__file__).resolve().parent.parent / "memory"


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
        default=DEFAULT_MEMORY_ROOT,
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
    except Exception as exc:
        print(f"approve failed: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(record, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

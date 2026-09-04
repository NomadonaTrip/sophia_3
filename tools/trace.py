#!/usr/bin/env python3
"""Decision-trace persistence (H-FR5).

Every run emits a trace, pass or escalation, even though nothing consumes it
yet. Validation is strict on purpose: a trace that records the wrong thing is
worse than no trace, because it will be trusted later.

Exit codes: 0 = the trace was written; 2 = failure (malformed payload,
unwritable directory, or anything unexpected), with stdout empty and the
reason on stderr. Nothing should ever exit 1 with a traceback.
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
    except Exception as exc:
        print(f"trace failed: {exc}", file=sys.stderr)
        return 2

    print(json.dumps({"written": str(written)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

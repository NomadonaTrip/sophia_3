"""Episodic run directories.

One directory per run holds run.md, trace.json, shipped.md and decision.json.
Run ids sort lexicographically by time, which is what lets 'most recent shipped
copy for this page' be a sort rather than a scan of file mtimes.

Exit codes (CLI): 0 = a run id was produced; 2 = failure (e.g. a slug that
reduces to empty), with stdout empty and the reason on stderr.
"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

_TS_FORMAT = "%Y%m%dT%H%M%SZ"
_NON_SLUG = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    return _NON_SLUG.sub("-", text.strip().lower()).strip("-")


def new_run_id(workflow: str, slug: str, *, now: datetime | None = None) -> str:
    slugified = slugify(slug)
    if not slugified:
        raise ValueError(f"slug reduces to empty after slugification: {slug!r}")

    if now is None:
        tz_aware = datetime.now(timezone.utc)
    else:
        # Check if datetime is naive
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError(f"now must be timezone-aware, got naive datetime: {now!r}")
        # Convert to UTC if not already
        tz_aware = now.astimezone(timezone.utc)

    stamp = tz_aware.strftime(_TS_FORMAT)
    return f"{stamp}-{workflow}-{slugified}"


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
        if d.is_dir()
        and (d / "shipped.md").is_file()
        and _get_run_id_slug(d.name) == target
    ]
    return candidates[0] if candidates else None


def _get_run_id_slug(run_id: str) -> str:
    """Extract slug component from run_id (format: timestamp-workflow-slug)."""
    parts = run_id.split("-", 2)
    return parts[2] if len(parts) == 3 else ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Produce a correctly-formatted run id."
    )
    sub = parser.add_subparsers(dest="command", required=True)
    new_id = sub.add_parser(
        "new-run-id",
        help="Print a run id for the given workflow and slug.",
    )
    new_id.add_argument("--workflow", required=True)
    new_id.add_argument("--slug", required=True)
    args = parser.parse_args(argv)

    try:
        run_id = new_run_id(args.workflow, args.slug)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"episodic failed: {exc}", file=sys.stderr)
        return 2

    print(run_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

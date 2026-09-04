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

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
    except Exception as exc:
        print(f"ingest failed: {exc}", file=sys.stderr)
        return 2

    print(json.dumps({
        "written": str(written),
        "pages": len(pages),
        "sample_warning": artifact["sample_warning"],
    }, indent=2))
    return 0

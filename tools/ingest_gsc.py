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

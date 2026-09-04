#!/usr/bin/env python3
"""Google Analytics 4 CSV -> normalized performance artifact.

GA4 sees mid and bottom: sessions, bounce, engagement, conversions. Conversion
rate is derived, and stays null when sessions are unknown rather than dividing
by an assumed denominator.
"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))

from interfaces.performance import empty_stage_signals
from tools.ingest_common import parse_number, parse_percent, run_ingest

REQUIRED_COLUMNS = (
    "Page path", "Sessions", "Bounce rate", "Average engagement time", "Conversions",
)


def to_page(row: dict) -> dict:
    sessions = parse_number(row.get("Sessions"))
    conversions = parse_number(row.get("Conversions"))
    conversion_rate = (
        conversions / sessions
        if sessions not in (None, 0) and conversions is not None
        else None
    )
    signals = empty_stage_signals()
    signals["mid"] = {
        "sessions": sessions,
        "bounce_rate": parse_percent(row.get("Bounce rate")),
        "avg_engagement_s": parse_number(row.get("Average engagement time")),
    }
    signals["bottom"] = {
        "conversions": conversions,
        "conversion_rate": conversion_rate,
    }
    return {
        "url": row["Page path"].strip(),
        "row_confidence": "high",
        "stage_signals": signals,
    }


if __name__ == "__main__":
    raise SystemExit(
        run_ingest(
            None,
            source_default="ga4",
            required_columns=REQUIRED_COLUMNS,
            to_page=to_page,
        )
    )

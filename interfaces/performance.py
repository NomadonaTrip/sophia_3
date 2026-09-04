"""Performance-artifact seam.

Every ingestion path emits this one shape, keyed to funnel stage, so revise
mode's diagnosis is a lookup rather than a fresh judgment each time.

Absent metrics are None, never 0: a page with no conversion tracking must not
read as a page with zero conversions.

Exit codes (CLI): 0 = the artifact was read and diagnosed; 2 = the artifact
was malformed or unreadable, with stdout empty and the reason on stderr.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ARTIFACT_SCHEMA_VERSION = "1"

# Volume floors below which a read is statistically untrustworthy. Revise mode
# must surface the warning rather than suppress the diagnosis (PRD section 11).
MIN_IMPRESSIONS = 100
MIN_SESSIONS = 30

STAGES = ("top", "mid", "bottom")
TOP_KEYS = ("impressions", "ctr", "avg_position")
MID_KEYS = ("sessions", "bounce_rate", "avg_engagement_s")
BOTTOM_KEYS = ("conversions", "conversion_rate")
_STAGE_KEYS = {"top": TOP_KEYS, "mid": MID_KEYS, "bottom": BOTTOM_KEYS}

SOURCES = ("gsc", "ga4", "screenshot")
ROW_CONFIDENCE = ("high", "low")

# Funnel thresholds.
_CTR_FLOOR = 0.02
_BOUNCE_CEILING = 0.70
_ENGAGEMENT_FLOOR_S = 15
_CONVERSION_FLOOR = 0.01


class ArtifactError(Exception):
    """The performance artifact is malformed. Never written, never diagnosed."""


def empty_stage_signals() -> dict:
    return {stage: {key: None for key in keys} for stage, keys in _STAGE_KEYS.items()}


def build_artifact(
    client: str,
    source: str,
    period: dict,
    pages: list[dict],
    *,
    min_impressions: int = MIN_IMPRESSIONS,
    min_sessions: int = MIN_SESSIONS,
    now: datetime | None = None,
) -> dict:
    total_impressions = _sum_metric(pages, "top", "impressions")
    total_sessions = _sum_metric(pages, "mid", "sessions")
    sample_warning = (
        total_impressions < min_impressions and total_sessions < min_sessions
    )
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "client": client,
        "source": source,
        "ingested_at": stamp,
        "period": period,
        "sample_warning": sample_warning,
        "pages": pages,
    }


def _sum_metric(pages: list[dict], stage: str, key: str) -> float:
    total = 0.0
    for page in pages:
        value = page.get("stage_signals", {}).get(stage, {}).get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            total += value
    return total


def validate_artifact(payload: dict) -> None:
    if not isinstance(payload, dict):
        raise ArtifactError(f"artifact must be an object, got {type(payload).__name__}")
    for key in (
        "schema_version", "client", "source", "ingested_at",
        "period", "sample_warning", "pages",
    ):
        if key not in payload:
            raise ArtifactError(f"artifact missing required key: {key}")
    if payload["schema_version"] != ARTIFACT_SCHEMA_VERSION:
        raise ArtifactError(
            f"schema_version must be {ARTIFACT_SCHEMA_VERSION!r}, "
            f"got {payload['schema_version']!r}"
        )
    if payload["source"] not in SOURCES:
        raise ArtifactError(f"source must be one of {SOURCES}, got {payload['source']!r}")
    for key in ("start", "end"):
        if key not in payload["period"]:
            raise ArtifactError(f"period missing '{key}'")
    if not isinstance(payload["pages"], list):
        raise ArtifactError(
            f"pages must be a list, got {type(payload['pages']).__name__}"
        )
    for page in payload["pages"]:
        _validate_page(page)


def _validate_page(page: object) -> None:
    if not isinstance(page, dict):
        raise ArtifactError(f"page must be an object, got {page!r}")
    for key in ("url", "row_confidence", "stage_signals"):
        if key not in page:
            raise ArtifactError(f"page missing required key: {key}")
    if page["row_confidence"] not in ROW_CONFIDENCE:
        raise ArtifactError(
            f"row_confidence must be one of {ROW_CONFIDENCE}, "
            f"got {page['row_confidence']!r}"
        )
    signals = page["stage_signals"]
    if not isinstance(signals, dict):
        raise ArtifactError(
            f"page {page['url']!r} stage_signals must be an object, "
            f"got {type(signals).__name__}"
        )
    for stage, keys in _STAGE_KEYS.items():
        if stage not in signals:
            raise ArtifactError(f"page {page['url']!r} missing stage {stage!r}")
        stage_values = signals[stage]
        if not isinstance(stage_values, dict):
            raise ArtifactError(
                f"page {page['url']!r} stage {stage!r} must be an object, "
                f"got {type(stage_values).__name__}"
            )
        for key in keys:
            if key not in stage_values:
                raise ArtifactError(
                    f"page {page['url']!r} stage {stage!r} missing metric {key!r}"
                )


def weak_stage(page: dict) -> str | None:
    """The funnel stage to act on, or None if nothing is diagnosably weak.

    Evaluated top-down; the earliest weak stage wins, because a page nobody
    clicks cannot have a message-match problem worth diagnosing. Comparisons
    involving a None metric are skipped -- an unmeasured stage is never weak.
    """
    signals = page.get("stage_signals", {})
    top, mid, bottom = signals.get("top", {}), signals.get("mid", {}), signals.get("bottom", {})

    impressions, ctr = top.get("impressions"), top.get("ctr")
    bounce, engagement = mid.get("bounce_rate"), mid.get("avg_engagement_s")
    conversion_rate = bottom.get("conversion_rate")

    if impressions is not None and ctr is not None:
        if impressions >= MIN_IMPRESSIONS and ctr < _CTR_FLOOR:
            return "top"

    ctr_healthy = ctr is not None and ctr >= _CTR_FLOOR
    if ctr_healthy:
        if bounce is not None and bounce > _BOUNCE_CEILING:
            return "mid"
        if engagement is not None and engagement < _ENGAGEMENT_FLOOR_S:
            return "mid"

    mid_healthy = bounce is not None and bounce <= _BOUNCE_CEILING
    if mid_healthy and conversion_rate is not None:
        if conversion_rate < _CONVERSION_FLOOR:
            return "bottom"

    return None


def write_artifact(memory_root: Path, artifact: dict) -> Path:
    validate_artifact(artifact)
    directory = (
        Path(memory_root) / "clients" / artifact["client"] / "performance"
    )
    directory.mkdir(parents=True, exist_ok=True)
    stamp = artifact["ingested_at"].replace(":", "").replace("-", "")
    target = directory / f"{stamp}-{artifact['source']}.json"
    target.write_text(json.dumps(artifact, indent=2) + "\n")
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Diagnose a performance artifact by funnel stage."
    )
    sub = parser.add_subparsers(dest="command", required=True)
    weak = sub.add_parser(
        "weak-stage",
        help="Print each page's weakest funnel stage (or null), as JSON.",
    )
    weak.add_argument("--artifact", required=True, type=Path)
    args = parser.parse_args(argv)

    try:
        payload = json.loads(args.artifact.read_text())
        validate_artifact(payload)
        result = {page["url"]: weak_stage(page) for page in payload["pages"]}
        output = json.dumps(result, indent=2)
    except (ArtifactError, OSError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"performance failed: {exc}", file=sys.stderr)
        return 2

    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

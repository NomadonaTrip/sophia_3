import json
import subprocess
import sys
from pathlib import Path

import pytest

from tools.ingest_common import IngestError, parse_number, parse_percent, read_rows
from tools.ingest_ga4 import to_page as ga4_to_page
from tools.ingest_gsc import to_page as gsc_to_page

FIXTURES = Path(__file__).parent / "fixtures"
REPO_ROOT = Path(__file__).resolve().parent.parent


# --- parsing helpers ---

def test_parse_number_handles_thousands_separators():
    assert parse_number("5,000") == 5000.0


def test_parse_number_returns_none_for_blank():
    assert parse_number("") is None
    assert parse_number(None) is None


def test_parse_number_rejects_garbage():
    with pytest.raises(IngestError, match="number"):
        parse_number("about five")


def test_parse_percent_converts_percentage_sign():
    assert parse_percent("2.4%") == pytest.approx(0.024)


def test_parse_percent_passes_through_a_ratio():
    assert parse_percent("0.024") == pytest.approx(0.024)


def test_parse_percent_returns_none_for_blank():
    assert parse_percent("") is None


def test_read_rows_requires_declared_columns(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("Page,Clicks\n/,1\n")
    with pytest.raises(IngestError, match="Impressions"):
        read_rows(path, ("Page", "Clicks", "Impressions"))


def test_read_rows_reports_a_missing_file(tmp_path):
    with pytest.raises(IngestError, match="not found"):
        read_rows(tmp_path / "absent.csv", ("Page",))


def test_read_rows_rejects_an_empty_file(tmp_path):
    path = tmp_path / "empty.csv"
    path.write_text("")
    with pytest.raises(IngestError, match="empty"):
        read_rows(path, ("Page",))


# --- row mapping ---

def test_gsc_row_maps_to_top_stage_only():
    rows = read_rows(FIXTURES / "gsc_export.csv",
                     ("Page", "Clicks", "Impressions", "CTR", "Position"))
    page = gsc_to_page(rows[0])
    assert page["url"] == "/"
    assert page["stage_signals"]["top"] == {
        "impressions": 5000.0, "ctr": pytest.approx(0.024), "avg_position": 8.1
    }
    assert page["stage_signals"]["mid"]["sessions"] is None
    assert page["stage_signals"]["bottom"]["conversions"] is None


def test_gsc_blank_row_becomes_all_none_not_zero():
    rows = read_rows(FIXTURES / "gsc_export.csv",
                     ("Page", "Clicks", "Impressions", "CTR", "Position"))
    page = gsc_to_page(rows[2])
    assert page["url"] == "/contact"
    assert page["stage_signals"]["top"] == {
        "impressions": None, "ctr": None, "avg_position": None
    }


def test_ga4_row_maps_to_mid_and_bottom_stages():
    rows = read_rows(
        FIXTURES / "ga4_export.csv",
        ("Page path", "Sessions", "Bounce rate", "Average engagement time",
         "Conversions"),
    )
    page = ga4_to_page(rows[0])
    assert page["url"] == "/"
    assert page["stage_signals"]["mid"] == {
        "sessions": 900.0, "bounce_rate": pytest.approx(0.325),
        "avg_engagement_s": 95.0,
    }
    assert page["stage_signals"]["bottom"]["conversions"] == 36.0
    assert page["stage_signals"]["bottom"]["conversion_rate"] == pytest.approx(0.04)


def test_ga4_conversion_rate_is_none_without_sessions():
    page = ga4_to_page({
        "Page path": "/x", "Sessions": "", "Bounce rate": "",
        "Average engagement time": "", "Conversions": "3",
    })
    assert page["stage_signals"]["bottom"]["conversion_rate"] is None


def test_row_confidence_defaults_to_high():
    rows = read_rows(FIXTURES / "gsc_export.csv",
                     ("Page", "Clicks", "Impressions", "CTR", "Position"))
    assert gsc_to_page(rows[0])["row_confidence"] == "high"


# --- CLI ---

def _ingest(tool: str, csv_path: Path, memory_root: Path, *extra: str):
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / "tools" / tool),
         "--client", "orban-forest", "--csv", str(csv_path),
         "--period", "2026-08-01:2026-08-31",
         "--memory-root", str(memory_root), *extra],
        capture_output=True, text=True,
    )


def test_gsc_cli_writes_an_artifact(tmp_path):
    proc = _ingest("ingest_gsc.py", FIXTURES / "gsc_export.csv", tmp_path)
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["pages"] == 3
    artifact = json.loads(Path(result["written"]).read_text())
    assert artifact["source"] == "gsc"
    assert artifact["period"] == {"start": "2026-08-01", "end": "2026-08-31"}
    assert artifact["sample_warning"] is False


def test_ga4_cli_writes_an_artifact(tmp_path):
    proc = _ingest("ingest_ga4.py", FIXTURES / "ga4_export.csv", tmp_path)
    assert proc.returncode == 0, proc.stderr
    artifact = json.loads(Path(json.loads(proc.stdout)["written"]).read_text())
    assert artifact["source"] == "ga4"


def test_screenshot_source_marks_every_row_low_confidence(tmp_path):
    """Screenshots are a lossy fallback; the hierarchy lives in the data."""
    proc = _ingest(
        "ingest_gsc.py", FIXTURES / "gsc_export.csv", tmp_path,
        "--source", "screenshot",
    )
    assert proc.returncode == 0, proc.stderr
    artifact = json.loads(Path(json.loads(proc.stdout)["written"]).read_text())
    assert artifact["source"] == "screenshot"
    assert {p["row_confidence"] for p in artifact["pages"]} == {"low"}


def test_cli_exits_two_on_missing_columns(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("Page,Clicks\n/,1\n")
    proc = _ingest("ingest_gsc.py", bad, tmp_path)
    assert proc.returncode == 2
    assert "Impressions" in proc.stderr
    assert proc.stdout == ""


def test_cli_exits_two_on_malformed_period(tmp_path):
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "tools" / "ingest_gsc.py"),
         "--client", "orban-forest", "--csv", str(FIXTURES / "gsc_export.csv"),
         "--period", "August", "--memory-root", str(tmp_path)],
        capture_output=True, text=True,
    )
    assert proc.returncode == 2
    assert "period" in proc.stderr

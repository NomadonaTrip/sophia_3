import subprocess
import sys

import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path

from tools.episodic import find_latest_shipped, new_run_id, run_dir, slugify

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_slugify_lowercases_and_hyphenates():
    assert slugify("Services / Tree Surgery") == "services-tree-surgery"


def test_slugify_collapses_repeats_and_trims():
    assert slugify("  --Hello___World!!  ") == "hello-world"


def test_new_run_id_shape():
    now = datetime(2026, 9, 4, 13, 5, 0, tzinfo=timezone.utc)
    assert new_run_id("webcopy", "home", now=now) == "20260904T130500Z-webcopy-home"


def test_run_dir_does_not_create_by_default(tmp_path):
    path = run_dir(tmp_path, "orban-forest", "20260904T130500Z-webcopy-home")
    assert not path.exists()
    assert path == (
        tmp_path / "clients" / "orban-forest" / "episodic"
        / "20260904T130500Z-webcopy-home"
    )


def test_run_dir_creates_when_asked(tmp_path):
    path = run_dir(tmp_path, "orban-forest", "r1", create=True)
    assert path.is_dir()


def test_find_latest_shipped_returns_none_when_absent(tmp_path):
    assert find_latest_shipped(tmp_path, "orban-forest", "home") is None


def test_find_latest_shipped_ignores_runs_without_shipped_copy(tmp_path):
    d = run_dir(tmp_path, "orban-forest", "20260901T000000Z-webcopy-home", create=True)
    (d / "trace.json").write_text("{}")
    assert find_latest_shipped(tmp_path, "orban-forest", "home") is None


def test_find_latest_shipped_picks_most_recent_matching_slug(tmp_path):
    for run_id in (
        "20260901T000000Z-webcopy-home",
        "20260903T000000Z-webcopy-home",
        "20260904T000000Z-webcopy-services",
    ):
        d = run_dir(tmp_path, "orban-forest", run_id, create=True)
        (d / "shipped.md").write_text(run_id)
    found = find_latest_shipped(tmp_path, "orban-forest", "home")
    assert found is not None
    assert found.read_text() == "20260903T000000Z-webcopy-home"


def test_find_latest_shipped_distinguishes_suffix_collision(tmp_path):
    """Test that 'home' lookup doesn't match 'new-home' run."""
    for run_id in (
        "20260901T000000Z-webcopy-new-home",
        "20260902T000000Z-webcopy-home",
    ):
        d = run_dir(tmp_path, "orban-forest", run_id, create=True)
        (d / "shipped.md").write_text(f"CONTENT-{run_id}")
    found = find_latest_shipped(tmp_path, "orban-forest", "home")
    assert found is not None
    assert found.read_text() == "CONTENT-20260902T000000Z-webcopy-home"


def test_new_run_id_rejects_empty_slug():
    """Test that new_run_id raises ValueError for punctuation-only slug."""
    with pytest.raises(ValueError, match="slug reduces to empty"):
        new_run_id("webcopy", "///")


def test_new_run_id_rejects_naive_datetime():
    """Test that new_run_id raises ValueError for naive datetime."""
    naive = datetime(2026, 9, 4, 13, 5, 0)  # no tzinfo
    with pytest.raises(ValueError, match="must be timezone-aware"):
        new_run_id("webcopy", "home", now=naive)


def test_new_run_id_converts_non_utc_aware_datetime():
    """Test that new_run_id converts aware non-UTC datetime to UTC."""
    # Use +05:00 offset where the UTC date will differ from local date
    eastern = timezone(timedelta(hours=5))
    local_time = datetime(2026, 9, 4, 13, 5, 0, tzinfo=eastern)  # 2026-09-04 13:05 +05:00
    # In UTC this is 2026-09-04 08:05:00Z
    result = new_run_id("webcopy", "home", now=local_time)
    assert result == "20260904T080500Z-webcopy-home"


# --- CLI (C1: the prompt layer must obtain run ids through this, never invent one) ---

def _run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / "tools" / "episodic.py"), *args],
        capture_output=True, text=True,
    )


def test_cli_new_run_id_prints_a_run_id():
    proc = _run_cli("new-run-id", "--workflow", "webcopy", "--slug", "Tree Surgery")
    assert proc.returncode == 0, proc.stderr
    run_id = proc.stdout.strip()
    assert run_id.endswith("-webcopy-tree-surgery")


def test_cli_new_run_id_exits_two_on_unusable_slug():
    proc = _run_cli("new-run-id", "--workflow", "webcopy", "--slug", "///")
    assert proc.returncode == 2
    assert proc.stdout == ""
    assert "slug" in proc.stderr


def test_cli_run_id_round_trips_through_find_latest_shipped(tmp_path):
    """End-to-end: a run id minted by the CLI is later found by
    find_latest_shipped for the same slug -- the exact bridge C1 closes.
    """
    proc = _run_cli("new-run-id", "--workflow", "webcopy", "--slug", "Tree Surgery")
    assert proc.returncode == 0, proc.stderr
    run_id = proc.stdout.strip()

    d = run_dir(tmp_path, "orban-forest", run_id, create=True)
    (d / "shipped.md").write_text("Shipped copy.")

    found = find_latest_shipped(tmp_path, "orban-forest", "Tree Surgery")
    assert found is not None
    assert found == d / "shipped.md"

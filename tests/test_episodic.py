from datetime import datetime, timezone
from pathlib import Path

from tools.episodic import find_latest_shipped, new_run_id, run_dir, slugify


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

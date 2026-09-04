import json
from pathlib import Path

import pytest

from interfaces.performance import (
    ARTIFACT_SCHEMA_VERSION,
    MIN_IMPRESSIONS,
    MIN_SESSIONS,
    ArtifactError,
    build_artifact,
    empty_stage_signals,
    validate_artifact,
    weak_stage,
    write_artifact,
)

PERIOD = {"start": "2026-08-01", "end": "2026-08-31"}


def page(url="/home", *, top=None, mid=None, bottom=None, confidence="high") -> dict:
    signals = empty_stage_signals()
    signals["top"].update(top or {})
    signals["mid"].update(mid or {})
    signals["bottom"].update(bottom or {})
    return {"url": url, "row_confidence": confidence, "stage_signals": signals}


# --- shape ---

def test_empty_stage_signals_has_every_stage_with_null_metrics():
    signals = empty_stage_signals()
    assert set(signals) == {"top", "mid", "bottom"}
    assert signals["top"] == {"impressions": None, "ctr": None, "avg_position": None}
    assert signals["mid"] == {
        "sessions": None, "bounce_rate": None, "avg_engagement_s": None
    }
    assert signals["bottom"] == {"conversions": None, "conversion_rate": None}


def test_build_artifact_sets_schema_version_and_timestamp():
    artifact = build_artifact("orban-forest", "gsc", PERIOD, [page()])
    assert artifact["schema_version"] == ARTIFACT_SCHEMA_VERSION
    assert artifact["ingested_at"].endswith("Z")
    assert artifact["client"] == "orban-forest"
    assert artifact["source"] == "gsc"


# --- sample_warning ---

def test_sample_warning_true_below_impression_floor():
    artifact = build_artifact(
        "orban-forest", "gsc", PERIOD,
        [page(top={"impressions": MIN_IMPRESSIONS - 1})],
    )
    assert artifact["sample_warning"] is True


def test_sample_warning_false_above_impression_floor():
    artifact = build_artifact(
        "orban-forest", "gsc", PERIOD,
        [page(top={"impressions": MIN_IMPRESSIONS})],
    )
    assert artifact["sample_warning"] is False


def test_sample_warning_false_above_session_floor():
    artifact = build_artifact(
        "orban-forest", "ga4", PERIOD, [page(mid={"sessions": MIN_SESSIONS})]
    )
    assert artifact["sample_warning"] is False


def test_sample_warning_sums_across_pages():
    artifact = build_artifact(
        "orban-forest", "gsc", PERIOD,
        [page("/a", top={"impressions": 60}), page("/b", top={"impressions": 60})],
    )
    assert artifact["sample_warning"] is False


def test_sample_warning_true_when_all_volume_metrics_are_null():
    artifact = build_artifact("orban-forest", "screenshot", PERIOD, [page()])
    assert artifact["sample_warning"] is True


def test_floors_are_overridable():
    artifact = build_artifact(
        "orban-forest", "gsc", PERIOD, [page(top={"impressions": 5})],
        min_impressions=1,
    )
    assert artifact["sample_warning"] is False


def test_build_artifact_tolerates_non_numeric_metric():
    """A malformed ingest (e.g. impressions='lots') must not crash build_artifact."""
    artifact = build_artifact(
        "orban-forest", "gsc", PERIOD, [page(top={"impressions": "lots"})]
    )
    assert artifact["sample_warning"] is True


def test_build_artifact_excludes_boolean_metric_from_volume_sum():
    """bool is an int subclass in Python; a boolean metric must not count as 1."""
    artifact = build_artifact(
        "orban-forest", "gsc", PERIOD, [page(top={"impressions": True})]
    )
    assert artifact["sample_warning"] is True


# --- validation ---

def test_valid_artifact_passes():
    validate_artifact(build_artifact("orban-forest", "gsc", PERIOD, [page()]))


def test_unknown_source_is_rejected():
    artifact = build_artifact("orban-forest", "gsc", PERIOD, [page()])
    artifact["source"] = "guesswork"
    with pytest.raises(ArtifactError, match="source"):
        validate_artifact(artifact)


def test_missing_stage_is_rejected():
    artifact = build_artifact("orban-forest", "gsc", PERIOD, [page()])
    del artifact["pages"][0]["stage_signals"]["mid"]
    with pytest.raises(ArtifactError, match="mid"):
        validate_artifact(artifact)


def test_unknown_row_confidence_is_rejected():
    artifact = build_artifact(
        "orban-forest", "gsc", PERIOD, [page(confidence="probably")]
    )
    with pytest.raises(ArtifactError, match="row_confidence"):
        validate_artifact(artifact)


def test_pages_non_list_is_rejected_not_crashed():
    """A malformed 'pages' shape must raise ArtifactError, not TypeError."""
    artifact = build_artifact("orban-forest", "gsc", PERIOD, [page()])
    artifact["pages"] = 5
    with pytest.raises(ArtifactError, match="pages"):
        validate_artifact(artifact)


def test_stage_signals_non_dict_is_rejected_not_crashed():
    """A malformed 'stage_signals' shape must raise ArtifactError, not TypeError."""
    artifact = build_artifact("orban-forest", "gsc", PERIOD, [page()])
    artifact["pages"][0]["stage_signals"] = "nope"
    with pytest.raises(ArtifactError, match="stage_signals"):
        validate_artifact(artifact)


def test_stage_value_non_dict_is_rejected_not_crashed():
    """A malformed stage value (e.g. a list) must raise ArtifactError, not TypeError."""
    artifact = build_artifact("orban-forest", "gsc", PERIOD, [page()])
    artifact["pages"][0]["stage_signals"]["mid"] = ["not", "a", "dict"]
    with pytest.raises(ArtifactError, match="mid"):
        validate_artifact(artifact)


def test_zero_is_not_conflated_with_absent():
    """A page with tracked zero conversions differs from one with no tracking."""
    tracked = page(bottom={"conversions": 0, "conversion_rate": 0.0})
    untracked = page()
    assert tracked["stage_signals"]["bottom"]["conversions"] == 0
    assert untracked["stage_signals"]["bottom"]["conversions"] is None


# --- funnel mapping ---

def test_weak_stage_top_when_impressions_healthy_and_ctr_low():
    assert weak_stage(page(top={"impressions": 5000, "ctr": 0.008})) == "top"


def test_weak_stage_mid_when_ctr_healthy_and_bounce_high():
    assert (
        weak_stage(page(top={"impressions": 5000, "ctr": 0.05},
                        mid={"bounce_rate": 0.85, "avg_engagement_s": 40}))
        == "mid"
    )


def test_weak_stage_mid_when_engagement_low():
    assert (
        weak_stage(page(top={"impressions": 5000, "ctr": 0.05},
                        mid={"bounce_rate": 0.4, "avg_engagement_s": 6}))
        == "mid"
    )


def test_weak_stage_bottom_when_engagement_healthy_and_conversion_low():
    assert (
        weak_stage(page(top={"impressions": 5000, "ctr": 0.05},
                        mid={"bounce_rate": 0.3, "avg_engagement_s": 90},
                        bottom={"conversion_rate": 0.002}))
        == "bottom"
    )


def test_weak_stage_none_when_everything_is_healthy():
    assert (
        weak_stage(page(top={"impressions": 5000, "ctr": 0.05},
                        mid={"bounce_rate": 0.3, "avg_engagement_s": 90},
                        bottom={"conversion_rate": 0.04}))
        is None
    )


def test_weak_stage_ignores_stages_with_no_data():
    """An unmeasured stage is never diagnosed as weak."""
    assert weak_stage(page(top={"impressions": 5000, "ctr": 0.05})) is None


def test_weak_stage_none_when_impressions_below_floor():
    assert weak_stage(page(top={"impressions": 3, "ctr": 0.001})) is None


# --- writing ---

def test_write_artifact_persists_under_client_performance(tmp_path):
    artifact = build_artifact("orban-forest", "gsc", PERIOD, [page()])
    written = write_artifact(tmp_path, artifact)
    assert written.parent == tmp_path / "clients" / "orban-forest" / "performance"
    assert written.suffix == ".json"
    assert json.loads(written.read_text())["client"] == "orban-forest"


def test_write_artifact_rejects_invalid_without_writing(tmp_path):
    artifact = build_artifact("orban-forest", "gsc", PERIOD, [page()])
    artifact["source"] = "guesswork"
    with pytest.raises(ArtifactError):
        write_artifact(tmp_path, artifact)
    assert not (tmp_path / "clients").exists()

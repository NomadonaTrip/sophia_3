"""The spine composes into one run.

Unit tests prove each tool; this proves they agree about paths, ids and shapes.
The prompt-driven loop is deliberately absent -- it is validated by
docs/acceptance.md, not by pytest.
"""
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from interfaces.performance import weak_stage
from tools.episodic import find_latest_shipped, new_run_id

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).parent / "fixtures"
CLIENT = "orban-forest"


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """A memory root with a real rubric, as onboarding would leave it."""
    evals = tmp_path / "clients" / CLIENT / "evals"
    evals.mkdir(parents=True)
    (evals / "webcopy.md").write_text((FIXTURES / "rubric_valid.md").read_text())
    return tmp_path


def run(script: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / "tools" / script), *args],
        capture_output=True, text=True,
    )


def trace_payload(run_id: str, deterministic: dict) -> dict:
    return {
        "schema_version": "1", "run_id": run_id, "client": CLIENT,
        "workflow": "webcopy", "mode": "generate",
        "started_at": "2026-09-04T13:05:00Z",
        "iterations": [{
            "n": 1,
            "criteria": [{"id": "campfire-voice", "verdict": "pass",
                          "confidence": 0.8, "rationale": "Opens on a scene."}],
            "deterministic": deterministic,
            "alternatives_considered": [],
            "decision": "pass", "reason": "All criteria passed.",
        }],
        "outcome": "passed", "iteration_count": 1,
        "escalation": None, "signal_links": [],
    }


def test_generate_run_composes_end_to_end(workspace, tmp_path):
    home_time = datetime(2026, 9, 4, 13, 0, 0, tzinfo=timezone.utc)
    new_home_time = datetime(2026, 9, 4, 14, 0, 0, tzinfo=timezone.utc)
    run_id = new_run_id("webcopy", "home", now=home_time)
    draft = tmp_path / "draft.md"
    draft.write_text("We climb trees in Kent. We clear the site before we leave.\n")

    # 1. The rubric onboarding wrote is readable by eval.py.
    evaluated = run("eval.py", "--client", CLIENT, "--workflow", "webcopy",
                    "--copy", str(draft), "--memory-root", str(workspace))
    assert evaluated.returncode == 0, evaluated.stderr
    deterministic = json.loads(evaluated.stdout)
    assert deterministic["invariant_failed"] is False

    # 2. The trace lands in the run directory named by that run id.
    traced = subprocess.run(
        [sys.executable, str(REPO_ROOT / "tools" / "trace.py"), "write",
         "--client", CLIENT, "--run-id", run_id, "--payload", "-",
         "--memory-root", str(workspace)],
        input=json.dumps(trace_payload(run_id, deterministic)),
        capture_output=True, text=True,
    )
    assert traced.returncode == 0, traced.stderr
    run_directory = Path(json.loads(traced.stdout)["written"]).parent

    # 3. approve.py finds that same directory and ships the copy.
    (run_directory / "draft.md").write_text(draft.read_text())
    approved = run("approve.py", "--client", CLIENT, "--run-id", run_id,
                   "--decision", "approve", "--copy", str(draft),
                   "--memory-root", str(workspace))
    assert approved.returncode == 0, approved.stderr

    # 3b. Ship a second, later run for a different page whose slug shares a
    # suffix with "home" -- "home" vs "new-home" is the pair that broke
    # find_latest_shipped's slug matching in Task 5. If the lookup merely
    # returned the newest shipped run regardless of slug, this would make
    # the "home" lookup below return new-home's copy instead.
    other_run_id = new_run_id("webcopy", "new-home", now=new_home_time)
    other_draft = tmp_path / "other-draft.md"
    other_draft.write_text("We fell dangerous trees fast. Call before the storm.\n")

    other_evaluated = run("eval.py", "--client", CLIENT, "--workflow", "webcopy",
                          "--copy", str(other_draft), "--memory-root", str(workspace))
    assert other_evaluated.returncode == 0, other_evaluated.stderr
    other_deterministic = json.loads(other_evaluated.stdout)

    other_traced = subprocess.run(
        [sys.executable, str(REPO_ROOT / "tools" / "trace.py"), "write",
         "--client", CLIENT, "--run-id", other_run_id, "--payload", "-",
         "--memory-root", str(workspace)],
        input=json.dumps(trace_payload(other_run_id, other_deterministic)),
        capture_output=True, text=True,
    )
    assert other_traced.returncode == 0, other_traced.stderr
    other_run_directory = Path(json.loads(other_traced.stdout)["written"]).parent

    (other_run_directory / "draft.md").write_text(other_draft.read_text())
    other_approved = run("approve.py", "--client", CLIENT, "--run-id", other_run_id,
                         "--decision", "approve", "--copy", str(other_draft),
                         "--memory-root", str(workspace))
    assert other_approved.returncode == 0, other_approved.stderr

    # 4. Episodic lookup for "home" finds home's own shipped copy, not the
    # chronologically later new-home run.
    shipped = find_latest_shipped(workspace, CLIENT, "home")
    assert shipped is not None
    assert shipped.read_text() == draft.read_text()
    assert (run_directory / "trace.json").is_file()


def test_an_invariant_failure_is_visible_to_the_loop(workspace, tmp_path):
    """The teeth: uncited statistics fail an invariant criterion, not a tunable one."""
    draft = tmp_path / "draft.md"
    draft.write_text("Storm damage rose 40% across Kent last year.\n")
    evaluated = run("eval.py", "--client", CLIENT, "--workflow", "webcopy",
                    "--copy", str(draft), "--memory-root", str(workspace))
    assert evaluated.returncode == 0, evaluated.stderr
    result = json.loads(evaluated.stdout)
    assert result["invariant_failed"] is True
    failed = [c for c in result["criteria"] if c["status"] == "fail"]
    assert [c["id"] for c in failed] == ["no-fabricated-stats"]


def test_ingested_data_diagnoses_to_the_expected_stage(workspace):
    """A real-shaped GSC export maps to the funnel stage the table promises."""
    ingested = run("ingest_gsc.py", "--client", CLIENT,
                   "--csv", str(FIXTURES / "gsc_export.csv"),
                   "--period", "2026-08-01:2026-08-31",
                   "--memory-root", str(workspace))
    assert ingested.returncode == 0, ingested.stderr
    artifact = json.loads(Path(json.loads(ingested.stdout)["written"]).read_text())
    by_url = {p["url"]: p for p in artifact["pages"]}

    # 4200 impressions at 0.36% CTR: plenty of demand, nobody clicking.
    assert weak_stage(by_url["/services/tree-surgery"]) == "top"
    # 5000 impressions at 2.4%: healthy, and GSC cannot see further down.
    assert weak_stage(by_url["/"]) is None
    # No data at all is never a diagnosis.
    assert weak_stage(by_url["/contact"]) is None


def test_spine_failure_is_distinguishable_from_a_failing_evaluation(tmp_path):
    """Exit 2 means stop; exit 0 with failures means regenerate. Never confused."""
    draft = tmp_path / "draft.md"
    draft.write_text("anything\n")
    missing_rubric = run("eval.py", "--client", CLIENT, "--workflow", "webcopy",
                         "--copy", str(draft), "--memory-root", str(tmp_path))
    assert missing_rubric.returncode == 2
    assert missing_rubric.stdout == ""
    assert "rubric not found" in missing_rubric.stderr

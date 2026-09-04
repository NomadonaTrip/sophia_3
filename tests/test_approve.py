import json
import subprocess
import sys
from pathlib import Path

import pytest

from tools.approve import ApprovalError, edit_magnitude, record_decision
from tools.episodic import run_dir

REPO_ROOT = Path(__file__).resolve().parent.parent
RUN_ID = "20260904T130500Z-webcopy-home"


@pytest.fixture
def staged(tmp_path: Path) -> Path:
    d = run_dir(tmp_path, "orban-forest", RUN_ID, create=True)
    (d / "draft.md").write_text("One\nTwo\nThree\n")
    return tmp_path


# --- edit magnitude ---

def test_edit_magnitude_zero_when_identical():
    assert edit_magnitude("a\nb\n", "a\nb\n") == 0


def test_edit_magnitude_counts_changed_lines():
    assert edit_magnitude("a\nb\nc\n", "a\nB\nc\n") == 2  # one removed, one added


def test_edit_magnitude_counts_pure_additions():
    assert edit_magnitude("a\n", "a\nb\n") == 1


# --- record_decision ---

def test_approve_writes_shipped_copy(staged):
    copy_path = staged / "final.md"
    copy_path.write_text("One\nTwo\nThree\n")
    record = record_decision(
        staged, "orban-forest", RUN_ID, "approve", copy_path=copy_path
    )
    shipped = run_dir(staged, "orban-forest", RUN_ID) / "shipped.md"
    assert shipped.read_text() == "One\nTwo\nThree\n"
    assert record["decision"] == "approve"
    assert record["edit_magnitude"] is None
    assert record["decided_at"].endswith("Z")


def test_edit_writes_shipped_copy_and_records_magnitude(staged):
    copy_path = staged / "final.md"
    copy_path.write_text("One\nTWO\nThree\n")
    record = record_decision(
        staged, "orban-forest", RUN_ID, "edit", copy_path=copy_path,
        note="Tightened the second line.",
    )
    assert (run_dir(staged, "orban-forest", RUN_ID) / "shipped.md").is_file()
    assert record["edit_magnitude"] == 2
    assert record["note"] == "Tightened the second line."


def test_reject_writes_no_shipped_copy(staged):
    record = record_decision(
        staged, "orban-forest", RUN_ID, "reject", note="Wrong angle entirely."
    )
    assert not (run_dir(staged, "orban-forest", RUN_ID) / "shipped.md").exists()
    assert record["decision"] == "reject"
    assert record["edit_magnitude"] is None


def test_decision_record_is_persisted(staged):
    copy_path = staged / "final.md"
    copy_path.write_text("One\nTwo\nThree\n")
    record_decision(staged, "orban-forest", RUN_ID, "approve", copy_path=copy_path)
    persisted = json.loads(
        (run_dir(staged, "orban-forest", RUN_ID) / "decision.json").read_text()
    )
    assert persisted["run_id"] == RUN_ID
    assert persisted["client"] == "orban-forest"


def test_edit_magnitude_is_null_when_no_draft_exists(tmp_path):
    run_dir(tmp_path, "orban-forest", RUN_ID, create=True)
    copy_path = tmp_path / "final.md"
    copy_path.write_text("x\n")
    record = record_decision(
        tmp_path, "orban-forest", RUN_ID, "edit", copy_path=copy_path
    )
    assert record["edit_magnitude"] is None


def test_unknown_decision_is_rejected(staged):
    with pytest.raises(ApprovalError, match="decision"):
        record_decision(staged, "orban-forest", RUN_ID, "maybe")


def test_approve_without_copy_is_rejected(staged):
    with pytest.raises(ApprovalError, match="requires --copy"):
        record_decision(staged, "orban-forest", RUN_ID, "approve")


def test_reject_with_copy_is_rejected(staged):
    copy_path = staged / "final.md"
    copy_path.write_text("x\n")
    with pytest.raises(ApprovalError, match="reject"):
        record_decision(
            staged, "orban-forest", RUN_ID, "reject", copy_path=copy_path
        )


def test_missing_run_directory_is_rejected(tmp_path):
    copy_path = tmp_path / "final.md"
    copy_path.write_text("x\n")
    with pytest.raises(ApprovalError, match="run directory"):
        record_decision(
            tmp_path, "orban-forest", "no-such-run", "approve", copy_path=copy_path
        )


# --- CLI ---

def test_cli_records_an_approval(staged):
    copy_path = staged / "final.md"
    copy_path.write_text("One\nTwo\nThree\n")
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "tools" / "approve.py"),
         "--client", "orban-forest", "--run-id", RUN_ID,
         "--decision", "approve", "--copy", str(copy_path),
         "--memory-root", str(staged)],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["decision"] == "approve"


def test_cli_exits_two_on_bad_input(staged):
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "tools" / "approve.py"),
         "--client", "orban-forest", "--run-id", RUN_ID,
         "--decision", "approve", "--memory-root", str(staged)],
        capture_output=True, text=True,
    )
    assert proc.returncode == 2
    assert "requires --copy" in proc.stderr

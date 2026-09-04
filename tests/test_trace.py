import json
import subprocess
import sys
from pathlib import Path

import pytest

from tools.trace import TRACE_SCHEMA_VERSION, TraceError, validate_trace, write_trace

REPO_ROOT = Path(__file__).resolve().parent.parent


def valid_payload(**overrides) -> dict:
    payload = {
        "schema_version": TRACE_SCHEMA_VERSION,
        "run_id": "20260904T130500Z-webcopy-home",
        "client": "orban-forest",
        "workflow": "webcopy",
        "mode": "generate",
        "started_at": "2026-09-04T13:05:00Z",
        "iterations": [
            {
                "n": 1,
                "criteria": [
                    {"id": "campfire-voice", "verdict": "fail",
                     "confidence": 0.7, "rationale": "Reads like a brochure."}
                ],
                "deterministic": {"criteria": [], "invariant_failed": False},
                "alternatives_considered": ["Open on the storm instead."],
                "decision": "regenerate",
                "reason": "Invariant voice criterion failed.",
            }
        ],
        "outcome": "passed",
        "iteration_count": 1,
        "escalation": None,
        "signal_links": [],
    }
    payload.update(overrides)
    return payload


def test_valid_payload_passes_validation():
    validate_trace(valid_payload())


def test_missing_required_key_is_rejected():
    payload = valid_payload()
    del payload["outcome"]
    with pytest.raises(TraceError, match="outcome"):
        validate_trace(payload)


def test_wrong_schema_version_is_rejected():
    with pytest.raises(TraceError, match="schema_version"):
        validate_trace(valid_payload(schema_version="2"))


def test_unknown_outcome_is_rejected():
    with pytest.raises(TraceError, match="outcome"):
        validate_trace(valid_payload(outcome="mostly fine"))


def test_unknown_mode_is_rejected():
    with pytest.raises(TraceError, match="mode"):
        validate_trace(valid_payload(mode="freestyle"))


def test_escalated_outcome_requires_a_sticking_point():
    with pytest.raises(TraceError, match="sticking_point"):
        validate_trace(valid_payload(outcome="escalated", escalation=None))


def test_escalated_outcome_with_sticking_point_is_valid():
    validate_trace(
        valid_payload(outcome="escalated", escalation={"sticking_point": "Voice."})
    )


def test_iterations_must_not_be_empty():
    with pytest.raises(TraceError, match="iterations"):
        validate_trace(valid_payload(iterations=[]))


def test_iteration_count_must_match_iterations_length():
    with pytest.raises(TraceError, match="iteration_count"):
        validate_trace(valid_payload(iteration_count=3))


def test_criterion_confidence_must_be_between_zero_and_one():
    payload = valid_payload()
    payload["iterations"][0]["criteria"][0]["confidence"] = 1.7
    with pytest.raises(TraceError, match="confidence"):
        validate_trace(payload)


def test_criterion_requires_a_rationale():
    payload = valid_payload()
    del payload["iterations"][0]["criteria"][0]["rationale"]
    with pytest.raises(TraceError, match="rationale"):
        validate_trace(payload)


def test_signal_links_entries_need_edit_and_signal():
    with pytest.raises(TraceError, match="signal"):
        validate_trace(valid_payload(signal_links=[{"edit": "Tightened the title."}]))


def test_write_trace_persists_to_the_run_directory(tmp_path):
    payload = valid_payload()
    written = write_trace(tmp_path, "orban-forest", payload["run_id"], payload)
    assert written == (
        tmp_path / "clients" / "orban-forest" / "episodic" / payload["run_id"]
        / "trace.json"
    )
    assert json.loads(written.read_text())["client"] == "orban-forest"


def test_write_trace_rejects_invalid_payload_without_writing(tmp_path):
    payload = valid_payload(outcome="nope")
    with pytest.raises(TraceError):
        write_trace(tmp_path, "orban-forest", payload["run_id"], payload)
    assert not (tmp_path / "clients").exists()


def test_cli_writes_from_a_file(tmp_path):
    payload_path = tmp_path / "payload.json"
    payload_path.write_text(json.dumps(valid_payload()))
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "tools" / "trace.py"), "write",
         "--client", "orban-forest",
         "--run-id", "20260904T130500Z-webcopy-home",
         "--payload", str(payload_path),
         "--memory-root", str(tmp_path)],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert Path(json.loads(proc.stdout)["written"]).is_file()


def test_cli_reads_payload_from_stdin(tmp_path):
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "tools" / "trace.py"), "write",
         "--client", "orban-forest",
         "--run-id", "20260904T130500Z-webcopy-home",
         "--payload", "-",
         "--memory-root", str(tmp_path)],
        input=json.dumps(valid_payload()), capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr


def test_cli_exits_two_on_invalid_payload(tmp_path):
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "tools" / "trace.py"), "write",
         "--client", "orban-forest", "--run-id", "r1", "--payload", "-",
         "--memory-root", str(tmp_path)],
        input=json.dumps(valid_payload(outcome="nope")),
        capture_output=True, text=True,
    )
    assert proc.returncode == 2
    assert "outcome" in proc.stderr

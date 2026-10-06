import json
import subprocess
import sys
from pathlib import Path

import pytest

from tools.onboarding import (
    SECTIONS,
    OnboardingError,
    discard_messages,
    keep_messages,
    log_message,
    reset,
    save_decision,
    status,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
CLIENT = "orban-forest"


def _onboarding_dir(root: Path) -> Path:
    return root / "clients" / CLIENT / "onboarding"


def _settle(root: Path, *sections: str) -> None:
    for section in sections:
        log_message(root, CLIENT, section, "sophia", f"Question about {section}?")
        log_message(root, CLIENT, section, "operator", f"Answer about {section}.")
        save_decision(root, CLIENT, section, {"summary": f"{section} settled"})


# --- status ---

def test_new_client_starts_at_seed(tmp_path):
    s = status(tmp_path, CLIENT)
    assert s["next"] == "seed"
    assert s["settled"] == []
    assert s["in_progress"] == {}
    assert s["profile_files"] == {
        "business.md": False, "icp.md": False,
        "voice.md": False, "evals/webcopy.md": False,
    }


def test_status_detects_existing_profile_files(tmp_path):
    client_dir = tmp_path / "clients" / CLIENT
    (client_dir / "evals").mkdir(parents=True)
    (client_dir / "voice.md").write_text("x\n")
    (client_dir / "evals" / "webcopy.md").write_text("x\n")
    files = status(tmp_path, CLIENT)["profile_files"]
    assert files["voice.md"] is True
    assert files["evals/webcopy.md"] is True
    assert files["business.md"] is False


# --- log ---

def test_logged_messages_resume_an_unsettled_section(tmp_path):
    _settle(tmp_path, "seed")
    log_message(tmp_path, CLIENT, "business", "sophia", "What do they sell?")
    log_message(tmp_path, CLIENT, "business", "operator", "AI automations.")
    s = status(tmp_path, CLIENT)
    assert s["next"] == "business"
    texts = [m["text"] for m in s["in_progress"]["business"]]
    assert texts == ["What do they sell?", "AI automations."]
    assert s["in_progress"]["business"][1]["role"] == "operator"


def test_log_rejects_unknown_section(tmp_path):
    with pytest.raises(OnboardingError, match="section"):
        log_message(tmp_path, CLIENT, "pricing", "operator", "x")


def test_log_rejects_unknown_role(tmp_path):
    with pytest.raises(OnboardingError, match="role"):
        log_message(tmp_path, CLIENT, "business", "assistant", "x")


def test_log_rejects_empty_text(tmp_path):
    with pytest.raises(OnboardingError, match="empty"):
        log_message(tmp_path, CLIENT, "business", "operator", "   ")


def test_client_name_cannot_escape_memory(tmp_path):
    with pytest.raises(OnboardingError, match="client"):
        log_message(tmp_path, "../elsewhere", "business", "operator", "x")


# --- save ---

def test_save_settles_a_section_and_advances_next(tmp_path):
    _settle(tmp_path, "seed")
    s = status(tmp_path, CLIENT)
    assert s["settled"] == ["seed"]
    assert s["next"] == "business"
    assert s["decisions"]["seed"]["decision"] == {"summary": "seed settled"}


def test_settled_section_messages_are_not_in_progress(tmp_path):
    _settle(tmp_path, "seed")
    assert "seed" not in status(tmp_path, CLIENT)["in_progress"]


def test_settled_section_with_messages_awaits_discard_answer(tmp_path):
    _settle(tmp_path, "seed")
    assert status(tmp_path, CLIENT)["discard_pending"] == ["seed"]


def test_resaving_a_section_replaces_it(tmp_path):
    _settle(tmp_path, "seed")
    save_decision(tmp_path, CLIENT, "seed", {"summary": "corrected"})
    s = status(tmp_path, CLIENT)
    assert s["decisions"]["seed"]["decision"] == {"summary": "corrected"}
    assert s["settled"] == ["seed"]


def test_save_rejects_empty_decision(tmp_path):
    for empty in ({}, [], "", None):
        with pytest.raises(OnboardingError, match="empty"):
            save_decision(tmp_path, CLIENT, "seed", empty)


def test_save_rejects_unknown_section(tmp_path):
    with pytest.raises(OnboardingError, match="section"):
        save_decision(tmp_path, CLIENT, "pricing", {"x": 1})


# --- discard / keep ---

def test_discard_before_save_is_refused(tmp_path):
    log_message(tmp_path, CLIENT, "seed", "operator", "Samples are in intake.md")
    with pytest.raises(OnboardingError, match="not settled"):
        discard_messages(tmp_path, CLIENT, "seed")
    assert status(tmp_path, CLIENT)["in_progress"]["seed"]


def test_discard_after_save_removes_only_that_section(tmp_path):
    _settle(tmp_path, "seed")
    log_message(tmp_path, CLIENT, "business", "operator", "Half an answer")
    removed = discard_messages(tmp_path, CLIENT, "seed")
    assert removed == 2
    s = status(tmp_path, CLIENT)
    assert s["discard_pending"] == []
    assert s["decisions"]["seed"]["messages"] == "discarded"
    assert [m["text"] for m in s["in_progress"]["business"]] == ["Half an answer"]


def test_keep_stops_the_discard_question(tmp_path):
    _settle(tmp_path, "seed")
    keep_messages(tmp_path, CLIENT, "seed")
    s = status(tmp_path, CLIENT)
    assert s["discard_pending"] == []
    assert s["decisions"]["seed"]["messages"] == "kept"


def test_keep_before_save_is_refused(tmp_path):
    with pytest.raises(OnboardingError, match="not settled"):
        keep_messages(tmp_path, CLIENT, "seed")


# --- reset ---

def test_full_reset_returns_to_seed(tmp_path):
    _settle(tmp_path, "seed", "business")
    log_message(tmp_path, CLIENT, "customer", "operator", "Half an answer")
    reset(tmp_path, CLIENT)
    s = status(tmp_path, CLIENT)
    assert s["next"] == "seed"
    assert s["settled"] == []
    assert s["in_progress"] == {}


def test_section_reset_clears_it_and_flags_later_sections(tmp_path):
    _settle(tmp_path, "seed", "business", "customer")
    reset(tmp_path, CLIENT, "business")
    s = status(tmp_path, CLIENT)
    assert "business" not in s["decisions"]
    assert s["settled"] == ["seed", "customer"]
    assert s["recheck"] == ["customer"]
    assert s["next"] == "business"
    assert "business" not in s["in_progress"]
    assert s["discard_pending"] == ["seed", "customer"]


def test_resaving_a_recheck_section_clears_the_flag(tmp_path):
    _settle(tmp_path, "seed", "business", "customer")
    reset(tmp_path, CLIENT, "business")
    _settle(tmp_path, "business")
    s = status(tmp_path, CLIENT)
    assert s["recheck"] == ["customer"]
    assert s["next"] == "customer"
    save_decision(tmp_path, CLIENT, "customer", {"summary": "still holds"})
    s = status(tmp_path, CLIENT)
    assert s["recheck"] == []
    assert s["next"] == "constraints"


def test_reset_never_touches_profile_files(tmp_path):
    _settle(tmp_path, "seed")
    client_dir = tmp_path / "clients" / CLIENT
    (client_dir / "voice.md").write_text("keep me\n")
    reset(tmp_path, CLIENT)
    assert (client_dir / "voice.md").read_text() == "keep me\n"


def test_reset_of_a_client_with_no_progress_is_harmless(tmp_path):
    reset(tmp_path, CLIENT)
    assert status(tmp_path, CLIENT)["next"] == "seed"


# --- completion ---

def test_next_is_none_once_every_section_is_settled(tmp_path):
    _settle(tmp_path, *SECTIONS)
    assert status(tmp_path, CLIENT)["next"] is None


def test_corrupt_session_log_is_a_failure_not_a_guess(tmp_path):
    _onboarding_dir(tmp_path).mkdir(parents=True)
    (_onboarding_dir(tmp_path) / "session.jsonl").write_text("{not json\n")
    with pytest.raises(OnboardingError, match="session"):
        status(tmp_path, CLIENT)


# --- CLI ---

def _cli(*args: str, stdin: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / "tools" / "onboarding.py"), *args],
        input=stdin, capture_output=True, text=True,
    )


def test_cli_round_trip(tmp_path):
    root = ["--client", CLIENT, "--memory-root", str(tmp_path)]
    proc = _cli("log", *root, "--section", "seed", "--role", "operator",
                "--text", "-", stdin="Samples are in intake.md")
    assert proc.returncode == 0, proc.stderr

    proc = _cli("save", *root, "--section", "seed", "--payload", "-",
                stdin=json.dumps({"samples": ["intake.md"]}))
    assert proc.returncode == 0, proc.stderr

    proc = _cli("discard", *root, "--section", "seed")
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["removed"] == 1

    proc = _cli("status", *root)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["next"] == "business"

    proc = _cli("reset", *root)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(_cli("status", *root).stdout)["next"] == "seed"


def test_cli_exits_two_on_bad_input(tmp_path):
    proc = _cli("discard", "--client", CLIENT, "--memory-root", str(tmp_path),
                "--section", "seed")
    assert proc.returncode == 2
    assert proc.stdout == ""
    assert "not settled" in proc.stderr


def test_cli_exits_two_on_malformed_payload(tmp_path):
    proc = _cli("save", "--client", CLIENT, "--memory-root", str(tmp_path),
                "--section", "seed", "--payload", "-", stdin="{nope")
    assert proc.returncode == 2
    assert proc.stdout == ""

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS = REPO_ROOT / ".claude" / "skills"
SKILL_NAMES = ("research-first", "voice-match", "gen-eval-loop")


@pytest.mark.parametrize("name", SKILL_NAMES)
def test_skill_exists_with_frontmatter(name):
    path = SKILLS / name / "SKILL.md"
    assert path.is_file(), path
    match = re.search(r"\A---\s*$(.*?)^---\s*$", path.read_text(), re.MULTILINE | re.DOTALL)
    assert match is not None, f"{name} has no frontmatter"
    front = yaml.safe_load(match.group(1))
    assert front["name"] == name
    assert front["description"].strip()


@pytest.fixture
def loop_text() -> str:
    return (SKILLS / "gen-eval-loop" / "SKILL.md").read_text()


def test_loop_states_the_default_cap(loop_text):
    assert "3" in loop_text
    assert "cap" in loop_text.lower()


def test_loop_states_that_an_invariant_failure_never_ships(loop_text):
    lowered = loop_text.lower()
    assert "never ship" in lowered or "never ships" in lowered
    assert "invariant" in lowered


def test_loop_requires_a_trace_on_every_outcome(loop_text):
    assert "tools/trace.py" in loop_text
    assert "escalat" in loop_text.lower()


def test_loop_forbids_eyeballing_deterministic_criteria_on_spine_failure(loop_text):
    assert "exit code 2" in loop_text or "exits 2" in loop_text
    assert "stop" in loop_text.lower()


def test_loop_invokes_the_research_first_gate(loop_text):
    assert "research-first" in loop_text


def test_loop_cites_the_real_eval_cli_signature(loop_text):
    """Skills drift from tools. Assert the invocation still matches Task 4."""
    assert "tools/eval.py" in loop_text
    for flag in ("--client", "--workflow", "--copy"):
        assert flag in loop_text, flag


def test_research_first_names_all_four_required_inputs():
    text = (SKILLS / "research-first" / "SKILL.md").read_text().lower()
    for required in ("voice", "business", "icp", "rubric", "research"):
        assert required in text, required


def test_research_first_forbids_inventing_missing_inputs():
    text = (SKILLS / "research-first" / "SKILL.md").read_text().lower()
    assert "escalate" in text
    assert "never invent" in text or "do not invent" in text


def test_research_first_cites_the_real_retrieval_cli():
    text = (SKILLS / "research-first" / "SKILL.md").read_text()
    assert "python -m interfaces.retrieval" in text
    assert "--client" in text


def test_voice_match_requires_observable_markers_not_adjectives():
    text = (SKILLS / "voice-match" / "SKILL.md").read_text().lower()
    assert "adjective" in text
    assert "marker" in text

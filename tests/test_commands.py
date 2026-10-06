import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
COMMANDS = REPO_ROOT / ".claude" / "commands"
COMMAND_NAMES = ("onboard", "webcopy", "revise", "client")


@pytest.mark.parametrize("name", COMMAND_NAMES)
def test_command_exists_with_a_description(name):
    path = COMMANDS / f"{name}.md"
    assert path.is_file(), path
    match = re.search(r"\A---\s*$(.*?)^---\s*$", path.read_text(), re.MULTILINE | re.DOTALL)
    assert match is not None, f"{name} has no frontmatter"
    assert yaml.safe_load(match.group(1))["description"].strip()


@pytest.fixture
def onboard() -> str:
    return (COMMANDS / "onboard.md").read_text()


def test_onboard_refuses_without_seed_material(onboard):
    lowered = onboard.lower()
    assert "seed material" in lowered
    assert "refuse" in lowered or "stop" in lowered
    assert "cannot bootstrap" in lowered or "never invent" in lowered


def test_onboard_writes_all_four_artifacts(onboard):
    for artifact in ("business.md", "icp.md", "voice.md", "evals/webcopy.md"):
        assert artifact in onboard, artifact


def test_onboard_seeds_both_rubric_sections(onboard):
    assert "## Invariant" in onboard
    assert "## Tunable" in onboard


def test_onboard_uses_the_voice_match_skill(onboard):
    assert "voice-match" in onboard


def test_onboard_verify_step_does_not_blame_the_rubric_for_uncited_stats(onboard):
    """I2: a sample failing no-fabricated-stats usually means its statistics
    are uncited, not that the rubric is wrong -- the old unqualified "the
    rubric is wrong" language sent operators to weaken correct boilerplate.
    """
    assert "no-fabricated-stats" in onboard
    assert "uncited" in onboard.lower()


def test_onboard_resumes_from_saved_state(onboard):
    assert "tools/onboarding.py status" in onboard
    assert "resume" in onboard.lower()


def test_onboard_logs_every_message(onboard):
    assert "tools/onboarding.py log" in onboard


def test_onboard_saves_then_asks_before_discarding(onboard):
    save = onboard.index("tools/onboarding.py save")
    discard = onboard.index("tools/onboarding.py discard")
    assert save < discard
    assert "tools/onboarding.py keep" in onboard


def test_onboard_offers_restart_and_confirms_before_reset(onboard):
    assert "tools/onboarding.py reset" in onboard
    lowered = onboard.lower()
    assert "restart" in lowered
    assert "confirm" in lowered


def test_onboard_writes_the_profile_from_saved_decisions(onboard):
    assert "decisions.json" in onboard


def test_onboard_asks_before_overwriting_profile_files(onboard):
    assert "profile_files" in onboard
    assert "overwrit" in onboard.lower()


def test_session_log_is_git_ignored():
    text = (REPO_ROOT / ".gitignore").read_text()
    assert "memory/clients/*/onboarding/session.jsonl" in text


@pytest.fixture
def revise() -> str:
    return (COMMANDS / "revise.md").read_text()


def test_revise_reads_shipped_copy_and_escalates_without_it(revise):
    assert "shipped.md" in revise
    assert "escalate" in revise.lower()


def test_revise_documents_the_funnel_mapping(revise):
    for stage in ("top", "mid", "bottom"):
        assert stage in revise.lower()
    assert "message-match" in revise.lower()


def test_revise_surfaces_the_sample_warning(revise):
    assert "sample_warning" in revise
    assert "provisional" in revise.lower()


def test_revise_cites_both_ingestors(revise):
    assert "tools/ingest_gsc.py" in revise
    assert "tools/ingest_ga4.py" in revise


def test_revise_routes_screenshots_through_the_same_ingestor(revise):
    assert "--source screenshot" in revise


def test_revise_runs_edits_through_the_same_loop(revise):
    assert "gen-eval-loop" in revise


def test_revise_links_each_edit_to_its_signal(revise):
    assert "signal_links" in revise


def test_revise_diagnoses_via_the_weak_stage_cli(revise):
    """I6: interfaces/performance.py's weak_stage is tested but was dead at
    runtime -- revise.md restated the funnel table in prose with no
    thresholds. It must now call the CLI the tests certify.
    """
    assert "interfaces.performance weak-stage" in revise
    assert "--artifact" in revise


def test_revise_obtains_run_id_from_the_episodic_cli(revise):
    """C1: the agent must obtain a run id from tools/episodic.py rather than
    inventing one, so a later find_latest_shipped lookup can match it.
    """
    assert "tools/episodic.py new-run-id" in revise


@pytest.fixture
def webcopy() -> str:
    return (COMMANDS / "webcopy.md").read_text()


def test_webcopy_delegates_to_the_agent_and_persists_the_decision(webcopy):
    assert "webcopy" in webcopy
    assert "tools/approve.py" in webcopy
    for decision in ("approve", "edit", "reject"):
        assert decision in webcopy


def test_webcopy_obtains_run_id_from_the_episodic_cli(webcopy):
    """C1: the agent must obtain a run id from tools/episodic.py rather than
    inventing one, so a later find_latest_shipped lookup can match it.
    """
    assert "tools/episodic.py new-run-id" in webcopy


def test_client_command_switches_context():
    text = (COMMANDS / "client.md").read_text()
    assert "voice.md" in text and "business.md" in text and "icp.md" in text


def test_routing_doc_names_the_workflows_and_invariants():
    text = (REPO_ROOT / "CLAUDE.md").read_text()
    assert "webcopy" in text
    assert "invariant" in text.lower()
    assert "/onboard" in text and "/revise" in text and "/client" in text


def test_routing_doc_states_the_delegation_boundary():
    text = (REPO_ROOT / "CLAUDE.md").read_text().lower()
    assert "delegat" in text
    assert "propose" in text  # propose, don't apply

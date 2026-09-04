import json
import subprocess
import sys
from pathlib import Path

import pytest

from tools.eval import (
    CHECKS,
    UnknownCheckError,
    banned_phrases,
    evaluate,
    fabricated_stat_scan,
    length_bands,
    passive_rate,
)
from tools.rubric import Criterion, Rubric, load_rubric

FIXTURES = Path(__file__).parent / "fixtures"
REPO_ROOT = Path(__file__).resolve().parent.parent


# --- banned_phrases ---

def test_banned_phrases_passes_when_absent():
    passed, detail = banned_phrases("Plain honest words.", {"phrases": ["leverage"]})
    assert passed is True
    assert detail == ""


def test_banned_phrases_fails_and_names_the_phrase():
    passed, detail = banned_phrases(
        "We leverage synergy.", {"phrases": ["leverage", "unlock"]}
    )
    assert passed is False
    assert "leverage" in detail
    assert "unlock" not in detail


def test_banned_phrases_is_case_insensitive():
    passed, _ = banned_phrases("We Leverage things.", {"phrases": ["leverage"]})
    assert passed is False


def test_banned_phrases_matches_whole_words_only():
    """'unlock' must not fire on 'unlockable' being absent -- nor on 'lock'."""
    passed, _ = banned_phrases("The lock is old.", {"phrases": ["unlock"]})
    assert passed is True


def test_banned_phrases_matches_multiword_phrase_across_a_newline():
    passed, detail = banned_phrases(
        "We leverage\nsynergy for you.", {"phrases": ["leverage synergy"]}
    )
    assert passed is False
    assert "leverage synergy" in detail


def test_banned_phrases_matches_phrase_with_non_word_edge_character():
    passed, detail = banned_phrases(
        "Act now! this is the moment.", {"phrases": ["!"]}
    )
    assert passed is False
    assert "!" in detail


# --- length_bands ---

def test_length_bands_passes_within_band():
    copy = "<!-- section: h1 -->\nWe climb trees in Kent\n"
    passed, detail = length_bands(copy, {"h1": [3, 12]})
    assert passed is True, detail


def test_length_bands_fails_when_too_short():
    copy = "<!-- section: h1 -->\nTrees\n"
    passed, detail = length_bands(copy, {"h1": [3, 12]})
    assert passed is False
    assert "h1" in detail and "1" in detail


def test_length_bands_fails_when_too_long():
    copy = "<!-- section: h1 -->\n" + " ".join(["word"] * 20) + "\n"
    passed, detail = length_bands(copy, {"h1": [3, 12]})
    assert passed is False


def test_length_bands_fails_when_named_section_missing():
    passed, detail = length_bands("<!-- section: h1 -->\nHello there now\n", {"hero_subhead": [10, 30]})
    assert passed is False
    assert "hero_subhead" in detail and "missing" in detail.lower()


def test_length_bands_ignores_unnamed_sections():
    copy = "<!-- section: h1 -->\nWe climb trees in Kent\n<!-- section: footer -->\nx\n"
    passed, _ = length_bands(copy, {"h1": [3, 12]})
    assert passed is True


# --- passive_rate ---

def test_passive_rate_passes_on_active_prose():
    copy = "We climb the tree. We cut the branch. We clear the site."
    passed, detail = passive_rate(copy, {"max_rate": 0.15})
    assert passed is True, detail


def test_passive_rate_fails_on_passive_prose():
    copy = (
        "The tree was climbed by us. The branch was cut. "
        "The site was cleared. The invoice was sent."
    )
    passed, detail = passive_rate(copy, {"max_rate": 0.15})
    assert passed is False
    assert "0." in detail


def test_passive_rate_on_empty_copy_passes():
    passed, _ = passive_rate("", {"max_rate": 0.15})
    assert passed is True


# --- fabricated_stat_scan ---

def test_fabricated_stat_scan_passes_when_stat_is_cited():
    copy = "Storm damage rose 40% last year [source: Kent Council 2025]."
    passed, detail = fabricated_stat_scan(copy, {})
    assert passed is True, detail


def test_fabricated_stat_scan_flags_uncited_percentage():
    passed, detail = fabricated_stat_scan("Storm damage rose 40% last year.", {})
    assert passed is False
    assert "40%" in detail


def test_fabricated_stat_scan_flags_uncited_large_number():
    passed, detail = fabricated_stat_scan("We have served 12,000 homeowners.", {})
    assert passed is False
    assert "12,000" in detail


def test_fabricated_stat_scan_ignores_small_bare_numbers():
    """Prices, counts and years are not statistical claims."""
    passed, detail = fabricated_stat_scan(
        "Call us on day 2 of the job in 2026 for 3 quotes.", {}
    )
    assert passed is True, detail


# --- dispatch table ---

def test_checks_table_holds_exactly_the_four_checks():
    assert set(CHECKS) == {
        "banned_phrases", "length_bands", "passive_rate", "fabricated_stat_scan",
    }


# --- evaluate ---

def _rubric(*criteria: Criterion) -> Rubric:
    return Rubric(criteria=list(criteria))


def test_evaluate_reports_each_deterministic_criterion():
    rubric = _rubric(
        Criterion(id="banned-phrases", type="deterministic", invariant=False,
                  check="banned_phrases", config={"phrases": ["leverage"]}),
    )
    result = evaluate("Plain words.", rubric)
    assert result["criteria"] == [
        {"id": "banned-phrases", "type": "deterministic", "invariant": False,
         "status": "pass", "detail": ""}
    ]
    assert result["invariant_failed"] is False


def test_evaluate_skips_judgment_criteria():
    """Judgment criteria are scored by the subagent, not by this tool."""
    rubric = _rubric(
        Criterion(id="campfire-voice", type="judgment", invariant=True,
                  criterion="warm"),
    )
    assert evaluate("anything", rubric)["criteria"] == []


def test_evaluate_sets_invariant_failed_on_invariant_failure():
    rubric = _rubric(
        Criterion(id="no-fabricated-stats", type="deterministic", invariant=True,
                  check="fabricated_stat_scan", config={}),
    )
    result = evaluate("Damage rose 40% last year.", rubric)
    assert result["criteria"][0]["status"] == "fail"
    assert result["invariant_failed"] is True


def test_evaluate_tunable_failure_does_not_set_invariant_failed():
    rubric = _rubric(
        Criterion(id="banned-phrases", type="deterministic", invariant=False,
                  check="banned_phrases", config={"phrases": ["leverage"]}),
    )
    result = evaluate("We leverage things.", rubric)
    assert result["criteria"][0]["status"] == "fail"
    assert result["invariant_failed"] is False


def test_unknown_check_is_a_hard_error_not_a_skipped_criterion():
    rubric = _rubric(
        Criterion(id="x", type="deterministic", invariant=False, check="vibes_check"),
    )
    with pytest.raises(UnknownCheckError, match="vibes_check"):
        evaluate("anything", rubric)


# --- CLI ---

@pytest.fixture
def memory_root(tmp_path: Path) -> Path:
    evals = tmp_path / "clients" / "orban-forest" / "evals"
    evals.mkdir(parents=True)
    (evals / "webcopy.md").write_text((FIXTURES / "rubric_valid.md").read_text())
    return tmp_path


def _run_cli(memory_root: Path, copy_path: Path):
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / "tools" / "eval.py"),
         "--client", "orban-forest", "--workflow", "webcopy",
         "--copy", str(copy_path), "--memory-root", str(memory_root)],
        capture_output=True, text=True,
    )


def test_cli_emits_json_and_exits_zero_on_passing_copy(memory_root, tmp_path):
    copy_path = tmp_path / "copy.md"
    copy_path.write_text("We climb trees. We cut branches.\n")
    proc = _run_cli(memory_root, copy_path)
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["invariant_failed"] is False


def test_cli_exits_zero_when_copy_fails_a_criterion(memory_root, tmp_path):
    """A failing evaluation is a successful run of the tool."""
    copy_path = tmp_path / "copy.md"
    copy_path.write_text("We leverage synergy.\n")
    proc = _run_cli(memory_root, copy_path)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["invariant_failed"] is False


def test_cli_exits_two_on_missing_rubric(tmp_path):
    copy_path = tmp_path / "copy.md"
    copy_path.write_text("x\n")
    proc = _run_cli(tmp_path, copy_path)
    assert proc.returncode == 2
    assert "rubric not found" in proc.stderr
    assert proc.stdout == ""


def test_cli_exits_two_on_missing_copy_file(memory_root, tmp_path):
    proc = _run_cli(memory_root, tmp_path / "absent.md")
    assert proc.returncode == 2
    assert "copy not found" in proc.stderr


def test_cli_exits_two_when_a_check_raises(tmp_path):
    """A structurally-invalid check config (e.g. a scalar band instead of a
    [min, max] pair) is a plausible YAML authoring typo. It must not escape
    as an uncaught exception (exit 1) -- the spine-failure contract is
    exit 2, stdout empty, reason on stderr.
    """
    evals = tmp_path / "clients" / "orban-forest" / "evals"
    evals.mkdir(parents=True)
    (evals / "webcopy.md").write_text(
        "# Web Copy Rubric\n\n"
        "## Invariant\n\n"
        "```yaml\n"
        "[]\n"
        "```\n\n"
        "## Tunable\n\n"
        "```yaml\n"
        "- id: bad-length-band\n"
        "  type: deterministic\n"
        "  check: length_bands\n"
        "  config:\n"
        "    h1: 5\n"
        "```\n"
    )
    copy_path = tmp_path / "copy.md"
    copy_path.write_text("<!-- section: h1 -->\nHello there.\n")
    proc = _run_cli(tmp_path, copy_path)
    assert proc.returncode == 2
    assert proc.stdout == ""
    assert proc.stderr.strip() != ""

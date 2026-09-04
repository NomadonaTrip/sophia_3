import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from interfaces.retrieval import SCOPES, GrepRetriever, Hit

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def memory_root(tmp_path: Path) -> Path:
    client = tmp_path / "clients" / "orban-forest"
    (client / "evals").mkdir(parents=True)
    (client / "episodic").mkdir(parents=True)
    (client / "voice.md").write_text(
        "# Voice\nShort sentences. Plain words.\nNever says 'leverage'.\n"
    )
    (client / "business.md").write_text("# Business\nTree surgery in Kent.\n")
    (client / "evals" / "webcopy.md").write_text("# Rubric\nleverage is banned\n")
    return tmp_path


def test_finds_match_across_client_memory(memory_root):
    hits = GrepRetriever(memory_root).search("leverage", client="orban-forest")
    assert len(hits) == 2
    assert {Path(h.path).name for h in hits} == {"voice.md", "webcopy.md"}
    assert all(isinstance(h, Hit) for h in hits)


def test_scope_narrows_to_one_area(memory_root):
    hits = GrepRetriever(memory_root).search(
        "leverage", client="orban-forest", scope="evals"
    )
    assert len(hits) == 1
    assert hits[0].scope == "evals"
    assert Path(hits[0].path).name == "webcopy.md"


def test_hit_carries_line_number_and_text(memory_root):
    hits = GrepRetriever(memory_root).search(
        "Tree surgery", client="orban-forest", scope="business"
    )
    assert hits[0].line == 2
    assert "Tree surgery in Kent." in hits[0].text


def test_no_match_returns_empty_list(memory_root):
    assert GrepRetriever(memory_root).search("nonexistent", client="orban-forest") == []


def test_missing_client_returns_empty_not_error(memory_root):
    """H-FR6: empty results are tolerated; absence is the caller's call to make."""
    assert GrepRetriever(memory_root).search("anything", client="no-such-client") == []


def test_empty_scope_directory_returns_empty(memory_root):
    assert (
        GrepRetriever(memory_root).search(
            "anything", client="orban-forest", scope="episodic"
        )
        == []
    )


def test_limit_caps_results(memory_root):
    hits = GrepRetriever(memory_root).search(
        "leverage", client="orban-forest", limit=1
    )
    assert len(hits) == 1
    # After sorting by (path, line), evals/webcopy.md comes before voice.md
    assert "evals" in hits[0].path or Path(hits[0].path).name == "webcopy.md"


@pytest.mark.skipif(os.geteuid() == 0, reason="chmod does not restrict root")
def test_unreadable_file_does_not_block_readable_matches(memory_root):
    """grep exit code 2 (unreadable file) should not discard valid matches."""
    # Create a scope directory with two files
    scope_dir = memory_root / "clients" / "orban-forest" / "performance"
    scope_dir.mkdir(parents=True, exist_ok=True)

    readable_file = scope_dir / "readable.md"
    unreadable_file = scope_dir / "unreadable.md"

    readable_file.write_text("# Readable\nThis file contains leverage\n")
    unreadable_file.write_text("# Unreadable\nShould not be readable\n")

    # Make unreadable_file inaccessible
    os.chmod(unreadable_file, 0o000)
    try:
        # Search should still find the match in the readable file
        hits = GrepRetriever(memory_root).search(
            "leverage", client="orban-forest", scope="performance"
        )
        assert len(hits) == 1
        assert Path(hits[0].path).name == "readable.md"
    finally:
        # Restore permissions so tmp_path can clean up
        os.chmod(unreadable_file, 0o644)


def test_unknown_scope_is_an_error(memory_root):
    with pytest.raises(ValueError, match="unknown scope"):
        GrepRetriever(memory_root).search("x", client="orban-forest", scope="bogus")


def test_regex_metacharacters_are_matched_literally(memory_root):
    """A query is a phrase, not a pattern; '.' must not match every character."""
    assert (
        GrepRetriever(memory_root).search("Plain.words", client="orban-forest") == []
    )


def test_scopes_tuple_matches_spec():
    assert SCOPES == ("voice", "business", "icp", "evals", "episodic", "performance")


def test_module_cli_emits_json(memory_root):
    proc = subprocess.run(
        [
            sys.executable, "-m", "interfaces.retrieval",
            "--memory-root", str(memory_root),
            "--client", "orban-forest",
            "--query", "leverage",
        ],
        capture_output=True, text=True, check=True, cwd=REPO_ROOT,
    )
    payload = json.loads(proc.stdout)
    assert len(payload) == 2
    assert set(payload[0]) == {"path", "line", "text", "scope"}

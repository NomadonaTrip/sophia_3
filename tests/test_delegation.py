import json
import subprocess
import sys
from pathlib import Path

import pytest

from interfaces.delegation import (
    REQUIRED_FRONTMATTER,
    REQUIRED_SECTIONS,
    DelegationError,
    load_workflows,
    parse_agent,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
AGENTS_DIR = REPO_ROOT / ".claude" / "agents"

GOOD_AGENT = """---
name: sample
description: A sample workflow.
tools: [Read, Write, Bash]
model: opus
modes: [generate, revise]
rubric_path: evals/sample.md
---

## Role

Do the sample thing.

## Memory to load

voice.md, business.md, icp.md

## Rubric

evals/sample.md

## Loop

Invoke the gen-eval-loop skill.

## Escalation

Escalate at the cap.
"""


def test_real_webcopy_agent_parses():
    spec = parse_agent(AGENTS_DIR / "webcopy.md")
    assert spec.name == "webcopy"
    assert spec.rubric_path == "evals/webcopy.md"
    assert "generate" in spec.modes and "revise" in spec.modes
    assert spec.tools


def test_template_declares_every_required_section():
    text = (AGENTS_DIR / "_TEMPLATE.md").read_text()
    for section in REQUIRED_SECTIONS:
        assert f"## {section}" in text, section


def test_load_workflows_skips_underscore_files():
    names = [s.name for s in load_workflows(AGENTS_DIR)]
    assert "webcopy" in names
    assert not any(n.startswith("_") for n in names)


def test_parse_agent_reads_frontmatter(tmp_path):
    path = tmp_path / "sample.md"
    path.write_text(GOOD_AGENT)
    spec = parse_agent(path)
    assert spec.description == "A sample workflow."
    assert spec.tools == ["Read", "Write", "Bash"]
    assert spec.agent_file == str(path)


def test_missing_frontmatter_is_an_error(tmp_path):
    path = tmp_path / "sample.md"
    path.write_text("## Role\n\nNo frontmatter here.\n")
    with pytest.raises(DelegationError, match="frontmatter"):
        parse_agent(path)


@pytest.mark.parametrize("field", REQUIRED_FRONTMATTER)
def test_each_required_frontmatter_field_is_enforced(tmp_path, field):
    lines = [ln for ln in GOOD_AGENT.splitlines() if not ln.startswith(f"{field}:")]
    path = tmp_path / "sample.md"
    path.write_text("\n".join(lines))
    with pytest.raises(DelegationError, match=field):
        parse_agent(path)


@pytest.mark.parametrize("section", REQUIRED_SECTIONS)
def test_each_required_section_is_enforced(tmp_path, section):
    path = tmp_path / "sample.md"
    path.write_text(GOOD_AGENT.replace(f"## {section}", "## Something Else"))
    with pytest.raises(DelegationError, match=section):
        parse_agent(path)


def test_tools_must_be_a_list(tmp_path):
    path = tmp_path / "sample.md"
    path.write_text(GOOD_AGENT.replace("tools: [Read, Write, Bash]", "tools: Read"))
    with pytest.raises(DelegationError, match="tools"):
        parse_agent(path)


def test_name_with_dash_is_rejected(tmp_path):
    path = tmp_path / "sample.md"
    path.write_text(GOOD_AGENT.replace("name: sample", "name: web-copy"))
    with pytest.raises(DelegationError, match="name"):
        parse_agent(path)


def test_ordinary_name_parses(tmp_path):
    path = tmp_path / "sample.md"
    path.write_text(GOOD_AGENT.replace("name: sample", "name: webcopy"))
    spec = parse_agent(path)
    assert spec.name == "webcopy"


def test_cli_validate_emits_specs_and_exits_zero():
    proc = subprocess.run(
        [sys.executable, "-m", "interfaces.delegation", "--validate",
         "--agents-dir", str(AGENTS_DIR)],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    assert proc.returncode == 0, proc.stderr
    assert "webcopy" in {s["name"] for s in json.loads(proc.stdout)}


def test_cli_validate_exits_two_on_a_malformed_agent(tmp_path):
    (tmp_path / "broken.md").write_text("no frontmatter\n")
    proc = subprocess.run(
        [sys.executable, "-m", "interfaces.delegation", "--validate",
         "--agents-dir", str(tmp_path)],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    assert proc.returncode == 2
    assert "frontmatter" in proc.stderr


def test_cli_validate_exits_two_on_a_missing_agents_dir(tmp_path):
    missing = tmp_path / "does-not-exist"
    proc = subprocess.run(
        [sys.executable, "-m", "interfaces.delegation", "--validate",
         "--agents-dir", str(missing)],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    assert proc.returncode == 2
    assert proc.stdout == ""
    assert str(missing) in proc.stderr


def test_well_formed_role_heading_passes(tmp_path):
    path = tmp_path / "sample.md"
    path.write_text(GOOD_AGENT)
    spec = parse_agent(path)
    assert spec.name == "sample"


@pytest.mark.parametrize(
    "heading",
    ["### Role", "## Roles", "## Role and scope"],
    ids=["deeper-heading", "trailing-word", "extra-words"],
)
def test_naive_role_lookalikes_do_not_satisfy_the_section(tmp_path, heading):
    path = tmp_path / "sample.md"
    path.write_text(GOOD_AGENT.replace("## Role\n", f"{heading}\n"))
    with pytest.raises(DelegationError, match="Role"):
        parse_agent(path)


def test_role_heading_inside_a_fenced_code_block_does_not_count(tmp_path):
    path = tmp_path / "sample.md"
    text = GOOD_AGENT.replace(
        "## Role\n\nDo the sample thing.\n\n",
        "```\n## Role\n```\n\n",
    )
    path.write_text(text)
    with pytest.raises(DelegationError, match="Role"):
        parse_agent(path)

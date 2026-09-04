from pathlib import Path

import pytest

from tools.rubric import Rubric, RubricError, load_rubric

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def rubric() -> Rubric:
    return load_rubric(FIXTURES / "rubric_valid.md")


def test_loads_all_criteria(rubric):
    assert [c.id for c in rubric.criteria] == [
        "campfire-voice", "no-fabricated-stats", "banned-phrases", "hook-strength",
    ]


def test_invariance_derives_from_section_not_a_field(rubric):
    by_id = {c.id: c for c in rubric.criteria}
    assert by_id["campfire-voice"].invariant is True
    assert by_id["no-fabricated-stats"].invariant is True
    assert by_id["banned-phrases"].invariant is False
    assert by_id["hook-strength"].invariant is False


def test_config_is_parsed(rubric):
    by_id = {c.id: c for c in rubric.criteria}
    assert by_id["banned-phrases"].config == {"phrases": ["leverage", "unlock"]}


def test_config_defaults_to_empty_dict(rubric):
    by_id = {c.id: c for c in rubric.criteria}
    assert by_id["no-fabricated-stats"].config == {}


def test_partitions_by_type(rubric):
    assert [c.id for c in rubric.deterministic()] == [
        "no-fabricated-stats", "banned-phrases",
    ]
    assert [c.id for c in rubric.judgment()] == ["campfire-voice", "hook-strength"]


def test_an_invariant_yaml_field_cannot_override_the_section(tmp_path):
    """Invariance is structural. A criterion that claims otherwise is rejected."""
    path = tmp_path / "r.md"
    path.write_text(
        "## Invariant\n\n```yaml\n- id: a\n  type: judgment\n  invariant: false\n"
        "  criterion: x\n```\n\n## Tunable\n\n```yaml\n[]\n```\n"
    )
    with pytest.raises(RubricError, match="invariant"):
        load_rubric(path)


def test_missing_invariant_section_is_an_error(tmp_path):
    path = tmp_path / "r.md"
    path.write_text("## Tunable\n\n```yaml\n[]\n```\n")
    with pytest.raises(RubricError, match="Invariant"):
        load_rubric(path)


def test_missing_tunable_section_is_an_error(tmp_path):
    path = tmp_path / "r.md"
    path.write_text("## Invariant\n\n```yaml\n[]\n```\n")
    with pytest.raises(RubricError, match="Tunable"):
        load_rubric(path)


def test_deterministic_criterion_without_check_is_an_error(tmp_path):
    path = tmp_path / "r.md"
    path.write_text(
        "## Invariant\n\n```yaml\n- id: a\n  type: deterministic\n```\n\n"
        "## Tunable\n\n```yaml\n[]\n```\n"
    )
    with pytest.raises(RubricError, match="check"):
        load_rubric(path)


def test_unknown_type_is_an_error(tmp_path):
    path = tmp_path / "r.md"
    path.write_text(
        "## Invariant\n\n```yaml\n- id: a\n  type: vibes\n```\n\n"
        "## Tunable\n\n```yaml\n[]\n```\n"
    )
    with pytest.raises(RubricError, match="type"):
        load_rubric(path)


def test_duplicate_ids_are_an_error(tmp_path):
    path = tmp_path / "r.md"
    path.write_text(
        "## Invariant\n\n```yaml\n- id: a\n  type: judgment\n  criterion: x\n```\n\n"
        "## Tunable\n\n```yaml\n- id: a\n  type: judgment\n  criterion: y\n```\n"
    )
    with pytest.raises(RubricError, match="duplicate"):
        load_rubric(path)


def test_missing_file_is_an_error(tmp_path):
    with pytest.raises(RubricError, match="not found"):
        load_rubric(tmp_path / "nope.md")


def test_malformed_yaml_is_an_error(tmp_path):
    path = tmp_path / "r.md"
    path.write_text(
        "## Invariant\n\n```yaml\n- id: [unclosed\n```\n\n"
        "## Tunable\n\n```yaml\n[]\n```\n"
    )
    with pytest.raises(RubricError, match="YAML"):
        load_rubric(path)


def test_empty_invariant_followed_by_populated_tunable(tmp_path):
    """Section extraction must not leak: empty Invariant followed by real Tunable."""
    path = tmp_path / "r.md"
    path.write_text(
        "## Invariant\n\n```yaml\n[]\n```\n\n"
        "## Tunable\n\n```yaml\n- id: a\n  type: judgment\n  criterion: x\n```\n"
    )
    rubric = load_rubric(path)
    assert len(rubric.criteria) == 1
    assert rubric.criteria[0].id == "a"
    assert rubric.criteria[0].invariant is False
    assert len(rubric.deterministic()) == 0
    assert len(rubric.judgment()) == 1


def test_multiple_yaml_blocks_in_section_is_an_error(tmp_path):
    """A section with multiple YAML fences is ambiguous and rejected."""
    path = tmp_path / "r.md"
    path.write_text(
        "## Invariant\n\n```yaml\n- id: wrong\n  type: judgment\n  criterion: x\n```\n\n"
        "```yaml\n- id: correct\n  type: judgment\n  criterion: y\n```\n\n"
        "## Tunable\n\n```yaml\n[]\n```\n"
    )
    with pytest.raises(RubricError, match="fenced yaml block"):
        load_rubric(path)


def test_section_heading_inside_yaml_content_does_not_truncate(tmp_path):
    """A ## inside YAML content (not at line start) should not truncate the section."""
    path = tmp_path / "r.md"
    path.write_text(
        "## Invariant\n\n```yaml\n- id: a\n  type: judgment\n  criterion: 'This mentions ## headers in prose'\n```\n\n"
        "## Tunable\n\n```yaml\n[]\n```\n"
    )
    rubric = load_rubric(path)
    assert len(rubric.criteria) == 1
    assert rubric.criteria[0].id == "a"
    assert rubric.criteria[0].invariant is True
    assert "##" in rubric.criteria[0].criterion


def test_yaml_comment_at_line_start_does_not_truncate_section(tmp_path):
    """A ## comment at column 0 inside a YAML fence should not truncate the section."""
    path = tmp_path / "r.md"
    path.write_text(
        "## Invariant\n\n```yaml\n## these are the criteria we never tune away\n"
        "- id: campfire-voice\n  type: judgment\n  criterion: x\n```\n\n"
        "## Tunable\n\n```yaml\n[]\n```\n"
    )
    rubric = load_rubric(path)
    assert len(rubric.criteria) == 1
    assert rubric.criteria[0].id == "campfire-voice"
    assert rubric.criteria[0].invariant is True


def test_yaml_comment_at_line_start_in_last_section(tmp_path):
    """A ## comment at column 0 in the last section's YAML fence should not truncate."""
    path = tmp_path / "r.md"
    path.write_text(
        "## Invariant\n\n```yaml\n[]\n```\n\n"
        "## Tunable\n\n```yaml\n## these are tunable criteria\n"
        "- id: hook-strength\n  type: judgment\n  criterion: earns the second line\n```\n"
    )
    rubric = load_rubric(path)
    assert len(rubric.criteria) == 1
    assert rubric.criteria[0].id == "hook-strength"
    assert rubric.criteria[0].invariant is False


def test_four_backtick_fence_with_nested_three_backtick_line(tmp_path):
    """A four-backtick fence containing a three-backtick line inside should parse correctly."""
    path = tmp_path / "r.md"
    path.write_text(
        "## Invariant\n\n````yaml\n"
        "- id: code-example\n"
        "  type: judgment\n"
        "  criterion: |\n"
        "    Code block contains:\n"
        "    ```\n"
        "    some code here\n"
        "    ```\n"
        "````\n\n"
        "## Tunable\n\n```yaml\n[]\n```\n"
    )
    rubric = load_rubric(path)
    assert len(rubric.criteria) == 1
    assert rubric.criteria[0].id == "code-example"
    assert rubric.criteria[0].invariant is True
    assert "```" in rubric.criteria[0].criterion


def test_three_backtick_fence_closes_on_three_backticks(tmp_path):
    """Normal three-backtick fences should close on matching three-backtick lines."""
    path = tmp_path / "r.md"
    path.write_text(
        "## Invariant\n\n```yaml\n- id: normal-case\n  type: judgment\n  criterion: x\n```\n\n"
        "## Tunable\n\n```yaml\n[]\n```\n"
    )
    rubric = load_rubric(path)
    assert len(rubric.criteria) == 1
    assert rubric.criteria[0].id == "normal-case"
    assert rubric.criteria[0].invariant is True

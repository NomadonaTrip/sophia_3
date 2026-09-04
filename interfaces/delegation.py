"""Coordinator seam.

Not a router -- the coordinator is the main Claude session plus a routing doc.
This is the enumeration a router would consume, and it earns its place today by
validating agent files against the template before a run discovers the problem.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import yaml

REQUIRED_FRONTMATTER = ("name", "description", "tools", "model")
REQUIRED_SECTIONS = ("Role", "Memory to load", "Rubric", "Loop", "Escalation")

DEFAULT_AGENTS_DIR = Path(__file__).resolve().parent.parent / ".claude" / "agents"

_FRONTMATTER_RE = re.compile(r"\A---\s*$(?P<body>.*?)^---\s*$", re.MULTILINE | re.DOTALL)

# Workflow names are embedded in run ids as `{timestamp}-{workflow}-{slug}` and
# split on '-' with maxsplit=2 (tools/episodic.py); a dash in the name would
# break that split, so names must be a dash-free lowercase identifier.
_NAME_RE = re.compile(r"\A[a-z][a-z0-9_]*\Z")


class DelegationError(Exception):
    """An agent file does not honour the convention. Never silently accepted."""


@dataclass(frozen=True)
class WorkflowSpec:
    name: str
    description: str
    agent_file: str
    rubric_path: str
    modes: list[str]
    tools: list[str]


def parse_agent(path: Path) -> WorkflowSpec:
    path = Path(path)
    if not path.is_file():
        raise DelegationError(f"agent file not found: {path}")
    text = path.read_text()

    match = _FRONTMATTER_RE.search(text)
    if match is None:
        raise DelegationError(f"{path}: missing YAML frontmatter")
    try:
        front = yaml.safe_load(match.group("body")) or {}
    except yaml.YAMLError as exc:
        raise DelegationError(f"{path}: malformed frontmatter YAML: {exc}") from exc

    missing = [f for f in REQUIRED_FRONTMATTER if not front.get(f)]
    if missing:
        raise DelegationError(
            f"{path}: frontmatter missing required fields: {', '.join(missing)}"
        )
    if not isinstance(front["tools"], list):
        raise DelegationError(f"{path}: 'tools' must be a YAML list")

    name = front["name"]
    if not isinstance(name, str) or not _NAME_RE.match(name):
        raise DelegationError(
            f"{path}: 'name' must be a lowercase alphanumeric identifier with no "
            f"dashes (matching [a-z][a-z0-9_]*), got: {name!r}"
        )

    body = text[match.end():]
    absent = [s for s in REQUIRED_SECTIONS if f"## {s}" not in body]
    if absent:
        raise DelegationError(
            f"{path}: missing required sections: {', '.join(absent)}"
        )

    return WorkflowSpec(
        name=name,
        description=front["description"],
        agent_file=str(path),
        rubric_path=front.get("rubric_path", f"evals/{name}.md"),
        modes=list(front.get("modes") or ["generate"]),
        tools=list(front["tools"]),
    )


def load_workflows(agents_dir: Path = DEFAULT_AGENTS_DIR) -> list[WorkflowSpec]:
    directory = Path(agents_dir)
    if not directory.is_dir():
        return []
    return [
        parse_agent(p)
        for p in sorted(directory.glob("*.md"))
        if not p.name.startswith("_")
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Enumerate and validate workflows.")
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--agents-dir", type=Path, default=DEFAULT_AGENTS_DIR)
    args = parser.parse_args(argv)

    try:
        specs = load_workflows(args.agents_dir)
    except DelegationError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(json.dumps([asdict(s) for s in specs], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

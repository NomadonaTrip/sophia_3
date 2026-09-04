"""Retrieval seam. V1 backing is grep over markdown memory.

Per H-FR6 every caller must tolerate empty results, so absence of a client
directory or a scope directory is an empty list, never an exception. Deciding
whether absence is fatal belongs to the caller -- the research-first gate
treats it as fatal; a background lookup does not.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

SCOPES: tuple[str, ...] = (
    "voice", "business", "icp", "evals", "episodic", "performance",
)

# Scopes that name a single file rather than a directory.
_FILE_SCOPES = {"voice": "voice.md", "business": "business.md", "icp": "icp.md"}

DEFAULT_MEMORY_ROOT = Path(__file__).resolve().parent.parent / "memory"


@dataclass(frozen=True)
class Hit:
    path: str
    line: int
    text: str
    scope: str


class Retriever(Protocol):
    def search(
        self, query: str, *, client: str,
        scope: str | None = None, limit: int = 20,
    ) -> list[Hit]: ...


class GrepRetriever:
    """Grep over ``memory/clients/<client>/`` with optional scope narrowing."""

    def __init__(self, memory_root: Path = DEFAULT_MEMORY_ROOT) -> None:
        self.memory_root = Path(memory_root)

    def search(
        self, query: str, *, client: str,
        scope: str | None = None, limit: int = 20,
    ) -> list[Hit]:
        if scope is not None and scope not in SCOPES:
            raise ValueError(f"unknown scope: {scope!r}; expected one of {SCOPES}")

        target = self._target(client, scope)
        if target is None or not target.exists():
            return []

        # -F: fixed string, so a query is a phrase and not a regex.
        # -r: recurse (harmless on a file target). -n: line numbers.
        proc = subprocess.run(
            ["grep", "-rFn", "--", query, str(target)],
            capture_output=True, text=True,
        )
        if proc.returncode not in (0, 1):  # 1 == no match, which is not an error
            return []

        hits: list[Hit] = []
        client_root = self.memory_root / "clients" / client
        for raw in proc.stdout.splitlines():
            parsed = self._parse_grep_line(raw, target)
            if parsed is None:
                continue
            path, line, text = parsed
            hits.append(
                Hit(
                    path=path, line=line, text=text,
                    scope=scope or self._infer_scope(Path(path), client_root),
                )
            )
            if len(hits) >= limit:
                break
        return hits

    def _target(self, client: str, scope: str | None) -> Path | None:
        client_root = self.memory_root / "clients" / client
        if scope is None:
            return client_root
        if scope in _FILE_SCOPES:
            return client_root / _FILE_SCOPES[scope]
        return client_root / scope

    @staticmethod
    def _parse_grep_line(raw: str, target: Path) -> tuple[str, int, str] | None:
        """grep prints ``path:line:text`` for directories, ``line:text`` for files."""
        if target.is_file():
            line_str, _, text = raw.partition(":")
            if not line_str.isdigit():
                return None
            return str(target), int(line_str), text
        path, _, rest = raw.partition(":")
        line_str, _, text = rest.partition(":")
        if not line_str.isdigit():
            return None
        return path, int(line_str), text

    @staticmethod
    def _infer_scope(path: Path, client_root: Path) -> str:
        try:
            rel = path.resolve().relative_to(client_root.resolve())
        except ValueError:
            return "unknown"
        head = rel.parts[0]
        for scope, filename in _FILE_SCOPES.items():
            if head == filename:
                return scope
        return head if head in SCOPES else "unknown"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Search client memory.")
    parser.add_argument("--client", required=True)
    parser.add_argument("--query", required=True)
    parser.add_argument("--scope", choices=SCOPES, default=None)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--memory-root", type=Path, default=DEFAULT_MEMORY_ROOT)
    args = parser.parse_args(argv)

    hits = GrepRetriever(args.memory_root).search(
        args.query, client=args.client, scope=args.scope, limit=args.limit
    )
    print(json.dumps([asdict(h) for h in hits], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

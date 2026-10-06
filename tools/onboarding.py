#!/usr/bin/env python3
"""Resumable onboarding state.

Two layers under memory/clients/<client>/onboarding/:

- session.jsonl  -- every interview message, appended as it happens. Scratch:
  git-ignored, and discarded per section once the operator agrees.
- decisions.json -- what each section settled on. Durable: /onboard writes the
  profile from it.

Messages are only discardable once their section's decision is saved, so the
raw interview can never be lost before what it decided is on disk. Judgment
stays in the session; this tool only persists.

Exit codes: 0 = done, JSON on stdout; 2 = failure, stdout empty and the reason
on stderr.
"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

SECTIONS = (
    "seed", "business", "customer", "constraints", "voice", "rubric", "written",
)
ROLES = ("operator", "sophia")
PROFILE_FILES = ("business.md", "icp.md", "voice.md", "evals/webcopy.md")

_CLIENT = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_TS_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

DEFAULT_MEMORY_ROOT = Path(__file__).resolve().parent.parent / "memory"


class OnboardingError(Exception):
    """The request could not be carried out. Nothing is written."""


# --- paths and io ---

def _client_dir(memory_root: Path, client: str) -> Path:
    if not _CLIENT.match(client):
        raise OnboardingError(f"invalid client name: {client!r}")
    return Path(memory_root) / "clients" / client


def _state_dir(memory_root: Path, client: str) -> Path:
    return _client_dir(memory_root, client) / "onboarding"


def _check_section(section: str) -> None:
    if section not in SECTIONS:
        raise OnboardingError(
            f"unknown section {section!r}; expected one of {SECTIONS}"
        )


def _now(now: datetime | None) -> str:
    return (now or datetime.now(timezone.utc)).strftime(_TS_FORMAT)


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, path)


def _read_messages(memory_root: Path, client: str) -> list[dict]:
    path = _state_dir(memory_root, client) / "session.jsonl"
    if not path.is_file():
        return []
    messages = []
    for number, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            messages.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise OnboardingError(
                f"session log is corrupt at line {number}: {exc}"
            ) from exc
    return messages


def _write_messages(memory_root: Path, client: str, messages: list[dict]) -> None:
    path = _state_dir(memory_root, client) / "session.jsonl"
    if not messages:
        path.unlink(missing_ok=True)
        return
    _atomic_write(path, "".join(json.dumps(m) + "\n" for m in messages))


def _read_decisions(memory_root: Path, client: str) -> dict:
    path = _state_dir(memory_root, client) / "decisions.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise OnboardingError(f"decisions file is corrupt: {exc}") from exc


def _write_decisions(memory_root: Path, client: str, decisions: dict) -> None:
    path = _state_dir(memory_root, client) / "decisions.json"
    if not decisions:
        path.unlink(missing_ok=True)
        return
    _atomic_write(path, json.dumps(decisions, indent=2) + "\n")


# --- operations ---

def log_message(
    memory_root: Path, client: str, section: str, role: str, text: str,
    *, now: datetime | None = None,
) -> dict:
    _check_section(section)
    if role not in ROLES:
        raise OnboardingError(f"role must be one of {ROLES}, got {role!r}")
    if not text or not text.strip():
        raise OnboardingError("message text is empty")

    entry = {"section": section, "role": role, "text": text, "at": _now(now)}
    path = _state_dir(memory_root, client) / "session.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        handle.write(json.dumps(entry) + "\n")
    return entry


def save_decision(
    memory_root: Path, client: str, section: str, decision,
    *, now: datetime | None = None,
) -> dict:
    _check_section(section)
    if decision is None or (
        isinstance(decision, (dict, list, str)) and not decision
    ):
        raise OnboardingError("decision is empty")

    decisions = _read_decisions(memory_root, client)
    record = {
        "decision": decision,
        "saved_at": _now(now),
        "messages": "pending",
        "recheck": False,
    }
    decisions[section] = record
    _write_decisions(memory_root, client, decisions)
    return record


def _settled_record(memory_root: Path, client: str, section: str) -> dict:
    _check_section(section)
    decisions = _read_decisions(memory_root, client)
    if section not in decisions:
        raise OnboardingError(
            f"section {section!r} is not settled; save its decision first"
        )
    return decisions


def discard_messages(memory_root: Path, client: str, section: str) -> int:
    decisions = _settled_record(memory_root, client, section)
    messages = _read_messages(memory_root, client)
    remaining = [m for m in messages if m.get("section") != section]
    _write_messages(memory_root, client, remaining)
    decisions[section]["messages"] = "discarded"
    _write_decisions(memory_root, client, decisions)
    return len(messages) - len(remaining)


def keep_messages(memory_root: Path, client: str, section: str) -> dict:
    decisions = _settled_record(memory_root, client, section)
    decisions[section]["messages"] = "kept"
    _write_decisions(memory_root, client, decisions)
    return decisions[section]


def reset(memory_root: Path, client: str, section: str | None = None) -> dict:
    """Clear onboarding state. Never touches the profile files or the samples."""
    if section is None:
        messages = _read_messages(memory_root, client)
        decisions = _read_decisions(memory_root, client)
        _write_messages(memory_root, client, [])
        _write_decisions(memory_root, client, {})
        return {
            "scope": "all",
            "messages_removed": len(messages),
            "decisions_removed": sorted(decisions, key=SECTIONS.index),
            "recheck": [],
        }

    _check_section(section)
    messages = _read_messages(memory_root, client)
    remaining = [m for m in messages if m.get("section") != section]
    decisions = _read_decisions(memory_root, client)
    removed = decisions.pop(section, None)

    later = SECTIONS[SECTIONS.index(section) + 1:]
    flagged = [s for s in later if s in decisions]
    for s in flagged:
        decisions[s]["recheck"] = True

    _write_messages(memory_root, client, remaining)
    _write_decisions(memory_root, client, decisions)
    return {
        "scope": section,
        "messages_removed": len(messages) - len(remaining),
        "decisions_removed": [section] if removed else [],
        "recheck": flagged,
    }


def status(memory_root: Path, client: str) -> dict:
    client_dir = _client_dir(memory_root, client)
    messages = _read_messages(memory_root, client)
    decisions = _read_decisions(memory_root, client)

    settled = [s for s in SECTIONS if s in decisions]
    recheck = [s for s in settled if decisions[s].get("recheck")]
    next_section = next(
        (s for s in SECTIONS if s not in decisions or decisions[s].get("recheck")),
        None,
    )

    in_progress: dict[str, list[dict]] = {}
    logged_sections: set[str] = set()
    for m in messages:
        logged_sections.add(m.get("section"))
        if m.get("section") not in decisions:
            in_progress.setdefault(m["section"], []).append(m)

    discard_pending = [
        s for s in settled
        if s in logged_sections and decisions[s].get("messages") != "kept"
    ]

    return {
        "client": client,
        "next": next_section,
        "settled": settled,
        "recheck": recheck,
        "discard_pending": discard_pending,
        "in_progress": in_progress,
        "decisions": decisions,
        "profile_files": {
            name: (client_dir / name).is_file() for name in PROFILE_FILES
        },
    }


# --- CLI ---

def _read_arg(value: str) -> str:
    return sys.stdin.read() if value == "-" else value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Resumable onboarding state.")
    sub = parser.add_subparsers(dest="command", required=True)

    def add(name: str, help_text: str, *, section: str | None = None):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--client", required=True)
        p.add_argument("--memory-root", type=Path, default=DEFAULT_MEMORY_ROOT)
        if section == "required":
            p.add_argument("--section", required=True)
        elif section == "optional":
            p.add_argument("--section", default=None)
        return p

    add("status", "Where onboarding stands for this client.")
    log = add("log", "Append one interview message.", section="required")
    log.add_argument("--role", required=True)
    log.add_argument("--text", required=True, help="the message, or - for stdin")
    save = add("save", "Record a settled section.", section="required")
    save.add_argument("--payload", required=True, help="path to JSON, or - for stdin")
    add("discard", "Delete a settled section's messages.", section="required")
    add("keep", "Keep a settled section's messages; stop asking.", section="required")
    add("reset", "Clear all progress, or one section's.", section="optional")

    args = parser.parse_args(argv)
    root, client = args.memory_root, args.client

    try:
        if args.command == "status":
            result = status(root, client)
        elif args.command == "log":
            result = log_message(root, client, args.section, args.role,
                                 _read_arg(args.text))
        elif args.command == "save":
            raw = (sys.stdin.read() if args.payload == "-"
                   else Path(args.payload).read_text())
            result = save_decision(root, client, args.section, json.loads(raw))
        elif args.command == "discard":
            result = {"section": args.section,
                      "removed": discard_messages(root, client, args.section)}
        elif args.command == "keep":
            result = keep_messages(root, client, args.section)
        else:
            result = reset(root, client, args.section)
    except (OnboardingError, json.JSONDecodeError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"onboarding failed: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

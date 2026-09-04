---
description: Switch the active client and load their full profile.
argument-hint: <client-name>
---

# Switch to $1

Load and summarise the client's profile so the rest of the session has it:

```bash
python3 -m interfaces.retrieval --client $1 --query "" --scope voice
python3 -m interfaces.retrieval --client $1 --query "" --scope business
python3 -m interfaces.retrieval --client $1 --query "" --scope icp
```

Read `memory/clients/$1/voice.md`, `business.md`, `icp.md`, and
`evals/webcopy.md` directly — retrieval is for searching, not for loading a
whole profile.

Report:

- What this client does, and who they sell to
- The voice in three or four markers, not adjectives
- What the rubric holds invariant
- The last few runs in `episodic/`, and how they were decided

**If the client directory does not exist, say so and offer `/onboard $1`.**
Do not infer a profile from the client's name.

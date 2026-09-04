# Web Copy Rubric — orban-forest

## Invariant

```yaml
- id: campfire-voice
  type: judgment
  criterion: >
    Reads as one person talking to another by a fire.
- id: no-fabricated-stats
  type: deterministic
  check: fabricated_stat_scan
```

## Tunable

```yaml
- id: banned-phrases
  type: deterministic
  check: banned_phrases
  config:
    phrases: ["leverage", "unlock"]
- id: hook-strength
  type: judgment
  criterion: The first line earns the second.
```

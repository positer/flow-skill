# Session: gen command — prompt→workflow generation

## What
Added `flow gen <description>` that generates `.Flow.json` workflows from natural language descriptions.

## Key changes
- **flow.py**: Added `cmd_gen()` (160 lines) + helper functions:
  - `_gen_name_from_text()` — kebab-case name from first meaningful words
  - `_gen_split_steps()` — split by "then", ". ", etc.
  - `_gen_is_condition()` — heuristic detection (action verbs first, ? ending, keywords)
  - `_gen_assign_mode()` — Plan/Build/Goal by position
  - Goto logic: conditions point to implementation step (false) or skip past it (true)
  - Default dir changed: auto-detect skill dir (alongside SKILL.md) vs local `Flow/`
- **CLI**: `flow gen <text>`, `--name/-n`, `--force/-f` flags
- **Docs**: README.md, SKILL.md, Flow/Flow.md updated with gen command
- **SKILL.md**: Added gen to triggers, removed duplicate File Structure section
- **Housekeeping**: Removed test-generated artifacts from repo

## Files changed
- `flow.py`: +gen logic, default dir detection
- `README.md`: CLI table + gen row
- `SKILL.md`: CLI table + triggers + dedup
- `Flow/Flow.md`: CLI table + gen rows
- `archive/2026-06-21-gen-command.md`: this file

## Verification
```bash
flow gen "read project structure then check if readme exists then create readme"
flow check  # all workflows valid
```

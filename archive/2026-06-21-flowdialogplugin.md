# Session: FlowDialogPlugin — Step-based Dialog Bridge

Date: 2026-06-21

## Problem

`run_workflow()` was a blocking CLI function that printed prompts to stdout and
read from stdin. In an agent context (OpenCode/Claude Code), dialog component
prompts need to be **injected into the agent's actual conversation turns** — not
just printed. The agent framework needs to receive each step one at a time and
feed responses back.

## Solution: Goal-Plugin Pattern Applied

Studied `OpenCode_goal_plugin` architecture:
1. `_detect_native_goal()` — check env vars + import capability
2. `ensure_goal_capability()` — returns tool dict or None
3. `GoalManager` — fallback implementation with same interface

Applied same pattern to flow dialog execution:

### 1. `run_workflow_iter()` generator in `flow.py`

New function alongside `run_workflow()` — identical logic but uses Python's
`yield`/`send()` coroutine protocol instead of blocking I/O:

- **Dialog step**: yields `{"type": "dialog", "id", "mode", "prompt"}` →
  caller sends `{"type": "dialog_response", "response": str}`
- **Logic step**: yields `{"type": "logic", "id", "prompt", "goto_true", "goto_false"}` →
  caller sends `{"type": "logic_response", "condition": bool}`
- Handles cycle detection, goto, and completion exactly like `run_workflow()`

### 2. `FlowDialogPlugin/` package

| File | Purpose |
|------|---------|
| `__init__.py` | Package init, re-exports, convenience API (`list_workflows`, `find_workflow`, `auto_trigger`) |
| `dialog_plugin.py` | `FlowDialogBridge` class + `ensure_flow_capability()` |
| `README.md` | Documentation |

`FlowDialogBridge` wraps the generator into a stateful object:
- `start()` → auto-skips cycle_warnings, returns first actionable step
- `submit_response(str)` → advances dialog step
- `submit_condition(bool)` → advances logic step
- `is_complete()` / `error()` / `cycle_warnings()`

### 3. Auto-Detection

```python
ensure_flow_capability()
```
- Checks `OPENCODE_NATIVE_FLOW=1` env var or `opencode.run_flow` tool
- If absent: returns `{"list_workflows", "find_workflow", "auto_trigger",
  "describe_workflow", "create_bridge"}`
- If present: returns `None` (no-op)

## Test Results

| Test | Result |
|------|--------|
| `run_workflow_iter` (all TRUE) | Executes 6 components, completes ✅ |
| `run_workflow_iter` (all FALSE → cycle) | Cycle detected at visit 11 ✅ |
| `FlowDialogBridge` end-to-end | 5 steps (Plan→Logic→Build→Logic→Goal→complete) ✅ |
| `ensure_flow_capability()` | Returns tool dict with 5 keys ✅ |
| Plugin convenience API | `list_workflows`, `find_workflow`, `auto_trigger` all work ✅ |

## Files Created/Modified

- Modified: `flow.py` (added `run_workflow_iter` generator, 857→965 lines)
- Created: `FlowDialogPlugin/__init__.py`
- Created: `FlowDialogPlugin/dialog_plugin.py`
- Created: `FlowDialogPlugin/README.md`
- Modified: `SKILL.md` (added FlowDialogPlugin section)
- Modified: `README.md` (added FlowDialogPlugin to structure + architecture)

# Flow Workflow System

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A lightweight multi-agent workflow system. Create, validate, and execute sequential workflows using **dialog** (Plan/Build/Goal) and **logic** (conditional branching) components — all stored as plain `*.Flow.json` files.

## Why Flow?

| Problem | Flow Solution |
|---------|---------------|
| Agents get lost in complex tasks | Break down into sequential steps with explicit goto branching |
| No easy way to reuse workflows | `*.Flow.json` files — version-controlled, shareable, reviewable |
| Agent lacks native workflow support | `FlowDialogPlugin` auto-injects step-by-step execution bridge |
| Conditional logic mid-task | `logic` components evaluate state → jump to next appropriate step |
| Cycle hazards | Static pre-flight analysis + runtime guard (10 visits max) |

## Quick Start

```bash
python flow.py              # Dashboard — init, check all
python flow.py list         # List all workflows
python flow.py run <name>   # Execute workflow (fuzzy name match)
python flow.py serve        # Launch HTML tree editor
```

## Project Structure

```
Flow/
├── Flow.md                     # Format specification
├── add_list_sum.Flow.json      # Sample: 8-component workflow
├── feature-dev.Flow.json       # Sample: 5-component feature dev
└── flow-test.Flow.json         # 7-component test (all types + jumps)

flow.py                         # CLI engine + workflow runner
FlowEditor.html                 # Visual tree editor (standalone HTML)
FlowDialogPlugin/               # Dialog bridge for agents without native flow
OpenCode_goal_plugin/           # Goal fallback for agents without native goal
SKILL.md                        # OpenCode skill definition
```

## Architecture

| Layer | Component | Responsibility |
|-------|-----------|----------------|
| **Format** | `*.Flow.json` | JSON-based workflow definition |
| **Engine** | `flow.py` | CLI, validation, execution, auto-trigger |
| **Dialog** | `FlowDialogPlugin` | Step-based bridge — wraps generator into start/step/response API |
| **Goal** | `OpenCode_goal_plugin` | JSON-backed goal tracking for Goal-mode components |
| **Editor** | `FlowEditor.html` | Visual workflow editor (click-to-edit tree) |
| **Skill** | `SKILL.md` | OpenCode skill definition |

### Plugin Architecture

Both plugins auto-activate when the host agent lacks native support:

| Plugin | Activation Condition | Provides |
|--------|---------------------|----------|
| `OpenCode_goal_plugin` | No `get_goal`/`update_goal` tools | `GoalManager` |
| `FlowDialogPlugin` | No `opencode.run_flow` tool | `FlowDialogBridge` |

Goal-mode dialog components call `set_goal()` / `update_goal()` through the goal plugin at runtime.

## Workflow Components

### Dialog (`type: "dialog"`)

Modes: **Plan** (create plan), **Build** (execute task), **Goal** (set objective).

```json
{"type": "dialog", "id": 0, "mode": "Plan", "prompt": "Plan: {#prompt#}"}
```

`{#prompt#}` is replaced with user input at runtime. Plan mode supports Chinese `设置计划` → `计划` stripping.

### Logic (`type: "logic"`)

Evaluate if a condition is already implemented → jump accordingly.

```json
{"type": "logic", "id": 1, "prompt": "Is README created?", "goto_true": 3, "goto_false": 2}
```

## CLI

| Command | Description |
|---------|-------------|
| `flow` | Dashboard: init Flow/, check all |
| `flow list` | List workflows |
| `flow show <name>` | Component details |
| `flow validate <name>` | Validate single workflow |
| `flow check` | Validate all workflows |
| `flow new <name>` | Create blank workflow |
| `flow delete <name>` | Delete workflow |
| `flow run <name> -i "..." [--true/--false]` | Execute workflow (fuzzy name match) |
| `flow auto <text>` | Auto-trigger: scan text for workflow matches |
| `flow gen <description>` | Generate workflow from natural language (use `{#prompt#}` for templates) |
| `flow sum <name> --workspace .` | Generate workflow from workspace analysis |
| `flow cycles <name> [--all]` | Analyze logic flow for cycles |
| `flow serve -p 8765` | Launch HTML editor |

## Verification

```bash
python flow.py check          # Validate all workflows
python flow.py cycles --all   # Check for logic loops
python flow.py run <name> --true   # Smoke test
```

## Agent Integration

```python
from FlowDialogPlugin import ensure_flow_capability

flow_tools = ensure_flow_capability()
if flow_tools:
    bridge = flow_tools["create_bridge"]("deploy", user_input="v2")
    bridge.start()
    while not bridge.is_complete():
        step = bridge.current_step()
        if step["type"] == "dialog":
            bridge.submit_response(agent_input(step["prompt"]))
        elif step["type"] == "logic":
            bridge.submit_condition(agent_eval(step["prompt"]))
```

## Requirements

- Python 3.10+
- No external dependencies required
- `rich` (optional, for enhanced CLI output)

## See Also

- `Flow/Flow.md` — Full format specification
- `FlowDialogPlugin/README.md` — Bridge API documentation
- `OpenCode_goal_plugin/README.md` — Goal plugin documentation

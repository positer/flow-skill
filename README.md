# Flow Workflow System

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Multi-agent workflow system with Python CLI, HTML tree editor, and agent-integrated FlowDialogPlugin. Create, edit, validate, and execute sequential workflows using dialog (Build/Plan/Goal) and logic (conditional branching) components saved as `*.Flow.json` files.

## Quick Start

```bash
python flow.py              # Dashboard — auto-init, validate all
python flow.py list         # List workflows
python flow.py run <name>   # Execute workflow (fuzzy name match)
python flow.py serve        # Launch HTML tree editor
```

## Theoretical Research Pipeline

`theoretical-research` is a 42-component (30 dialog + 12 logic) generic workflow for theoretical physics/mathematics research. It captures the full pipeline:

1. **Phase 0-2: Foundations** — Workspace audit, literature survey, mathematical framework setup
2. **Phase 3-6: Core Computation** — 8-step Bosonic sector → Fermionic extension → High-order singularities → Renormalization
3. **Phase 7-8: Classification** — Lie subgroup topology → Manifold topology → Unified theorem
4. **Phase 9-10: Verification** — n=5/pp-wave specialization, LaTeX draft assembly
5. **Phase 11-15: Review Cycle** — 4 independent subagent review → revision loop → 2 consecutive clean confirmation rounds → final paper assembly

All prompts use `{#prompt#}` placeholders for injection of specific research problems at runtime.

```bash
python flow.py run theoretical-research -i "Ads^n x S^m three-string vertex unified theory"
```

## Project Structure

```
flow-skill/
├── flow.py                      # CLI engine + workflow runner (951 lines)
├── FlowEditor.html              # Visual tree editor (standalone HTML)
├── pyproject.toml               # Project metadata
├── requirements.txt             # Dependencies
├── SKILL.md                     # Skill definition for OpenCode
├── README.md
├── .gitignore
│
├── Flow/                        # Workflow definitions (*.Flow.json)
│   ├── Flow.md                  # Format specification (139 lines)
│   ├── add_list_sum.Flow.json              # Sample: 8-component workflow
│   ├── feature-dev.Flow.json               # Sample: 5-component feature dev
│   ├── flow-test.Flow.json                 # Test: 7-component (all types + logic jumps)
│   └── theoretical-research.Flow.json      # Generic: 42-component theoretical research pipeline
│
├── FlowDialogPlugin/            # Dialog bridge for agents without native flow
│   ├── __init__.py              # Package exports + auto-detection
│   ├── dialog_plugin.py         # FlowDialogBridge + ensure_flow_capability()
│   └── README.md
│
├── OpenCode_goal_plugin/        # Goal fallback for agents without native goal
│   ├── __init__.py
│   ├── goal_plugin.py           # GoalManager + ensure_goal_capability()
│   └── README.md
│
└── archive/                     # Session history (date-stamped)
```

## Architecture

| Layer | Component | Responsibility |
|-------|-----------|----------------|
| **Format** | `*.Flow.json` | JSON-based workflow definition with sequentially-addressed components |
| **Engine** | `flow.py` | CLI, validation, execution, auto-trigger |
| **Dialog** | `FlowDialogPlugin/` | Step-based bridge — wraps `run_workflow_iter()` generator into start/step/response API |
| **Goal** | `OpenCode_goal_plugin/` | Lightweight JSON-backed goal tracking |
| **Editor** | `FlowEditor.html` | Visual workflow editor (drag-free: click-to-edit tree) |
| **Skill** | `SKILL.md` | OpenCode skill definition with auto-trigger descriptions |

### Plugin Architecture

Flow ships with two companion plugins that auto-activate when the host agent lacks native support:

| Plugin | Trigger | Provides |
|--------|---------|----------|
| `OpenCode_goal_plugin` | Agent has no `get_goal`/`update_goal` tools | `GoalManager` — JSON-backed goal tracking |
| `FlowDialogPlugin` | Agent has no `opencode.run_flow` tool | `FlowDialogBridge` — step-based workflow execution |

**Goal mode integration**: When a workflow reaches a `Goal`-mode dialog component, the bridge calls `OpenCode_goal_plugin`'s `set_goal()` to establish the objective and `update_goal("completed")` on completion. This means every Flow workflow's Goal step automatically benefits from goal persistence — whether through OpenCode's native tools or the plugin fallback.

### Key Design Decisions

- **Generator protocol**: `run_workflow_iter()` uses `yield`/`send` instead of blocking I/O, allowing external agents to drive execution step by step
- **Plugin detection**: `FlowDialogPlugin` and `OpenCode_goal_plugin` auto-detect native agent support before activating (env vars + tool/import check)
- **Conversation boundary**: `FlowDialogBridge` is a transport layer only — the caller is responsible for injecting prompts as real conversation turns
- **Plan mode**: Chinese `设置计划` → `计划` stripping via `str.replace()` in Plan mode only
- **Cycle safety**: Static pre-flight graph analysis + runtime max-visit guard (10 visits/component)

## Workflow Components

### Dialog (`type: "dialog"`)

Modes: `Build` (execute task), `Plan` (create plan), `Goal` (set long-term objective).

```json
{"type": "dialog", "id": 0, "mode": "Plan", "prompt": "Plan: {#prompt#}"}
```

- `{#prompt#}` is replaced with user input at runtime
- If absent, user input is appended as additional context

### Logic (`type: "logic"`)

Evaluates a condition → jumps to `goto_true` (implemented) or `goto_false` (not implemented).

```json
{"type": "logic", "id": 1, "prompt": "Is README created?", "goto_true": 3, "goto_false": 2}
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `flow` | Dashboard: init, validate all, show descriptions |
| `flow list` | List workflows with descriptions |
| `flow show <name>` | Show component details |
| `flow validate <name>` | Validate single workflow |
| `flow check` | Validate all workflows |
| `flow new <name>` | Create blank workflow |
| `flow delete <name>` | Delete a workflow |
| `flow run <name> -i "..." [--true/--false]` | Execute workflow (fuzzy name match) |
| `flow auto <text>` | Auto-trigger: scan text for workflow name matches |
| `flow gen <description>` | Generate workflow from natural language (use `{#prompt#}` for templates) |
| `flow cycles <name> [--all]` | Analyze logic flow for potential cycles |
| `flow sum <name> [--workspace] [--force]` | Generate workflow from workspace analysis |
| `flow serve -p 8765` | Launch HTML tree editor |

## Verification

```bash
python flow.py check          # Validate all workflows
python flow.py cycles --all   # Check for logic loops
python flow.py run <name> --true   # Smoke test (all conditions true)
```

## Agent Integration

Both plugins auto-detect native support and fall back gracefully:

```python
from OpenCode_goal_plugin import ensure_goal_capability
from FlowDialogPlugin import ensure_flow_capability

# Goal capability (used by Goal-mode dialog components)
goal_tools = ensure_goal_capability()
if goal_tools:
    goal_tools["set_goal"]("Complete deployment workflow")

# Flow dialog capability (workflow execution bridge)
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
- No external dependencies required for core functionality
- `rich` (optional, for enhanced CLI output)

## See Also

- `Flow/Flow.md` — Full format specification
- `FlowDialogPlugin/README.md` — Bridge API documentation
- `OpenCode_goal_plugin/README.md` — Goal plugin documentation

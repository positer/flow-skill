# Flow Workflow System

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A lightweight multi-agent workflow engine, standalone skill, and callable plugin. Define sequential workflows as `*.Flow.json` files — **dialog** (Plan/Build/Goal) and **logic** (conditional branching) components with cycle-safe, chat-visible execution.

## Architecture

```
Flow Engine (flow.py)
  ├── CLIStepHandler      — stdin/stdout (terminal)
  ├── GeneratorStepHandler — yield/send (agent frameworks)
  ├── MCPToolHandler      — JSON-RPC tools (OpenCode/Codex/Harness)
  └── flow-mcp.py         — callable plugin server
```

| Layer | Component | Role |
|-------|-----------|------|
| **Format** | `*.Flow.json` | Version-controlled workflow definitions |
| **Engine** | `flow.py` | CLI, validation, execution (1548 lines) |
| **Handlers** | `StepHandler` ABC | Pluggable dialog/logic I/O: CLI, Generator, MCP |
| **Bridge** | `FlowDialogPlugin` | Auto-injects step-by-step execution for agents |
| **Editor** | `FlowEditor.html` | Visual tree editor (standalone HTML) |
| **Gen** | `flow gen` | Harness-inspired pipeline generation from natural language |
| **Plugin** | `.codex-plugin/`, `.claude-plugin/`, `.mcp.json` | Codex/Claude plugin packaging and callable MCP tools |

### StepHandler — Universal Agent Interface

All agent calling patterns map to the same `StepHandler` interface:

```python
class StepHandler(ABC):
    def on_dialog(self, step_id, mode, prompt) -> str   # returns response
    def on_logic(self, step_id, prompt) -> bool           # returns T/F
    def on_goal_verify(self, goal, work) -> bool          # bounce-back check
```

- **CLIStepHandler** — stdin `input()` with `---done---` terminator, T/F prompts
- **GeneratorStepHandler** — yield/send protocol for agent frameworks
- **MCPToolHandler** — tool call buffer for OpenCode, Claude Code, Codex, Harness

### Goal Mode: Self-Contained Bounce-Back

Goal components execute as **Build + Logic composite**: prompt runs, then auto-injects a verification logic step. Not achieved → loops back. No external plugin dependency.

### Chat-Area Execution

Agent integrations should prefer `run_workflow_iter()`, `FlowDialogBridge`, or
the MCP tools over terminal stdout. Each step includes chat rendering metadata:
`chat_header`, `display_title`, `rendered_prompt`, branch decision, target, and
completion/error state. The Agent should display each step in the conversation
area before executing or advancing it.

## Pipeline Generation (`flow gen`)

Modeled after Harness CI/CD pipelines. Auto-detects type, groups steps into stages, injects failure recovery and approval gates.

```bash
flow gen "build then test then deploy"
flow gen "implement feature then verify tests pass then create pr"
flow gen "derive theorem then prove lemmas then write paper"
```

**Pipeline types:** CI, CD, FEATURE, RESEARCH, REVIEW  
**Generated structure:** Stage labels → dialog actions → logic conditions → failure recovery checks → inter-stage approval gates → Goal completion

## Quick Start

```bash
python flow.py                    # Dashboard
python flow.py list               # List workflows
python flow.py run <name>         # Execute (fuzzy name match)
python flow.py gen "build test deploy"  # Generate pipeline
python flow.py serve              # HTML tree editor
```

## Featured: Theoretical Research Pipeline

42-component workflow automating full research pipeline — literature audit to final LaTeX. 5 phases, 4-way subagent peer review, SymPy-gated computation steps.

```bash
python flow.py run theoretical-research -i "Ads^n x S^m three-string vertex unified theory"
```

## CLI

| Command | Description |
|---------|-------------|
| `flow` | Dashboard: init, check all |
| `flow list` | List workflows |
| `flow show <name>` | Component details |
| `flow validate <name>` | Validate single workflow |
| `flow check` | Validate all |
| `flow new <name>` | Create blank |
| `flow delete <name>` | Delete workflow |
| `flow run <name> -i "..." [--true/--false]` | Execute (fuzzy name) |
| `flow auto <text>` | Auto-trigger: scan for matches |
| `flow gen <description>` | Generate pipeline from natural language |
| `flow sum <name> --workspace .` | Generate from workspace analysis |
| `flow cycles <name> [--all]` | Analyze logic for cycles |
| `flow serve -p 8765` | Launch HTML editor |

## Project Structure

```
Flow/                             # Workflow definitions
├── Flow.md                       # Format specification
├── add_list_sum.Flow.json        # Sample (8 comps)
├── feature-dev.Flow.json         # Feature dev (5 comps)
├── flow-test.Flow.json           # Test workflow (7 comps)
└── theoretical-research.Flow.json # Research pipeline (42 comps)

flow.py                           # CLI + engine (1548 lines)
FlowEditor.html                   # Tree editor
FlowDialogPlugin/                 # Dialog bridge for agents
SKILL.md                          # OpenCode skill
.codex-plugin/plugin.json         # Codex plugin manifest
.claude-plugin/plugin.json        # Claude Code plugin manifest
.mcp.json                         # MCP server registration
bin/flow-mcp.py                   # Callable Flow plugin tools
OVERVIEW.md                       # Project structure and purpose
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

Goal mode yields two steps (dialog + verification logic) transparently through the bridge.

## Callable Plugin Tools

The MCP server exposes:

- `flow_list_workflows`
- `flow_find_workflow`
- `flow_auto_trigger`
- `flow_start_workflow`
- `flow_current_step`
- `flow_submit_dialog_response`
- `flow_submit_logic_condition`

## Requirements

- Python 3.10+
- No external dependencies

## See Also

- `Flow/Flow.md` — Format specification + gen guide
- `FlowDialogPlugin/README.md` — Bridge API

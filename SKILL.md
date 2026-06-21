---
name: flow
description: "Multi-agent workflow system with Python CLI, HTML tree editor, and agent-integrated FlowDialogPlugin. Create, edit, validate, and execute sequential workflows using dialog (Build/Plan/Goal) and logic (conditional branching) components saved as *.Flow.json files. FlowDialogPlugin provides step-based dialog bridge for agents without native flow support. Triggers include: /Flow, flow workflow, flow list, flow run, flow new, flow check, flow show, flow validate, flow serve, flow sum, flow dashboard, FlowEditor, workflow editor, *.Flow.json, workflow file, run workflow, execute workflow, conditional workflow, dialog component, logic component, goto branch, {#prompt#}, FlowDialogPlugin, flow bridge, step-based execution, dialog plugin, Flow工作流, 工作流编辑器, 工作流启动, 生成工作流, 总结工作流, 对话插件, 流式执行."
license: Proprietary
---

# Flow Workflow System

## Quick Start — `/Flow`

Run `flow` with no arguments to auto-detect the `Flow/` directory and show dashboard:

```bash
python /path/to/flow.py
```

Output example:
```
  Flow directory: /path/to/project/Flow

  OK deploy    3d 2l  (Plan) Plan deployment → if ready? → (Build) Deploy → ...
  OK review    2d 1l  (Build) Run review → ...

  Summary: 2 workflow(s), 5 dialog, 3 logic
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `flow` | Dashboard: auto-init Flow/, ensure Flow.md, check all |
| `flow list` | List workflows with natural language descriptions |
| `flow show <name>` | Show component details |
| `flow validate <name>` | Validate a single workflow |
| `flow check` | Validate all workflows |
| `flow new <name>` | Create blank workflow |
| `flow delete <name>` | Delete a workflow |
| `flow run <name> -i "..."` | Execute workflow (**fuzzy name matching**) |
| `flow auto <text>` | Auto-trigger: scan text for matching workflow names |
| `flow sum <name>` | Generate workflow from workspace analysis |
| `flow serve -p 8765` | Launch HTML editor |

## Workflow Components

### Dialog Component (`type: "dialog"`)

- **mode**: `"Build"`, `"Plan"`, or `"Goal"` (NOT `"Flow"`)
- **prompt**: Base prompt with `{#prompt#}` placeholder for user input
- **Plan mode convention**: prompt wraps user input as planning instruction

### Logic Component (`type: "logic"`)

- **prompt**: Condition to evaluate (also supports `{#prompt#}`)
- **goto_true** / **goto_false**: Component IDs to jump to
- **Evaluation**: Agent judges whether condition is already implemented in workspace

## Auto-Trigger & Fuzzy Matching

Workflows can be launched by exact name or fuzzy match:

```
# Exact match
flow run deploy

# Fuzzy match (finds "deploy_website")
flow run deploy

# Auto-detect from conversation
flow auto "请帮我整理工作区"
→ [FUZZY 0.85] add_list_sum  Plan: read current structure → ...
```

The `auto` subcommand returns ranked candidates. Score >= 0.5 is recommended for execution.

## OpenCode-goal-plugin (`OpenCode_goal_plugin/`)

Built-in plugin providing `get_goal`/`update_goal` capability for agents that lack native goal support.

**Activation**: Auto-detects native goal capability. Only activates when absent.
**Persistence**: Stores goals in `.opencode/goals/state.json`.
**Integration**: Flow's Goal mode dialog components use this plugin to set/complete goals.

## Format Specification

See `Flow/Flow.md` for complete schema documentation.

## FlowDialogPlugin (`FlowDialogPlugin/`)

Built-in plugin providing step-based dialog execution for agents that lack native flow support. Mirrors the `OpenCode_goal_plugin` pattern: **detect native capability → fallback injection → same interface**.

**Activation**: Auto-detects native flow capability. Only activates when absent.
**Bridge**: `FlowDialogBridge` wraps `run_workflow_iter()` generator into a stateful object.
**Conversation mapping**: Dialog component prompts become real conversation turns (not stdout).

### Agent Loop Using the Bridge

```python
from FlowDialogPlugin import FlowDialogBridge

bridge = FlowDialogBridge("feature-dev", "Flow/", user_input="add auth")
step = bridge.start()

while not bridge.is_complete():
    if step["type"] == "dialog":
        # Present as real conversation turn
        print(f"[{step['mode']}] {step['prompt']}")
        response = input("Your response: ")
        step = bridge.submit_response(response)
    elif step["type"] == "logic":
        condition = ask_llm(f"Is this true?\n{step['prompt']}")
        step = bridge.submit_condition(condition)
```

### Plugin Auto-Install

```python
from FlowDialogPlugin import ensure_flow_capability

flow_tools = ensure_flow_capability()
if flow_tools:
    bridge = flow_tools["create_bridge"]("deploy", user_input="v2")
    bridge.start()
    # ... drive execution ...
```

## Python API

### CLI (blocking, for terminal use)

```python
from flow import load_workflow, run_workflow, find_workflow, auto_trigger

wf = load_workflow("deploy", "Flow/")
name = find_workflow("deploy", "Flow/")      # fuzzy match
matches = auto_trigger("deploy website", "Flow/")  # auto-detect

def my_eval(prompt: str) -> bool:
    return call_llm(prompt)

run_workflow("deploy", "Flow/", user_input="v2", llm_eval=my_eval)
```

### Generator (step-based, for agent integration)

```python
from flow import run_workflow_iter

wf_iter = run_workflow_iter("deploy", "Flow/", user_input="v2")
step = next(wf_iter)
while step["type"] not in ("complete", "error"):
    if step["type"] == "dialog":
        step = wf_iter.send({"type": "dialog_response", "response": user_reply})
    elif step["type"] == "logic":
        step = wf_iter.send({"type": "logic_response", "condition": llm_result})
```

## File Structure

```
Flow/
├── Flow.md                  # Format specification (auto-created)
├── my_workflow.Flow.json    # Saved workflows
└── ...

OpenCode_goal_plugin/        # Built-in goal capability
├── __init__.py
├── goal_plugin.py
└── README.md

FlowDialogPlugin/            # Built-in flow dialog bridge
├── __init__.py
├── dialog_plugin.py
└── README.md

flow.py                      # CLI + execution engine
FlowEditor.html              # Visual workflow editor
SKILL.md                     # This file
```

## File Structure

```
Flow/
├── Flow.md                  # Format specification (auto-created)
├── my_workflow.Flow.json    # Saved workflows
└── ...

OpenCode_goal_plugin/        # Built-in goal capability
├── __init__.py
├── goal_plugin.py
└── README.md

flow.py                      # CLI + execution engine
FlowEditor.html              # Visual workflow editor
SKILL.md                     # This file
```

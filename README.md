# Flow Workflow System

Multi-agent workflow system with Python CLI and HTML tree editor. Create, edit, validate, and execute sequential workflows using dialog (Build/Plan/Goal) and logic (conditional branching) components saved as `*.Flow.json` files.

## Quick Start

```bash
python flow.py              # Dashboard
python flow.py list         # List workflows
python flow.py run <name>   # Execute workflow (fuzzy name match)
python flow.py serve        # Launch HTML editor
```

## Structure

```
flow-skill/
├── flow.py                  # CLI + execution engine (857 lines)
├── FlowEditor.html          # Visual workflow editor
├── Flow/
│   ├── Flow.md             # *.Flow.json format specification
│   ├── add_list_sum.Flow.json   # Sample: 8-component workflow
│   └── feature-dev.Flow.json    # Sample: 5-component feature dev workflow
├── OpenCode_goal_plugin/   # Built-in goal capability (for agents without native goal)
│   ├── __init__.py
│   ├── goal_plugin.py
│   └── README.md
FlowDialogPlugin/       # Built-in flow dialog bridge (for agents without native flow)
│   ├── __init__.py
│   ├── dialog_plugin.py
│   └── README.md
├── SKILL.md                # Skill definition for OpenCode
├── README.md
├── archive/                # Session history
└── dirt/                   # Source backup (original copies)
```

## Architecture

- **Flow.json** — JSON-based workflow definition with sequentially-addressed components
- **Dialog Component** — Executes in Build/Plan/Goal mode with `{#prompt#}` placeholder
- **Logic Component** — Conditional branch: evaluate condition (is it implemented?) → goto true/false target
- **Runner** — Sequential execution engine with cycle detection and goto support
- **Fuzzy Matching** — `find_workflow()` tries exact → case-insensitive → substring
- **Auto-trigger** — `auto_trigger()` scans text for word overlap; scores ≥ 0.5 recommended for auto-execution
- **Cycle Protection** — Static pre-flight graph analysis + runtime max-visit guard (10 visits/component)
- **Goal Plugin** — Auto-detects if agent lacks native goal tools; installs JSON-backed alternative
- **FlowDialogPlugin** — Step-based dialog bridge that converts workflow execution into agent conversation turns; only activates when native flow support is absent

## CLI Commands

| Command | Description |
|---------|-------------|
| `flow` | Dashboard: init Flow/, create Flow.md, validate all |
| `flow list` | List workflows with descriptions |
| `flow show <name>` | Show component details |
| `flow validate <name>` | Validate a single workflow |
| `flow check` | Validate all workflows |
| `flow new <name>` | Create blank workflow |
| `flow delete <name>` | Delete a workflow |
| `flow run <name> -i "..." [--true/--false]` | Execute workflow |
| `flow auto <text>` | Auto-trigger: scan text for matching workflow names |
| `flow cycles <name> [--all]` | Analyze for potential logic cycles |
| `flow sum <name> [--workspace] [--force]` | Generate workflow from workspace analysis |
| `flow serve -p 8765` | Launch HTML editor |

## Workflow Format

```json
{
  "name": "my_workflow",
  "components": [
    {"type": "dialog", "id": 0, "mode": "Plan",  "prompt": "Plan: {#prompt#}"},
    {"type": "logic",  "id": 1, "prompt": "Is README created?", "goto_true": 3, "goto_false": 2},
    {"type": "dialog", "id": 2, "mode": "Build", "prompt": "Create file: {#prompt#}"},
    {"type": "dialog", "id": 3, "mode": "Goal",  "prompt": "Goal: {#prompt#}"}
  ]
}
```

See `Flow/Flow.md` for complete documentation.

## Verification

```bash
python flow.py check        # Validate all workflows
python flow.py cycles --all # Check for logic loops
python flow.py run <name> --true  # Smoke test with all conditions true
```

## See Also

- `Flow/Flow.md` — Full format specification
- `archive/` — Session history

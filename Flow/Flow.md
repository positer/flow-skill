# Flow Workflows — Format Specification

Files: `Flow/{name}.Flow.json`

## Schema

```json
{
  "name": "my_workflow",
  "components": [
    { "type": "dialog", "id": 0, "mode": "Plan",  "prompt": "..." },
    { "type": "logic",  "id": 1, "prompt": "...", "goto_true": 3, "goto_false": 2 },
    { "type": "dialog", "id": 2, "mode": "Build", "prompt": "..." },
    { "type": "dialog", "id": 3, "mode": "Goal",  "prompt": "..." }
  ]
}
```

## Components

### Dialog Component (`type: "dialog"`)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | yes | Must be `"dialog"` |
| `id` | int | yes | Sequential address (0, 1, 2...). Execution order. |
| `mode` | string | yes | `"Build"`, `"Plan"`, or `"Goal"`. Determines agent mode. NOTE: `"Flow"` is NOT a valid mode (reserved for workflow-level dispatch). |
| `prompt` | string | yes | Base prompt. Use `{#prompt#}` as placeholder for user input. |

**Prompt substitution rules:**
- `{#prompt#}` is replaced with user input at execution time
- If `{#prompt#}` is absent, user input is appended as additional context
- **Plan mode**: base prompt SHOULD frame the planning task. Example:
  - Base prompt: `听从以下指令设置计划：{#prompt#}`
  - User input: `整理工作区`
  - Executed prompt: `听从以下指令计划：整理工作区`  (Plan mode strips redundant planning language; `{#prompt#}` is replaced directly, and the prompt structure implies planning)
- **Build mode**: direct execution of the specified task
- **Goal mode**: sets a long-term objective for the agent to pursue

### Logic Component (`type: "logic"`)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | yes | Must be `"logic"` |
| `id` | int | yes | Sequential address |
| `prompt` | string | yes | Condition to evaluate. Use `{#prompt#}` for user input. |
| `goto_true` | int | yes | Component ID to jump to if condition is TRUE (already implemented) |
| `goto_false` | int | yes | Component ID to jump to if condition is FALSE (not yet implemented) |

**Evaluation behavior:**
- The agent evaluates whether the condition described by `prompt` is **already implemented in the current workspace**
- If TRUE (already implemented) → jump to `goto_true`, continue sequential from there
- If FALSE (not implemented) → jump to `goto_false`, continue sequential from there

**Logic component prompt examples:**
- `"Does the project have a README.md?"` — TRUE → skip creation; FALSE → goto creation step
- `"Is the API endpoint /users implemented?"` — TRUE → goto test step; FALSE → goto implementation
- `"Are all tests passing?"` — TRUE → goto deploy; FALSE → goto fix step

## Execution Semantics

```
Execution starts at component with id=0.
For each component in id order:
  Dialog → execute prompt, advance to next id
  Logic  → evaluate condition, jump to goto_true or goto_false
After goto → continue sequential from the target component
Cycle detection → stops if same component is re-entered >10 times
```

**Component IDs must be unique** across the workflow and should form a sequential chain (0, 1, 2, ...). Non-sequential IDs are allowed but must all be reachable from the start via sequential traversal or logic jumps.

### Cycle Detection

Flow provides two levels of cycle protection:
1. **Static pre-flight**: `detect_cycles_static()` analyzes the workflow graph before execution and warns about potential cycles involving logic goto-back pairs
2. **Runtime guard**: each component tracks visit count; if visited >10 times, execution stops with a cycle-detected message

## Validation Rules

Validation (`flow check` / `flow validate`) checks:
1. All component IDs are unique
2. Dialog mode is one of: Build, Plan, Goal (NOT Flow)
3. Logic goto_true and goto_false point to existing component IDs
4. First component ID is 0 (advisory)

## Auto-Trigger & Fuzzy Matching

Agents can auto-detect workflows from conversation text:

```
flow auto "请帮我整理工作区"
→ [FUZZY 0.85] add_list_sum  Plan: read current structure → ...
→ [WEAK  0.30] review        Run review → commands → ...

flow run add_list_sum  # fuzzy match: exact → case-insensitive → substring
```

The `auto` command scans text for workflow names and returns ranked candidates:
- **Exact match** (score 1.0): name matches verbatim
- **Fuzzy match** (score 0.5-0.9): name is a substring of the input, or vice versa
- **Word overlap** (score 0.2-0.8): individual words match

For auto-execution, scores ≥ 0.5 are recommended.

## Agent Integration

When an agent detects workflow intent in user input:
1. Call `flow auto "<user message>"` to find matching workflows
2. If best score ≥ 0.5, ask user confirmation: `"Detected workflow '{name}'. Run it? [Y/n]"`
3. If confirmed, run: `flow run "<name>" --input "<context>"`

For LLM-based logic evaluation without CLI, use the Python API:
```python
from flow import load_workflow, run_workflow

def my_llm_eval(prompt: str) -> bool:
    return call_my_llm(f"Is this condition met?\n{prompt}\nAnswer TRUE/FALSE:")

run_workflow("deploy", "Flow/", user_input="deploy v2", llm_eval=my_llm_eval)
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `flow` (no args) | Dashboard: auto-init Flow/, check all, show descriptions |
| `flow list` | List workflows with descriptions |
| `flow show <name>` | Show component details |
| `flow validate <name>` | Validate a single workflow |
| `flow check` | Validate all workflows |
| `flow new <name>` | Create blank workflow |
| `flow delete <name>` | Delete a workflow |
| `flow run <name> -i "..." [--true/--false]` | Execute workflow (fuzzy name matching) |
| `flow auto <text>` | Auto-trigger: scan text for matching workflow names |
| `flow cycles <name> [--all]` | Analyze workflow structure for potential cycles |
| `flow sum <name> [--workspace] [--force]` | Generate workflow from workspace analysis |
| `flow sum <name> --print-context` | Show workspace context without generating |
| `flow serve -p 8765` | Launch HTML editor |

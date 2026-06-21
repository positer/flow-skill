# FlowDialogPlugin

Dialog execution bridge for agents without native flow workflow support.

## When It Activates

The plugin auto-detects whether the host agent already has native flow dialog
execution tools. Activation happens ONLY when native flow support is absent
— checked via:
- Environment variable `OPENCODE_NATIVE_FLOW=1`
- `opencode.run_flow` tool presence

## What It Provides

| Function | Description |
|----------|-------------|
| `ensure_flow_capability()` | Returns flow tools dict if activated, None if native |
| `FlowDialogBridge(name, flow_dir, user_input)` | Step-by-step workflow executor |
| `list_workflows(flow_dir)` | List all workflow names |
| `find_workflow(name, flow_dir)` | Fuzzy-match a workflow name |
| `auto_trigger(text, flow_dir)` | Scan text for matching workflow names |

## Bridge API

`FlowDialogBridge` wraps `flow.py`'s `run_workflow_iter()` generator into a
stateful object that an agent framework can drive one step at a time:

```python
bridge = FlowDialogBridge("my_workflow", "Flow/")

# Start → get first step
step = bridge.start()

while not bridge.is_complete():
    if step["type"] == "dialog":
        # Present prompt to user as a real conversation turn
        response = agent_input(f"[{step['mode']}] {step['prompt']}")
        step = bridge.submit_response(response)
    elif step["type"] == "logic":
        condition = agent_eval(step["prompt"])
        step = bridge.submit_condition(condition)
    elif step["type"] == "error":
        break
```

## Integration

```python
# In agent bootstrap:
from FlowDialogPlugin import ensure_flow_capability

flow_tools = ensure_flow_capability()
if flow_tools:
    bridge = flow_tools["create_bridge"]("deploy", user_input="v2")
    bridge.start()
    while not bridge.is_complete():
        step = bridge.current_step()
        # ... drive execution ...
```

## Conversation Injection Boundary

**Critical design note**: `FlowDialogBridge` is a **transport layer**, not an injector.

It handles the workflow protocol (sequencing, goto, cycle detection) and yields
dialog prompts as structured step dicts. But the actual **injection of the
prompt into the agent's conversation** is the **caller's responsibility** —
the agent framework that consumes the bridge.

The intended injection flow is:

```
Bridge yields dialog step {prompt: "..."} 
  → Agent framework presents prompt as a real conversation turn
    → LLM/user generates a response
      → Bridge.submit_response(response) advances to next step
```

This separation of concerns allows the bridge to be framework-agnostic.
Example agent loops are shown in the **Bridge API** section above.

## How It Works

The core idea mirrors `OpenCode_goal_plugin`:

1. **Detection**: Check if the agent already has native flow dialog tools
2. **Fallback**: If absent, use `run_workflow_iter()` generator from `flow.py`
3. **Bridge**: Convert the generator's yield/send protocol into a simple
   start/step/response API that any agent framework can consume
4. **Conversation mapping**: Dialog component prompts are yielded as step
   dicts for the agent framework to present as actual conversation turns,
   rather than being printed to stdout

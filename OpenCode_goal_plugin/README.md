# OpenCode-goal-plugin

Built-in goal capability for agents without native `get_goal`/`update_goal` support.

## When It Activates

The plugin auto-detects whether the host agent already has native goal tools.
Activation happens ONLY when native goal support is absent — checked via:
- Environment variable `OPENCODE_NATIVE_GOAL=1`
- `opencode.get_goal` import availability

## What It Provides

| Function | Equivalent To |
|----------|---------------|
| `get_goal()` | Native `get_goal` tool |
| `set_goal(desc)` | Start tracking a new goal |
| `update_goal(status, summary)` | Native `update_goal` tool |
| `list_goals()` | List all tracked goals |

## Persistence

Goals are stored in `.opencode/goals/state.json` at the project root,
matching the same path that native OpenCode goal tools use.

## Integration

```python
# In agent bootstrap:
from OpenCode_goal_plugin import ensure_goal_capability
goal_tools = ensure_goal_capability()
if goal_tools:
    # Agent now has goal capability
    goal_tools["set_goal"]("Complete the deployment workflow")
```

For Flow workflow integration, the Goal mode dialog component calls
`set_goal()` before execution and `update_goal("completed")` after.

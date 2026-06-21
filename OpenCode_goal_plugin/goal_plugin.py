"""OpenCode-goal-plugin - Goal capability for agents without native goal support.

Provides the same interface as OpenCode's native get_goal/update_goal tools,
backed by a JSON file at `.opencode/goals/state.json`.

## Activation

The plugin auto-activates when it detects the agent lacks native `get_goal`/
`update_goal` tools. Call `ensure_goal_capability()` at agent init to
conditionally install the goal layer.

## Usage

```python
from OpenCode_goal_plugin import ensure_goal_capability, GoalManager

# Auto-activate if needed
goal_tools = ensure_goal_capability()

# Or use directly
gm = GoalManager()
gm.set("Refactor the authentication module")
print(gm.get())       # "Refactor the authentication module"
gm.complete("Done")   # marks as completed
```

## API Reference

- `ensure_goal_capability()` → dict or None: returns goal tools dict if activated, None if native
- `GoalManager()`: full-featured manager
  - `.get()` → str | None: current active goal
  - `.set(description)`: set a new goal
  - `.complete(summary="")`: mark current goal completed
  - `.block(reason="")`: mark current goal blocked
  - `.list_all()` → dict: all goals
"""

import json
import os
import sys
from pathlib import Path


GOAL_STATE_REL = Path(".opencode") / "goals" / "state.json"


def _detect_native_goal() -> bool:
    """Detect if the host environment has native get_goal/update_goal.

    Checks for environment variables, sys.modules, or tool presence.
    """
    if os.environ.get("OPENCODE_NATIVE_GOAL") == "1":
        return True
    try:
        from opencode import get_goal
        return True
    except (ImportError, AttributeError):
        pass
    return False


class GoalManager:
    """Persistent goal manager that mirrors OpenCode's native goal interface."""

    def __init__(self, state_path: str | Path | None = None):
        self._path = Path(state_path) if state_path else GOAL_STATE_REL
        self._data = self._load()

    def _load(self) -> dict:
        if self._path.is_file():
            try:
                return json.loads(self._path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return {"version": 1, "goals": {}}
        return {"version": 1, "goals": {}}

    def _save(self):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._data, indent=2), encoding="utf-8")

    def get(self, goal_id: str = "default") -> str | None:
        g = self._data.get("goals", {}).get(goal_id)
        if g and g.get("status") == "active":
            return g.get("description")
        return None

    def set(self, description: str, goal_id: str = "default"):
        self._data.setdefault("goals", {})[goal_id] = {
            "description": description,
            "status": "active",
            "created": __import__("datetime").datetime.now().isoformat(),
        }
        self._save()

    def update(self, goal_id: str, status: str, summary: str = ""):
        g = self._data.get("goals", {}).get(goal_id)
        if g:
            g["status"] = status
            if summary:
                g["summary"] = summary
            g["updated"] = __import__("datetime").datetime.now().isoformat()
            self._save()

    def complete(self, summary: str = "", goal_id: str = "default"):
        self.update(goal_id, "completed", summary)

    def block(self, reason: str = "", goal_id: str = "default"):
        self.update(goal_id, "blocked", reason)

    def list_all(self) -> dict:
        return dict(self._data.get("goals", {}))


def ensure_goal_capability(state_path: str | Path | None = None) -> dict | None:
    """Conditionally install goal capability.

    Returns a dict of goal tool functions if activated, None if native goal exists.
    """
    if _detect_native_goal():
        return None

    gm = GoalManager(state_path)

    tools = {
        "get_goal": lambda gid="default": gm.get(gid),
        "set_goal": lambda desc, gid="default": gm.set(desc, gid),
        "update_goal": lambda status, summary="", gid="default": gm.update(gid, status, summary),
        "list_goals": gm.list_all,
    }

    return tools

"""OpenCode-goal-plugin: Built-in goal capability for agents without native goal support.

Auto-detects whether the host agent has `get_goal`/`update_goal` tools. If not,
installs a lightweight goal tracking layer backed by `.opencode/goals/state.json`.
"""

import json
import os
from pathlib import Path

# Re-export the main API from goal_plugin
from .goal_plugin import ensure_goal_capability, GoalManager  # noqa: F401

GOAL_STATE_PATH = Path(".opencode") / "goals" / "state.json"


def agent_has_native_goal() -> bool:
    """Detect if agent already supports get_goal/update_goal tools."""
    try:
        import builtins
        return hasattr(builtins, "__opencode_goal__")
    except ImportError:
        return False


def should_activate() -> bool:
    """Returns True if this plugin should activate (agent lacks native goal)."""
    return not agent_has_native_goal()


class GoalState:
    """Persistent goal state backed by `.opencode/goals/state.json`."""

    def __init__(self):
        self._path = GOAL_STATE_PATH
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

    def get_goal(self, goal_id: str = "default") -> str | None:
        g = self._data.get("goals", {}).get(goal_id)
        return g.get("description") if g else None

    def set_goal(self, description: str, goal_id: str = "default"):
        self._data.setdefault("goals", {})[goal_id] = {
            "description": description,
            "status": "active",
        }
        self._save()

    def update_goal(self, goal_id: str = "default", status: str = "completed", summary: str = ""):
        g = self._data.get("goals", {}).get(goal_id)
        if g:
            g["status"] = status
            if summary:
                g["summary"] = summary
            self._save()

    def list_goals(self) -> dict:
        return dict(self._data.get("goals", {}))


_state: GoalState | None = None


def get_state() -> GoalState:
    global _state
    if _state is None:
        _state = GoalState()
    return _state


# Convenience API matching OpenCode's native goal interface
def goal_get() -> dict | None:
    s = get_state()
    g = s.get_goal()
    return {"description": g} if g else None


def goal_set(description: str):
    get_state().set_goal(description)


def goal_update(status: str, summary: str = ""):
    get_state().update_goal(status=status, summary=summary)

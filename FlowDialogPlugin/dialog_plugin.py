"""FlowDialogPlugin - Dialog execution bridge for agents without native flow capability.

Provides the same step-based interface that a natively flow-capable agent would,
backed by flow.py's ``run_workflow_iter()`` generator.

## Activation

The plugin auto-activates when it detects the agent lacks native flow dialog
execution tools. Call ``ensure_flow_capability()`` at agent init to conditionally
install the flow bridge layer.

## Usage

```python
from FlowDialogPlugin import ensure_flow_capability, FlowDialogBridge

# Auto-activate if needed
flow_tools = ensure_flow_capability()

# Or use directly
bridge = FlowDialogBridge("my_workflow", "Flow/")
bridge.start()
while not bridge.is_complete():
    step = bridge.current_step()
    if step["type"] == "dialog":
        response = agent_chat(f"[{step['mode']}] {step['prompt']}")
        bridge.submit_response(response)
    elif step["type"] == "logic":
        condition = agent_eval(step["prompt"])
        bridge.submit_condition(condition)
```
"""

import os
import sys
from pathlib import Path


# Allow importing flow.py from parent or sibling directories
_FLOW_MODULE = None


def _get_flow_module():
    """Lazy-import flow.py — try simple import first, then search known paths."""
    global _FLOW_MODULE
    if _FLOW_MODULE is not None:
        return _FLOW_MODULE

    try:
        import flow as _f
        _FLOW_MODULE = _f
        return _f
    except ImportError:
        pass

    import importlib.util

    candidates = [
        Path(__file__).parent.parent / "flow.py",          # sibling
        Path.cwd() / "flow.py",                              # cwd
        Path(__file__).parent.parent.parent / "flow.py",    # up 2 levels
    ]
    for path in candidates:
        if path.is_file():
            spec = importlib.util.spec_from_file_location("flow", path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            _FLOW_MODULE = mod
            return mod

    raise ImportError(
        "flow.py not found. Ensure it is in the project root, "
        "sibling to FlowDialogPlugin/, or in the current working directory."
    )


def _detect_native_flow() -> bool:
    """Detect if the host environment has native flow dialog capabilities.

    Checks for environment variables, sys.modules, or tool presence.
    """
    if os.environ.get("OPENCODE_NATIVE_FLOW") == "1":
        return True
    try:
        import opencode
        if hasattr(opencode, "run_flow"):
            return True
    except ImportError:
        pass
    return False


class FlowDialogBridge:
    """Step-by-step flow workflow executor.

    Wraps ``run_workflow_iter()`` into a stateful bridge that an agent
    framework can drive one dialog/logic step at a time.
    """

    def __init__(self, name: str, flow_dir: str = "Flow", user_input: str | None = None):
        self.name = name
        self.flow_dir = flow_dir
        self.user_input = user_input
        self._generator = None
        self._current_step = None
        self._complete = False
        self._error = None
        self._cycle_warnings = None

    def start(self) -> dict:
        """Initialize the workflow and return the first actionable step.

        Auto-skips non-actionable yields (cycle_warnings) so the caller
        always receives a dialog, logic, complete, or error step.

        Returns the first step dict, or a completion/error dict.
        """
        flow = _get_flow_module()
        self._generator = flow.run_workflow_iter(self.name, self.flow_dir, self.user_input)
        try:
            self._current_step = next(self._generator)
            # auto-skip non-actionable yields (cycle_warnings)
            while self._current_step and self._current_step.get("type") == "cycle_warning":
                self._cycle_warnings = self._current_step.get("warnings")
                self._current_step = next(self._generator)
            self._check_complete()
            return self._current_step
        except StopIteration:
            self._complete = True
            return {"type": "complete", "message": "Workflow complete."}

    def current_step(self) -> dict:
        """Return the current step without advancing."""
        return self._current_step

    def submit_response(self, response: str) -> dict:
        """Submit a dialog response and advance to the next step.

        Args:
            response: Free-text response from the agent/user.

        Returns:
            The next step dict.
        """
        return self._advance({"type": "dialog_response", "response": response})

    def submit_condition(self, condition: bool) -> dict:
        """Submit a logic condition evaluation and advance.

        Args:
            condition: True (goto_true) or False (goto_false).

        Returns:
            The next step dict.
        """
        return self._advance({"type": "logic_response", "condition": condition})

    def _advance(self, value: dict) -> dict:
        if self._complete or self._generator is None:
            return self._current_step or {"type": "error", "message": "No active workflow."}
        try:
            self._current_step = self._generator.send(value)
            # auto-skip non-actionable yields
            while self._current_step and self._current_step.get("type") == "cycle_warning":
                self._cycle_warnings = self._current_step.get("warnings")
                self._current_step = self._generator.send(None)
            self._check_complete()
            return self._current_step
        except StopIteration:
            self._complete = True
            return {"type": "complete", "message": "Workflow complete."}

    def _check_complete(self):
        if self._current_step and self._current_step.get("type") in ("complete", "error"):
            self._complete = True
            if self._current_step["type"] == "error":
                self._error = self._current_step.get("message")

    def is_complete(self) -> bool:
        return self._complete

    def error(self) -> str | None:
        return self._error

    def cycle_warnings(self) -> list | None:
        if self._current_step and self._current_step.get("type") == "cycle_warning":
            return self._current_step.get("warnings")
        return None

    def reset(self):
        """Reset the bridge to allow re-execution."""
        self._generator = None
        self._current_step = None
        self._complete = False
        self._error = None
        self._cycle_warnings = None


def ensure_flow_capability(flow_dir: str = "Flow") -> dict | None:
    """Conditionally install flow dialog capability.

    Returns a dict of flow tool functions if activated, None if native flow
    capability already exists.

    The returned tools dict mirrors what a natively flow-capable agent would
    provide:

    - ``list_workflows()`` → list of workflow names
    - ``find_workflow(name)`` → fuzzy-matched name or None
    - ``auto_trigger(text)`` → ranked matches
    - ``create_bridge(name, user_input)`` → FlowDialogBridge instance
    """
    if _detect_native_flow():
        return None

    flow = _get_flow_module()

    tools = {
        "list_workflows": lambda: flow.list_workflows(flow_dir),
        "find_workflow": lambda name: flow.find_workflow(name, flow_dir),
        "auto_trigger": lambda text: flow.auto_trigger(text, flow_dir),
        "describe_workflow": lambda name: flow.describe_workflow(name, flow_dir),
        "create_bridge": lambda name, user_input=None: FlowDialogBridge(name, flow_dir, user_input),
    }

    return tools

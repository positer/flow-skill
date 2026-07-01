"""FlowDialogPlugin: Dialog execution bridge for agents without native flow support.

Auto-detects whether the host agent has built-in flow dialog execution
capabilities. If not, installs a lightweight bridge layer backed by
flow.py's ``run_workflow_iter()`` step-based generator.

The bridge converts workflow execution into a sequence of step dicts
that the agent framework can present as actual conversation turns.
"""

from .dialog_plugin import ensure_flow_capability, FlowDialogBridge, render_chat_step  # noqa: F401

import os


def agent_has_native_flow() -> bool:
    """Detect if the agent already supports native flow dialog execution."""
    try:
        import builtins
        return hasattr(builtins, "__opencode_flow__")
    except ImportError:
        return False


def should_activate() -> bool:
    """Returns True if this plugin should activate (agent lacks native flow)."""
    return not agent_has_native_flow()


def list_workflows(flow_dir: str = "Flow") -> list[str]:
    """Convenience: list all workflow names in the flow directory."""
    from .dialog_plugin import _get_flow_module
    return _get_flow_module().list_workflows(flow_dir)


def find_workflow(name: str, flow_dir: str = "Flow") -> str | None:
    """Convenience: fuzzy-find a workflow by name."""
    from .dialog_plugin import _get_flow_module
    return _get_flow_module().find_workflow(name, flow_dir)


def auto_trigger(text: str, flow_dir: str = "Flow") -> list[tuple[str, float]]:
    """Convenience: scan text for matching workflow names."""
    from .dialog_plugin import _get_flow_module
    return _get_flow_module().auto_trigger(text, flow_dir)

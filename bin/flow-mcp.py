#!/usr/bin/env python
"""MCP stdio server for Flow workflows.

The tools expose Flow as a callable plugin surface. Workflow execution is
stateful: start_workflow returns the first chat-renderable step, then callers
submit dialog or logic results to advance.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import traceback
import uuid
from pathlib import Path
from typing import Any


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
_PLUGIN_SKILL_ROOT = PLUGIN_ROOT / "skills" / "flow"
SKILL_ROOT = _PLUGIN_SKILL_ROOT if (_PLUGIN_SKILL_ROOT / "flow.py").is_file() else PLUGIN_ROOT


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {name} from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


flow = _load_module("flow", SKILL_ROOT / "flow.py")
sys.path.insert(0, str(SKILL_ROOT))
from FlowDialogPlugin import FlowDialogBridge, render_chat_step  # noqa: E402


SESSIONS: dict[str, FlowDialogBridge] = {}


def _flow_dir(value: str | None = None) -> str:
    if value:
        return value
    return os.environ.get("FLOW_DIR", str(SKILL_ROOT / "Flow"))


def _ok(value: Any) -> dict:
    return {"content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False)}]}


def _err(message: str) -> dict:
    return {"isError": True, "content": [{"type": "text", "text": message}]}


TOOLS: dict[str, dict[str, Any]] = {
    "flow_list_workflows": {
        "description": "List saved Flow workflows in a Flow directory.",
        "inputSchema": {
            "type": "object",
            "properties": {"flow_dir": {"type": "string"}},
            "additionalProperties": False,
        },
    },
    "flow_find_workflow": {
        "description": "Resolve a workflow name by exact match first, then fuzzy match.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "flow_dir": {"type": "string"},
            },
            "required": ["name"],
            "additionalProperties": False,
        },
    },
    "flow_auto_trigger": {
        "description": "Rank workflow candidates from user text.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "flow_dir": {"type": "string"},
            },
            "required": ["text"],
            "additionalProperties": False,
        },
    },
    "flow_start_workflow": {
        "description": "Start a workflow session and return the first chat-renderable step.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name_or_text": {"type": "string"},
                "user_input": {"type": "string"},
                "flow_dir": {"type": "string"},
            },
            "required": ["name_or_text"],
            "additionalProperties": False,
        },
    },
    "flow_current_step": {
        "description": "Return the current chat-renderable step for a workflow session.",
        "inputSchema": {
            "type": "object",
            "properties": {"session_id": {"type": "string"}},
            "required": ["session_id"],
            "additionalProperties": False,
        },
    },
    "flow_submit_dialog_response": {
        "description": "Submit the visible Agent/user response for the current dialog step.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "response": {"type": "string"},
            },
            "required": ["session_id", "response"],
            "additionalProperties": False,
        },
    },
    "flow_submit_logic_condition": {
        "description": "Submit TRUE/FALSE for the current logic step and return the next step.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "condition": {"type": "boolean"},
            },
            "required": ["session_id", "condition"],
            "additionalProperties": False,
        },
    },
}


def _tool_call(name: str, args: dict[str, Any]) -> dict:
    d = _flow_dir(args.get("flow_dir"))
    if name == "flow_list_workflows":
        return _ok({"flow_dir": d, "workflows": flow.list_workflows(d)})
    if name == "flow_find_workflow":
        found = flow.find_workflow(args["name"], d)
        return _ok({"flow_dir": d, "query": args["name"], "workflow": found})
    if name == "flow_auto_trigger":
        matches = [{"name": n, "score": score} for n, score in flow.auto_trigger(args["text"], d)]
        return _ok({"flow_dir": d, "query": args["text"], "matches": matches})
    if name == "flow_start_workflow":
        query = args["name_or_text"]
        found = flow.find_workflow(query, d)
        if not found:
            matches = flow.auto_trigger(query, d)
            found = matches[0][0] if matches else None
        if not found:
            return _err(f"No Flow workflow matched: {query}")
        session_id = str(uuid.uuid4())
        bridge = FlowDialogBridge(found, d, args.get("user_input"))
        SESSIONS[session_id] = bridge
        step = bridge.start()
        return _ok({"session_id": session_id, "workflow": found, "step": render_chat_step(step)})
    if name == "flow_current_step":
        bridge = SESSIONS.get(args["session_id"])
        if not bridge:
            return _err("Unknown Flow session_id.")
        return _ok({"session_id": args["session_id"], "step": bridge.current_chat_step()})
    if name == "flow_submit_dialog_response":
        bridge = SESSIONS.get(args["session_id"])
        if not bridge:
            return _err("Unknown Flow session_id.")
        step = bridge.submit_response(args["response"])
        return _ok({"session_id": args["session_id"], "step": render_chat_step(step)})
    if name == "flow_submit_logic_condition":
        bridge = SESSIONS.get(args["session_id"])
        if not bridge:
            return _err("Unknown Flow session_id.")
        step = bridge.submit_condition(bool(args["condition"]))
        return _ok({"session_id": args["session_id"], "step": render_chat_step(step)})
    return _err(f"Unknown tool: {name}")


def _handle(request: dict[str, Any]) -> dict[str, Any] | None:
    rid = request.get("id")
    method = request.get("method")
    try:
        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": rid,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "flow-workflow", "version": "1.1.0"},
                },
            }
        if method == "notifications/initialized":
            return None
        if method == "tools/list":
            tools = [{"name": k, **v} for k, v in TOOLS.items()]
            return {"jsonrpc": "2.0", "id": rid, "result": {"tools": tools}}
        if method == "tools/call":
            params = request.get("params") or {}
            result = _tool_call(params.get("name"), params.get("arguments") or {})
            return {"jsonrpc": "2.0", "id": rid, "result": result}
        return {
            "jsonrpc": "2.0",
            "id": rid,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }
    except Exception as exc:
        return {
            "jsonrpc": "2.0",
            "id": rid,
            "error": {"code": -32000, "message": str(exc), "data": traceback.format_exc()},
        }


def main() -> int:
    for line in sys.stdin:
        if not line.strip():
            continue
        response = _handle(json.loads(line))
        if response is not None:
            print(json.dumps(response, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

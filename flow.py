#!/usr/bin/env python3
"""Flow Workflow CLI — load, validate, list, edit, and run .Flow.json workflows."""

import argparse
import json
import os
import sys
import webbrowser
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler


# ─── Data Models ──────────────────────────────────────────────────────────────

class FlowComponent:
    def __init__(self, data: dict):
        self.type: str = data.get("type", "")
        self.id: int = data.get("id", 0)
        self.prompt: str = data.get("prompt", "")

class FlowDialogComponent(FlowComponent):
    def __init__(self, data: dict):
        super().__init__(data)
        self.mode: str = data.get("mode", "Build")

class FlowLogicComponent(FlowComponent):
    def __init__(self, data: dict):
        super().__init__(data)
        self.goto_true: int = data.get("goto_true", 0)
        self.goto_false: int = data.get("goto_false", 0)

class FlowWorkflow:
    def __init__(self, name: str, components: list | None = None):
        self.name = name
        self.components: list[FlowComponent] = components or []

    def to_dict(self) -> dict:
        comps = []
        for c in sorted(self.components, key=lambda x: x.id):
            if isinstance(c, FlowDialogComponent):
                comps.append({"type": "dialog", "id": c.id, "mode": c.mode, "prompt": c.prompt})
            elif isinstance(c, FlowLogicComponent):
                comps.append({"type": "logic", "id": c.id, "prompt": c.prompt, "goto_true": c.goto_true, "goto_false": c.goto_false})
        return {"name": self.name, "components": comps}


# ─── Loader ───────────────────────────────────────────────────────────────────

_SCRIPT_DIR = Path(__file__).parent.resolve()
_SKILL_FLOW_DIR = str(_SCRIPT_DIR / "Flow")

# Default: use skill's Flow/ dir (alongside SKILL.md). Fallback: local "Flow".
# Override with FLOW_DIR env var or --dir flag.
_DEFAULT_FLOW_DIR = _SKILL_FLOW_DIR
if not (_SCRIPT_DIR / "SKILL.md").is_file():
    _DEFAULT_FLOW_DIR = "Flow"

WORKFLOW_DIR = os.environ.get("FLOW_DIR", _DEFAULT_FLOW_DIR)

def resolve_dir(d: str | None = None) -> str:
    return d or WORKFLOW_DIR

def list_workflows(flow_dir: str) -> list[str]:
    p = Path(flow_dir)
    if not p.is_dir():
        return []
    return sorted({f.stem.replace(".Flow", "") for f in p.glob("*.Flow.json")})

def load_workflow(name: str, flow_dir: str) -> FlowWorkflow | None:
    path = Path(flow_dir) / f"{name}.Flow.json"
    if not path.is_file():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        wf = FlowWorkflow(name)
        for c in data.get("components", []):
            t = c.get("type", "")
            if t == "dialog":
                wf.components.append(FlowDialogComponent(c))
            elif t == "logic":
                wf.components.append(FlowLogicComponent(c))
        return wf
    except (json.JSONDecodeError, KeyError, OSError):
        return None

def save_workflow(wf: FlowWorkflow, flow_dir: str) -> bool:
    try:
        path = Path(flow_dir) / f"{wf.name}.Flow.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(wf.to_dict(), f, indent=2)
        return True
    except OSError:
        return False

def delete_workflow(name: str, flow_dir: str) -> bool:
    path = Path(flow_dir) / f"{name}.Flow.json"
    if path.is_file():
        path.unlink()
        return True
    return False


# ─── Static Cycle Detection ───────────────────────────────────────────────────

def detect_cycles_static(wf: FlowWorkflow) -> list[list[int]]:
    """Analyze workflow graph for potential infinite loops.
    
    Builds a directed graph where:
      - dialog component → next sequential component (id+1)
      - logic component → goto_true AND goto_false
    
    Uses DFS to find all cycles. Returns list of cycles, each as [id, ..., id].
    A cycle means the workflow can re-enter a previously visited component,
    potentially causing an infinite loop.
    """
    comps = sorted(wf.components, key=lambda c: c.id)
    if not comps:
        return []

    id_to_idx = {c.id: i for i, c in enumerate(comps)}
    graph = {c.id: [] for c in comps}

    for c in comps:
        if isinstance(c, FlowDialogComponent):
            nxt = c.id + 1
            if nxt in id_to_idx:
                graph[c.id].append(nxt)
        elif isinstance(c, FlowLogicComponent):
            if c.goto_true in id_to_idx:
                graph[c.id].append(c.goto_true)
            if c.goto_false in id_to_idx:
                graph[c.id].append(c.goto_false)

    WHITE, GRAY, BLACK = 0, 1, 2
    color = {c.id: WHITE for c in comps}
    cycles: list[list[int]] = []
    path: list[int] = []

    def dfs(node: int):
        color[node] = GRAY
        path.append(node)
        for nb in graph.get(node, []):
            if nb not in color:
                continue
            if color[nb] == GRAY:
                start = path.index(nb)
                cycles.append(path[start:])
            elif color[nb] == WHITE:
                dfs(nb)
        path.pop()
        color[node] = BLACK

    for c in comps:
        if color[c.id] == WHITE:
            dfs(c.id)

    # Deduplicate cycles (same set of edges, different entry points)
    unique: list[list[int]] = []
    seen = set()
    for cyc in cycles:
        normalized = tuple(sorted(cyc))
        if normalized not in seen:
            seen.add(normalized)
            unique.append(cyc)
    return unique


def warn_cycles(wf: FlowWorkflow) -> list[str]:
    """Return human-readable cycle warnings for a workflow."""
    cycles = detect_cycles_static(wf)
    if not cycles:
        return []
    warnings = []
    for cyc in cycles:
        involved = ", ".join(str(cid) for cid in cyc)
        warnings.append(
            f"[!] Potential logic cycle detected in '{wf.name}': "
            f"components [{involved}] can form a loop. "
            f"This may cause infinite execution if all logic conditions "
            f"consistently evaluate the same way."
        )
    return warnings


# ─── Validation ───────────────────────────────────────────────────────────────

def validate_workflow(name: str, flow_dir: str) -> list[str]:
    errors = []
    wf = load_workflow(name, flow_dir)
    if wf is None:
        return [f"Workflow '{name}' not found or invalid JSON."]
    if not wf.components:
        errors.append("No components defined.")
        return errors
    ids = {c.id for c in wf.components}
    if len(ids) != len(wf.components):
        seen = set()
        for c in wf.components:
            if c.id in seen:
                errors.append(f"Duplicate component ID: {c.id}")
            seen.add(c.id)
    for c in wf.components:
        if c.type == "dialog":
            if c.mode not in ("Build", "Plan", "Goal"):
                errors.append(f"Component {c.id}: invalid mode '{c.mode}' (must be Build/Plan/Goal)")
        elif c.type == "logic":
            lc = c
            if lc.goto_true not in ids:
                errors.append(f"Component {c.id}: goto_true={lc.goto_true} not found")
            if lc.goto_false not in ids:
                errors.append(f"Component {c.id}: goto_false={lc.goto_false} not found")
        else:
            errors.append(f"Component {c.id}: unknown type '{c.type}'")
    if wf.components[0].id != 0:
        errors.append(f"First component should ideally be ID 0 (found {wf.components[0].id})")
    return errors


# ─── Natural Language Description ──────────────────────────────────────────────

def _short_label(prompt: str, n: int = 28) -> str:
    s = prompt.replace("{#prompt#}", "<i>").replace("\n", " ").strip()
    return (s[:n] + "..") if len(s) > n else s

def describe_workflow(name: str, flow_dir: str) -> str | None:
    wf = load_workflow(name, flow_dir)
    if wf is None:
        return None
    comps = sorted(wf.components, key=lambda c: c.id)
    if not comps:
        return ""
    parts = []
    for c in comps:
        if isinstance(c, FlowDialogComponent):
            parts.append(c.mode)
        elif isinstance(c, FlowLogicComponent):
            parts.append(f"?{_short_label(c.prompt, 22)}?")
    return " → ".join(parts)

# ─── Runner (execution engine) ────────────────────────────────────────────────

# ─── Fuzzy Matching & Auto-Trigger ─────────────────────────────────────────────

def find_workflow(name: str, flow_dir: str) -> str | None:
    """Exact-match first, else fuzzy (case-insensitive contains). Returns canonical name or None."""
    names = list_workflows(flow_dir)
    if not names:
        return None
    if name in names:
        return name
    name_lower = name.lower()
    for n in names:
        if n.lower() == name_lower:
            return n
    for n in names:
        if name_lower in n.lower():
            return n
    return None

def auto_trigger(text: str, flow_dir: str) -> list[tuple[str, float]]:
    """Scan `text` for workflow names. Returns list of (name, score) sorted by score descending.
    Score: exact match = 1.0, fuzzy match = 0.5-0.9 based on overlap ratio."""
    import re
    names = list_workflows(flow_dir)
    text_lower = text.lower()
    results = []
    for n in names:
        n_lower = n.lower()
        if n_lower == text_lower:
            results.append((n, 1.0))
        elif n_lower in text_lower:
            ratio = len(n_lower) / max(len(text_lower), 1)
            results.append((n, 0.5 + 0.4 * min(ratio, 1.0)))
        else:
            words = re.split(r'[\s_\-]+', n_lower)
            match_count = sum(1 for w in words if w and w in text_lower)
            if match_count > 0:
                ratio = match_count / max(len(words), 1)
                score = 0.2 + 0.6 * ratio  # range 0.2-0.8
                results.append((n, score))
    results.sort(key=lambda x: -x[1])
    return results


# ─── Dialog Trigger (following goal-plugin CLI pattern) ─────────────────────

import abc


class StepHandler(abc.ABC):
    """Pluggable handler for workflow dialog/logic steps.
    
    Universal interface supporting all agent calling patterns:
      - Generator (yield/send for agent frameworks)
      - CLI (stdin/stdout for terminal)
      - MCP (JSON-RPC tools for OpenCode/Codex/Harness)
    
    Usage in run_workflow():
        handler = CLIStepHandler()
        run_workflow("deploy", "Flow/", handler=handler)
    """

    @abc.abstractmethod
    def on_dialog(self, step_id: int, mode: str, prompt: str) -> str:
        """Handle a dialog step. Returns free-text response string."""
        ...

    @abc.abstractmethod
    def on_logic(self, step_id: int, prompt: str) -> bool:
        """Handle a logic condition. Returns True (condition met) or False."""
        ...

    def on_goal_verify(self, goal_prompt: str, work_done: str) -> bool:
        """Verify whether a goal was achieved. Default reuses on_logic."""
        check = f"Is the following goal achieved?\nGoal: {goal_prompt[:200]}\nCompleted: {work_done[:200]}"
        return self.on_logic(-1, check)

    def on_complete(self, message: str = "Workflow complete."):
        """Called when workflow finishes successfully."""
        pass

    def on_error(self, step_id: int, message: str):
        """Called when a workflow error occurs."""
        pass


class GeneratorStepHandler(StepHandler):
    """Step handler using yield/send generator protocol.
    
    For agent frameworks that can drive execution via generator iteration.
    Yields step dicts, receives responses via .send().
    
    Usage:
        handler = GeneratorStepHandler()
        gen = handler.run(workflow_name, flow_dir, user_input)
        for step in gen:
            if step["type"] == "dialog":
                gen.send(handler.on_dialog(...))
    """

    def __init__(self):
        self._generator = None
        self._current_step = None
        self._responses: list[tuple[str, str]] = []

    def on_dialog(self, step_id: int, mode: str, prompt: str) -> str:
        print(f"\n[Generator {step_id}] Mode: {mode}")
        print(f"  Prompt: {prompt[:80]}...")
        resp = input(f"  Response ({step_id}): ")
        return resp

    def on_logic(self, step_id: int, prompt: str) -> bool:
        while True:
            ans = input(f"  Logic [{step_id}]: {prompt[:60]}... (T/F): ").strip().upper()
            if ans in ("T", "TRUE"):
                return True
            elif ans in ("F", "FALSE"):
                return False

    def run(self, name: str, flow_dir: str, user_input: str | None = None):
        """Run the workflow and yield steps for agent consumption."""
        from flow import run_workflow_iter
        return run_workflow_iter(name, flow_dir, user_input)


class CLIStepHandler(StepHandler):
    """Step handler using stdin/stdout (terminal).
    
    The default handler for CLI usage. Prints prompts and reads responses
    via input() with ---done--- terminator for multi-line input.
    Follows the same pattern as OpenCode_goal_plugin's CLI interface.
    """

    def __init__(self, llm_eval=None):
        self._llm_eval = llm_eval

    def on_dialog(self, step_id: int, mode: str, prompt: str) -> str:
        print(f"\n{'='*60}")
        print(f"[Component {step_id}] Mode: {mode}")
        print(f"{'='*60}")
        print(prompt)
        print(f"{'─'*60}")
        if self._llm_eval:
            print("[Flow] Auto mode: prompt printed — simulated run")
            return ""
        print("[Flow] Enter response (end with '---done---' on its own line):")
        resp_lines = []
        while True:
            try:
                line = input()
            except EOFError:
                break
            if line.strip() == "---done---":
                break
            resp_lines.append(line)
        response = "\n".join(resp_lines).strip()
        print(f"{'='*60}")
        print(f"[Response {step_id}] {response[:120]}{'...' if len(response) > 120 else ''}")
        return response

    def on_logic(self, step_id: int, prompt: str) -> bool:
        print(f"\n>>> Logic [{step_id}] Evaluating: {prompt} >>>")
        if self._llm_eval:
            eval_prompt = f"In the current workspace, is the following condition already implemented?\nCondition: {prompt}\nAnswer only TRUE or FALSE."
            return self._llm_eval(eval_prompt)
        while True:
            ans = input("  Condition TRUE or FALSE? (T/F): ").strip().upper()
            if ans in ("T", "TRUE"):
                return True
            elif ans in ("F", "FALSE"):
                return False

    def on_goal_verify(self, goal_prompt: str, work_done: str) -> bool:
        check = f"Is the following goal achieved?\nGoal: {goal_prompt[:200]}\nCompleted: {work_done[:200]}"
        print(f"\n>>> Goal verification: {check} >>>")
        if self._llm_eval:
            return self._llm_eval(check)
        while True:
            ans = input("  Goal achieved? (Y/N): ").strip().upper()
            if ans in ("Y", "YES"):
                return True
            elif ans in ("N", "NO"):
                return False


class MCPToolHandler(StepHandler):
    """Step handler via MCP (Model Context Protocol) tools.
    
    For OpenCode, Claude Code, Codex, and other MCP-compatible agents.
    Exposes workflow steps as MCP tool calls: the agent triggers a tool,
    the handler returns the result, and the engine advances.
    """

    def __init__(self, tool_callback=None):
        self._callback = tool_callback
        self._dialog_buffer: list[dict] = []

    def on_dialog(self, step_id: int, mode: str, prompt: str) -> str:
        if self._callback:
            return self._callback("dialog", {"id": step_id, "mode": mode, "prompt": prompt})
        self._dialog_buffer.append({"id": step_id, "mode": mode, "prompt": prompt})
        return ""

    def on_logic(self, step_id: int, prompt: str) -> bool:
        if self._callback:
            result = self._callback("logic", {"id": step_id, "prompt": prompt})
            return bool(result)
        return True

    def get_pending_dialogs(self) -> list[dict]:
        """Return buffered dialog prompts for agent to process."""
        pending = list(self._dialog_buffer)
        self._dialog_buffer.clear()
        return pending


class DialogTrigger:
    """[DEPRECATED] Use CLIStepHandler directly.
    
    Response-gathering mechanism for dialog components.
    Follows the same detect→fallback pattern as OpenCode_goal_plugin.
    """

    def __init__(self, generator=None):
        self._generator = generator
        self._handler = CLIStepHandler()

    def get(self, prompt: str, mode: str = "Build") -> str:
        if self._generator is not None:
            import warnings
            warnings.warn("Direct DialogTrigger.get() in generator mode — use yield protocol instead.")
            return ""
        return self._handler.on_dialog(0, mode, prompt)

    def verify_goal(self, goal_prompt: str, completed_work: str, llm_eval=None) -> bool:
        h = CLIStepHandler(llm_eval)
        return h.on_goal_verify(goal_prompt, completed_work)


# ─── Plan Mode Prompt Wrapping ────────────────────────────────────────────────


# ─── Plan Mode Prompt Wrapping ────────────────────────────────────────────────

def _build_dialog_prompt(component: FlowDialogComponent, user_input: str | None) -> str:
    """Build the final prompt for a dialog component.
    
    For Plan mode: wraps user input into a plan-oriented instruction,
    stripping redundant planning language from the base prompt when user
    input is provided.
    
    Convention:
      - Plan mode: the base prompt SHOULD contain {#prompt#} as the user
        input insertion point. Example base prompt:
          "听从以下指令设置计划：{#prompt#}"
        With user input "整理工作区" → final prompt:
          "听从以下指令计划：整理工作区"
    """
    raw = component.prompt
    ui = user_input or ""
    if component.mode == "Plan" and ui:
        if "{#prompt#}" in raw:
            result = raw.replace("{#prompt#}", ui)
            # Plan mode convention: strip "设置" before "计划" for Chinese prompts.
            # The agent already knows this is a planning instruction, so
            # "设置计划" (establish/set plan) is redundant →  "计划" (plan).
            result = result.replace("设置计划", "计划")
            return result
        else:
            return f"Plan: {raw}\nUser context: {ui}"
    return raw.replace("{#prompt#}", ui)


def run_workflow(name: str, flow_dir: str, user_input: str | None = None,
                 llm_eval=None, handler: StepHandler | None = None) -> None:
    """Execute a workflow.
    
    Args:
        name: Workflow name (fuzzy-matched)
        flow_dir: Flow/ directory path
        user_input: Text for {#prompt#} substitution
        llm_eval: Callable for auto-evaluating logic conditions (deprecated, use handler instead)
        handler: A StepHandler instance (CLIStepHandler, MCPToolHandler, etc.)
                 Defaults to CLIStepHandler with optional llm_eval.
    """
    wf = load_workflow(name, flow_dir)
    if wf is None:
        print(f"[Flow] Workflow '{name}' not found.", file=sys.stderr)
        sys.exit(1)

    if handler is None:
        handler = CLIStepHandler(llm_eval)

    # Pre-flight: warn about potential cycles before first execution
    cycle_warnings = warn_cycles(wf)
    if cycle_warnings:
        print(f"  [!] '{name}' has {len(cycle_warnings)} potential cycle(s):")
        for w in cycle_warnings:
            print(f"    {w}")
        if llm_eval is not None:
            print("  (auto mode: --true/--false, continuing)")
        else:
            ans = input("  Continue execution? (y/N): ").strip().lower()
            if ans not in ("y", "yes"):
                print("[Flow] Execution cancelled by user.")
                return

    components = sorted(wf.components, key=lambda c: c.id)
    idx = 0
    responses: dict[int, str] = {}
    visit_counts: dict[int, int] = {}
    MAX_VISITS = 300

    while 0 <= idx < len(components):
        c = components[idx]
        cid = c.id

        visit_counts[cid] = visit_counts.get(cid, 0) + 1
        if visit_counts[cid] > MAX_VISITS:
            print(f"\n[Flow] Cycle detected: component {c.id} visited {visit_counts[cid]} times, stopping.")
            handler.on_error(cid, f"Cycle detected at component {cid}")
            break

        if isinstance(c, FlowDialogComponent):
            prompt = _build_dialog_prompt(c, user_input)
            response = handler.on_dialog(cid, c.mode, prompt)
            responses[cid] = response
            if c.mode == "Goal":
                achieved = handler.on_goal_verify(c.prompt, response)
                if achieved:
                    print(f"  -> Goal achieved, advancing.")
                    idx += 1
                else:
                    print(f"  -> Goal NOT achieved, re-executing component {cid}.")
                    continue
            else:
                idx += 1

        elif isinstance(c, FlowLogicComponent):
            prompt = c.prompt.replace("{#prompt#}", user_input or "")
            result = handler.on_logic(cid, prompt)
            if result:
                print(f"  -> TRUE, goto component {c.goto_true}")
                new_idx = next((i for i, x in enumerate(components) if x.id == c.goto_true), -1)
            else:
                print(f"  -> FALSE, goto component {c.goto_false}")
                new_idx = next((i for i, x in enumerate(components) if x.id == c.goto_false), -1)

            if new_idx < 0:
                print(f"  [Flow] Goto target not found, stopping.")
                break
            idx = new_idx

    print("\n[Flow] Workflow complete.")


# ─── Step-based Generator (Agent Integration) ───────────────────────────────

def run_workflow_iter(name: str, flow_dir: str, user_input: str | None = None):
    """Generator that yields workflow steps one at a time for agent-based execution.

    Allows an agent loop to drive flow execution by yielding each component
    as a step dict and receiving responses via ``.send()``.

    Yields (dialog component — Plan/Build mode):
        ``{"type": "dialog", "id": int, "mode": str, "prompt": str}``
    Expects via ``.send()``:
        ``{"type": "dialog_response", "response": str}``

    Yields (dialog component — Goal mode): TWO consecutive steps
        1. ``{"type": "dialog", "id": int, "mode": "Goal", "prompt": str}``
           → send ``dialog_response``
        2. ``{"type": "logic", "id": ..., "prompt": "<achievement check>"}``
           → send ``logic_response`` with condition=True (achieved) or False (loop back)

    Yields (logic component):
        ``{"type": "logic", "id": int, "prompt": str, "goto_true": int, "goto_false": int}``
    Expects via ``.send()``:
        ``{"type": "logic_response", "condition": bool}``

    Yields (complete signal):
        ``{"type": "complete", "message": "Workflow complete."}``

    Raises ``StopIteration`` after completion or error.

    Usage in an agent loop::

        wf_iter = run_workflow_iter("my_flow", "Flow/", user_input="...")
        try:
            step = next(wf_iter)
            while step["type"] != "complete":
                if step["type"] == "dialog":
                    # Present prompt in agent conversation
                    response = agent_input(f"[{step['mode']}] {step['prompt']}")
                    step = wf_iter.send({"type": "dialog_response", "response": response})
                elif step["type"] == "logic":
                    condition = llm_eval(step["prompt"])
                    step = wf_iter.send({"type": "logic_response", "condition": condition})
        except StopIteration:
            pass
    """
    wf = load_workflow(name, flow_dir)
    if wf is None:
        yield {"type": "error", "message": f"Workflow '{name}' not found."}
        return

    cycle_warnings = warn_cycles(wf)
    if cycle_warnings:
        yield {"type": "cycle_warning", "warnings": cycle_warnings, "workflow": name}

    components = sorted(wf.components, key=lambda c: c.id)
    idx = 0
    visit_counts: dict[int, int] = {}
    MAX_VISITS = 300

    while 0 <= idx < len(components):
        c = components[idx]
        cid = c.id

        visit_counts[cid] = visit_counts.get(cid, 0) + 1
        if visit_counts[cid] > MAX_VISITS:
            yield {"type": "error", "message": f"Cycle detected: component {cid} visited {visit_counts[cid]} times."}
            return

        if isinstance(c, FlowDialogComponent):
            prompt = _build_dialog_prompt(c, user_input)
            step = {"type": "dialog", "id": cid, "mode": c.mode, "prompt": prompt}
            response = yield step
            if response is None:
                response = {"type": "dialog_response", "response": ""}
            if c.mode == "Goal":
                resp_text = response.get("response", "") if isinstance(response, dict) else ""
                check_prompt = f"Is component {cid}'s goal achieved?\nGoal: {c.prompt[:200]}\nCompleted: {resp_text[:200]}"
                step_verify = {"type": "logic", "id": cid + 10000, "prompt": check_prompt, "goto_true": cid + 1, "goto_false": cid}
                result = yield step_verify
                condition = result.get("condition", False) if isinstance(result, dict) else False
                if condition:
                    idx += 1
            else:
                idx += 1

        elif isinstance(c, FlowLogicComponent):
            prompt = c.prompt.replace("{#prompt#}", user_input or "")
            step = {"type": "logic", "id": cid, "prompt": prompt, "goto_true": c.goto_true, "goto_false": c.goto_false}
            result = yield step
            condition = result.get("condition", False) if isinstance(result, dict) else False

            if condition:
                new_idx = next((i for i, x in enumerate(components) if x.id == c.goto_true), -1)
            else:
                new_idx = next((i for i, x in enumerate(components) if x.id == c.goto_false), -1)

            if new_idx < 0:
                yield {"type": "error", "message": f"Goto target not found at component {cid}."}
                return
            idx = new_idx

    yield {"type": "complete", "message": "Workflow complete."}


# ─── Gen (prompt → workflow generation) ─────────────────────────────────────
# Built on Harness CI/CD pipeline principles:
#   Pipeline → Stages (Plan/Build/Deploy/Verify) → Steps (dialog/logic)
#   + Conditional execution, failure strategies, approval gates

_PIPELINE_PATTERNS = {
    "ci":     {"keywords": ["build", "test", "ci", "compile", "lint", "unit test", "integration test", "artifact"]},
    "cd":     {"keywords": ["deploy", "release", "rollout", "canary", "blue-green", "production", "staging"]},
    "feature": {"keywords": ["feature", "implement", "story", "ticket", "pr", "pull request", "branch"]},
    "research": {"keywords": ["research", "derive", "prove", "theorem", "literature", "paper", "theory"]},
    "review":  {"keywords": ["review", "audit", "inspect", "approve", "sign-off"]},
}


def _gen_detect_pipeline_type(text: str) -> str:
    """Detect the pipeline type from description keywords."""
    tl = text.lower()
    scores = {}
    for ptype, cfg in _PIPELINE_PATTERNS.items():
        scores[ptype] = sum(1 for kw in cfg["keywords"] if kw in tl)
    if max(scores.values()) == 0:
        return "general"
    return max(scores, key=scores.get)


def _gen_pipeline_header(ptype: str) -> str:
    """Return a stage label and prompt header for the pipeline type."""
    headers = {
        "ci":       ("CI Pipeline", "CI pipeline: clone, build, test, and publish artifacts."),
        "cd":       ("CD Pipeline", "CD pipeline: deploy through environments with approval gates."),
        "feature":  ("Feature Pipeline", "Feature branch: plan, implement, test, and submit."),
        "research": ("Research Pipeline", "Research workflow: literature, derive, verify, and publish."),
        "review":   ("Review Pipeline", "Review pipeline: inspect, approve, and merge."),
    }
    return headers.get(ptype, headers["feature"])


def _gen_detect_stages(text: str, steps: list[tuple[str, bool]]) -> list[list[int]]:
    """Group step indices into stages based on transitions and keywords.
    
    Each stage is a list of step indices. A new stage starts when:
    - A step mentions a phase keyword ("deploy", "review", "publish", "verify")
    - Consecutive logic/action pairs form a natural group
    - More than 4 steps exist (split into stages of 2-4)
    """
    t = text.lower()
    stage_breaks = []
    
    # Phase transition keywords signal new stages
    phase_keywords = [
        r'\bdeploy\b', r'\breview\b', r'\bpublish\b', r'\brelease\b',
        r'\bverify\b', r'\bapprove\b', r'\bstage\b', r'\bphase\b',
        r'\bround\b', r'\bfinalize\b',
    ]
    
    for i, (step_text, _) in enumerate(steps):
        st = step_text.lower()
        for kw in phase_keywords:
            import re
            if re.search(kw, st):
                if i > 0 and i not in stage_breaks:
                    stage_breaks.append(i)
                break
    
    if not stage_breaks and len(steps) > 4:
        # Auto-split into stages of 2-4 steps
        mid = len(steps) // 2
        stage_breaks.append(mid)
    
    # Build stage groups
    groups = []
    start = 0
    for brk in sorted(stage_breaks):
        if brk > start:
            groups.append(list(range(start, brk)))
            start = brk
    if start < len(steps):
        groups.append(list(range(start, len(steps))))
    
    return groups if groups else [list(range(len(steps)))]


def _gen_name_from_text(text: str) -> str:
    """Generate a kebab-case workflow name from the first meaningful words."""
    import re
    cleaned = re.sub(r'\{#prompt#\}', '', text).strip()
    cleaned = re.sub(r'[^a-zA-Z0-9\u4e00-\u9fff\s_-]', '', cleaned)
    sep_parts = re.split(r'[\s,;.]+', cleaned)
    stopwords = {"the", "a", "an", "to", "of", "in", "for", "and", "or", "is", "it",
                 "then", "after", "finally", "next", "with", "by", "at", "on"}
    meaningful = [p.lower() for p in sep_parts if p.lower() not in stopwords and len(p) > 1]
    if not meaningful:
        return "generated_workflow"
    name = "-".join(meaningful[:4])
    name = re.sub(r'[-]+', '-', name.strip('-'))
    return name[:50] or "generated_workflow"


def _gen_split_steps(text: str) -> list[str]:
    """Split a description into individual step descriptions."""
    import re
    separators = [
        r',\s*and\s+', r'\s+and\s+then\s+', r'\s+then\s+',
        r'\s+after\s+that\s*', r'\s+finally\s+', r'\s+next\s*,\s*',
        r'\s+after\s+which\s*', r'\s+afterwards\s*', r'\s+subsequently\s*',
        r'\.\s+',
    ]
    pattern = '|'.join(separators)
    raw = re.split(pattern, text)
    steps = [s.strip().rstrip('.') for s in raw if s.strip()]
    return steps if len(steps) > 1 else [text]


def _gen_is_condition(step: str) -> bool:
    """Detect if a step describes a logic condition (check/verify/confirm).

    Harness-inspired patterns:
      - Conditional execution: "only if", "when X fails", "skip when"
      - Approval gates: "needs approval", "requires sign-off"
      - Failure strategies: "on failure", "rollback if", "if broken"
    """
    import re
    s = step.strip().lower()

    # Action verbs override everything
    action_verbs = [
        r'^implement', r'^create\b', r'^write\b', r'^build\b', r'^add\b',
        r'^read\b', r'^explore\b', r'^update\b', r'^refactor\b', r'^fix\b',
        r'^test\b', r'^deploy\b', r'^set\s+up', r'^configure\b', r'^run\b',
        r'^make\b', r'^generate\b', r'^delete\b', r'^remove\b', r'^rename\b',
        r'^move\b', r'^copy\b', r'^setup\b', r'^init\b', r'^prepare\b',
        r'^review\b', r'^analyze\b', r'^document\b', r'^research\b', r'^find\b',
        r'^compile\b', r'^publish\b', r'^release\b', r'^rollout\b',
    ]
    for pat in action_verbs:
        if re.search(pat, s):
            return False

    # Ends with question mark
    if s.rstrip('?.!').endswith('?'):
        return True

    # Short pure-check phrases
    short_check = r'^(check|verify|validate|confirm|ensure)\s'
    if re.search(short_check, s) and len(s.split()) <= 8:
        return True

    # Conditional execution patterns (Harness-inspired)
    conditional_patterns = [
        r'\bonly\s+if\b', r'\bwhen\s+\w+\s+(fails|passes|succeeds|completes)\b',
        r'\bskip\s+(when|if)\b', r'\bfail\s+if\b',
        r'\brollback\s+(if|when)\b', r'\bif\s+\w+\s+(fails|breaks)\b',
    ]
    for pat in conditional_patterns:
        if re.search(pat, s):
            return True

    # Contains condition keywords
    logic_triggers = [
        r'\bcheck\s+if\b', r'\bverify\s+(that\s+)?', r'\bvalidate\b', r'\bconfirm\b',
        r'\bensure\b', r'\bis\s+it\b', r'\bare\s+there\b', r'\bdoes\s+it\b',
        r'\bwhether\b', r'\bimplemented\?', r'\bready\?', r'\bcomplete\?',
        r'\bexists\?', r'\bpassing\?',
        r'\bis\s+\w+\s+(ready|done|complete|implemented|deployed)',
        r'\bare\s+\w+\s+(ready|done|complete|implemented|deployed)',
        r'\bapprove\b', r'\bapproval\b', r'\bsign.?off\b',
        r'\bgate\b', r'\bquality.?gate\b',
    ]
    for pat in logic_triggers:
        if re.search(pat, s):
            return True

    return False


def _gen_build_stage_header(stage_idx: int, ptype: str, step_count: int) -> str:
    """Build a stage label prompt that sets context for the steps within."""
    stage_names = {
        "ci":       ["Plan & Setup", "Build & Compile", "Test & Verify", "Package & Publish"],
        "cd":       ["Plan Release", "Deploy to Staging", "Verify & Approve", "Production Rollout"],
        "feature":  ["Plan & Design", "Implementation", "Test & Review", "Merge & Close"],
        "research": ["Foundations & Lit Review", "Core Derivation", "Verification & Classification", "Paper & Review"],
    }
    names = stage_names.get(ptype, ["Phase 1", "Phase 2", "Phase 3", "Phase 4"])
    name = names[stage_idx] if stage_idx < len(names) else f"Phase {stage_idx + 1}"
    return f"[Stage: {name}]"


def cmd_gen(args):
    """Generate a workflow from a natural language description.
    
    Built on Harness CI/CD pipeline principles:
      - Pipeline → Stages → Steps with conditional execution
      - Failure recovery logic between steps
      - Approval gates between stages
      - Stage context enriches individual step prompts
    
    Examples:
      flow gen "build then test then deploy"
      flow gen "implement feature then verify tests pass then create pr"
      flow gen "derive theorem then prove lemmas then write paper" --name research-paper
      flow gen "clone build test publish" --name ci-pipeline --force
    """
    d = resolve_dir(args.dir)
    text = args.text

    if not text:
        print("[Flow] No description provided.", file=sys.stderr)
        sys.exit(1)

    name = args.name or _gen_name_from_text(text)
    
    existing = load_workflow(name, d)
    if existing is not None and not args.force:
        print(f"Workflow '{name}' already exists. Use --force to overwrite.", file=sys.stderr)
        sys.exit(1)

    is_template = "{#prompt#}" in text
    ptype = _gen_detect_pipeline_type(text)
    stage_label, pipeline_desc = _gen_pipeline_header(ptype)
    
    raw_steps = _gen_split_steps(text)
    
    # Classify each step
    classified = []
    for s in raw_steps:
        ss = s.strip()
        if ss:
            classified.append((ss, _gen_is_condition(ss)))

    if not classified:
        print("[Flow] Could not parse description into steps.", file=sys.stderr)
        sys.exit(1)

    # Group steps into stages
    stage_groups = _gen_detect_stages(text, classified)

    comps = []
    inserted_stage_labels = set()
    last_action_cid = None  # track across stages for condition→action back-links

    for stage_idx, step_indices in enumerate(stage_groups):
        
        for pos_in_stage, step_idx in enumerate(step_indices):
            step_text, is_cond = classified[step_idx]
            stage_header = _gen_build_stage_header(stage_idx, ptype, len(step_indices))
            
            # Insert a stage label dialog before the first step of each stage
            if pos_in_stage == 0:
                label_key = f"stage_{stage_idx}"
                if label_key not in inserted_stage_labels:
                    inserted_stage_labels.add(label_key)
                    cid = len(comps)
                    comps.append({
                        "type": "dialog",
                        "id": cid,
                        "mode": "Plan" if stage_idx == 0 else "Plan",
                        "prompt": f"{stage_header} {pipeline_desc} Context: prepare for the steps in this stage."
                    })
                else:
                    cid = len(comps)
                    comps.append({
                        "type": "dialog",
                        "id": cid,
                        "mode": "Plan",
                        "prompt": f"{stage_header} Transition to next phase."
                    })

            if is_cond:
                cid = len(comps)
                # Smart goto: if this condition follows an action in the classified list,
                # it's verifying that action → FALSE goes back to redo it
                if step_idx > 0 and not classified[step_idx - 1][1]:
                    # Condition verifies the previous action → FALSE back to action
                    goto_false = last_action_cid if last_action_cid is not None else cid + 1
                    goto_true = cid + 1  # TRUE → skip past the verification to next normal step
                else:
                    # Condition checks if next step is needed → FALSE to next comp, TRUE skip
                    goto_false = cid + 1
                    goto_true = goto_false + 1
                comps.append({
                    "type": "logic",
                    "id": cid,
                    "prompt": step_text,
                    "goto_true": goto_true,
                    "goto_false": goto_false
                })
            else:
                cid = len(comps)
                mode = "Build"
                if stage_idx == 0 and pos_in_stage == 0:
                    mode = "Plan"
                enriched = f"{stage_header} {step_text}"
                comps.append({
                    "type": "dialog",
                    "id": cid,
                    "mode": mode,
                    "prompt": enriched
                })
                last_action_cid = cid

                # Harness-inspired failure check after each Build action
                if mode == "Build" and not is_template:
                    cid = len(comps)
                    comps.append({
                        "type": "logic",
                        "id": cid,
                        "prompt": f"Did the previous step '{step_text[:50]}' complete successfully?",
                        "goto_true": cid + 1,
                        "goto_false": cid - 1  # re-execute on failure
                    })

        # Add approval gate between stages (Harness approval stage pattern)
        if stage_idx < len(stage_groups) - 1:
            cid = len(comps)
            comps.append({
                "type": "logic",
                "id": cid,
                "prompt": f"Manual approval: proceed to next stage?",
                "goto_true": cid + 1,
                "goto_false": cid  # wait at gate until approved
            })

    # Terminal: add a Goal completion if last component isn't already a goal-worthy step
    if comps:
        last = comps[-1]
        if last["type"] != "dialog" or last.get("mode") != "Goal":
            cid = len(comps)
            last_bit = classified[-1][0][:60] if classified else "pipeline"
            comps.append({
                "type": "dialog",
                "id": cid,
                "mode": "Goal",
                "prompt": f"Goal: Pipeline complete. Verify all outputs and finalize. Last step: {last_bit}"
            })

    # Renumber IDs sequentially and fix goto targets
    for i, c in enumerate(comps):
        c["id"] = i

    n_comps = len(comps)
    term_id = n_comps - 1
    for c in reversed(comps):
        if c["type"] == "dialog":
            term_id = c["id"]
            break
    for c in comps:
        if c["type"] == "logic":
            if c["goto_true"] > n_comps - 1:
                c["goto_true"] = term_id
            if c["goto_false"] > n_comps - 1:
                c["goto_false"] = term_id
            # Self-looping approval gate: cap to itself (wait)
            if c["goto_false"] > n_comps - 1:
                c["goto_false"] = c["id"]

    wf = FlowWorkflow(name)
    for c_data in comps:
        t = c_data["type"]
        if t == "dialog":
            wf.components.append(FlowDialogComponent(c_data))
        elif t == "logic":
            wf.components.append(FlowLogicComponent(c_data))

    save_workflow(wf, d)
    
    dc = sum(1 for c in wf.components if c.type == "dialog")
    lc = sum(1 for c in wf.components if c.type == "logic")
    template_tag = " [TEMPLATE]" if is_template else ""
    print(f"Created: {d}/{name}.Flow.json{template_tag}")
    print(f"  Pipeline: {ptype.upper()}  |  Components: {len(wf.components)} ({dc} dialog + {lc} logic)")
    print(f"  Stages: {len(stage_groups)}  |  Description: {describe_workflow(name, d)}")
    if is_template:
        print(f"  Template: uses {'{#prompt#}'} — accepts user input at runtime")

    for c in sorted(wf.components, key=lambda x: x.id):
        if isinstance(c, FlowDialogComponent):
            pr = c.prompt[:70] + "..." if len(c.prompt) > 70 else c.prompt
            print(f"    [{c.id:02d}] DIALOG  mode={c.mode:5s}  {pr}")
        elif isinstance(c, FlowLogicComponent):
            pr = c.prompt[:60] + "..." if len(c.prompt) > 60 else c.prompt
            print(f"    [{c.id:02d}] LOGIC   T->{c.goto_true} F->{c.goto_false}  {pr}")


# ─── Sum (workspace analysis → workflow generation) ─────────────────────────

def cmd_sum(args):
    d = resolve_dir(args.dir)
    wf_name = args.name
    ws_dir = args.workspace or os.getcwd()

    context_parts = []
    git_log = ""
    try:
        import subprocess
        r = subprocess.run(["git", "log", "--oneline", "-20"], capture_output=True, text=True, cwd=ws_dir, timeout=10)
        if r.returncode == 0 and r.stdout.strip():
            git_log = r.stdout.strip()
            context_parts.append(f"Recent git commits:\n{git_log}")
    except Exception:
        pass

    readme_text = ""
    for name in ("README.md", "Readme.md", "readme.md"):
        rp = Path(ws_dir) / name
        if rp.is_file():
            readme_text = rp.read_text(encoding="utf-8", errors="replace")[:2000]
            context_parts.append(f"README excerpt:\n{readme_text[:500]}")
            break

    dir_lines = []
    try:
        root = Path(ws_dir)
        for entry in sorted(root.iterdir()):
            if entry.name.startswith(".git") or entry.name.startswith("__pycache__") or entry.name == ".venv":
                continue
            if entry.is_dir():
                dir_lines.append(f"  {entry.name}/")
                try:
                    subs = sorted(entry.iterdir())[:6]
                    for sub in subs:
                        if not sub.name.startswith("."):
                            dir_lines.append(f"    {sub.name}{'/' if sub.is_dir() else ''}")
                except PermissionError:
                    pass
            else:
                dir_lines.append(f"  {entry.name}")
    except PermissionError:
        pass
    if dir_lines:
        context_parts.append("Directory structure:\n" + "\n".join(dir_lines[:40]))

    existing = list_workflows(d)
    if existing:
        flow_lines = []
        for n in existing:
            desc = describe_workflow(n, d)
            flow_lines.append(f"  {n}: {desc or '?'}")
        context_parts.append("Existing workflows:\n" + "\n".join(flow_lines))

    project_type = "unknown"
    if list(Path(ws_dir).glob("*.csproj")):
        project_type = "C#"
    elif (Path(ws_dir) / "package.json").is_file():
        project_type = "Node.js"
    elif (Path(ws_dir) / "pyproject.toml").is_file() or (Path(ws_dir) / "requirements.txt").is_file():
        project_type = "Python"
    elif (Path(ws_dir) / "Cargo.toml").is_file():
        project_type = "Rust"

    context = "\n\n".join(context_parts) if context_parts else "(no workspace context detected)"

    if args.print_context:
        print(context)
        return

    has_git = bool(git_log)
    has_readme = bool(readme_text)

    comps = []

    comps.append({
        "type": "dialog", "id": 0, "mode": "Plan",
        "prompt": f"Explore and understand the {project_type} project workspace. Read README, examine structure, review recent changes."
    })

    if has_git:
        comps.append({
            "type": "logic", "id": 1,
            "prompt": "Is the workspace ready for development (no blocking issues found during exploration)?",
            "goto_true": 2, "goto_false": 3
        })
        comps.append({
            "type": "dialog", "id": 2, "mode": "Build",
            "prompt": "Continue development based on {#prompt#}. Follow project conventions. Refer to recent git history for context."
        })
        comps.append({
            "type": "dialog", "id": 3, "mode": "Goal",
            "prompt": "Goal: Resolve blocking issues in the workspace. Objective: {#prompt#}"
        })
    else:
        comps.append({
            "type": "logic", "id": 1,
            "prompt": "Does the workspace have existing code or configuration to build upon?",
            "goto_true": 2, "goto_false": 3
        })
        comps.append({
            "type": "dialog", "id": 2, "mode": "Build",
            "prompt": "Implement: {#prompt#} following project conventions."
        })
        comps.append({
            "type": "dialog", "id": 3, "mode": "Goal",
            "prompt": "Goal: Initialize and scaffold the project. Objective: {#prompt#}"
        })

    comps.append({
        "type": "logic", "id": 4,
        "prompt": "Is the implementation complete and verified?",
        "goto_true": 5, "goto_false": 2
    })
    comps.append({
        "type": "dialog", "id": 5, "mode": "Goal",
        "prompt": "Goal: {#prompt#} — verify all requirements are met, tests pass, and documentation is updated."
    })

    if load_workflow(wf_name, d) is not None and not args.force:
        print(f"Workflow '{wf_name}' already exists. Use --force to overwrite.", file=sys.stderr)
        print(f"\nGenerated preview (unsaved):")
        _print_sum_preview(wf_name, comps)
        return

    wf = FlowWorkflow(wf_name)
    for c_data in comps:
        t = c_data["type"]
        if t == "dialog":
            wf.components.append(FlowDialogComponent(c_data))
        elif t == "logic":
            wf.components.append(FlowLogicComponent(c_data))
    save_workflow(wf, d)
    print(f"Created: {d}/{wf_name}.Flow.json")
    print(f"  Type: {project_type} project workflow")
    print(f"  Components: {len(wf.components)} ({sum(1 for c in wf.components if c.type=='dialog')} dialog + {sum(1 for c in wf.components if c.type=='logic')} logic)")
    print(f"  Description: {describe_workflow(wf_name, d)}")

def _print_sum_preview(name, comps):
    for c in comps:
        t = c["type"]
        if t == "dialog":
            pr = c["prompt"][:60]
            print(f"  [{c['id']:02d}] DIALOG  mode={c['mode']:5s}  {pr}")
        elif t == "logic":
            pr = c["prompt"][:60]
            print(f"  [{c['id']:02d}] LOGIC   T->{c['goto_true']} F->{c['goto_false']}  {pr}")

# ─── Editor Server ────────────────────────────────────────────────────────────

class FlowEditorHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, editor_dir="", **kwargs):
        self.editor_dir = editor_dir
        super().__init__(*args, **kwargs)

    def translate_path(self, path):
        p = super().translate_path(path)
        if p.endswith("/") or not os.path.splitext(p)[1]:
            return os.path.join(self.editor_dir, "FlowEditor.html")
        return p

def serve_editor(flow_dir: str, port: int = 8765) -> None:
    editor_path = Path(__file__).parent / "FlowEditor.html"
    if not editor_path.is_file():
        print(f"[Flow] FlowEditor.html not found alongside flow.py.", file=sys.stderr)
        sys.exit(1)

    os.chdir(flow_dir)  # cwd = flow dir so FSA can pick it up
    server = HTTPServer(("127.0.0.1", port), lambda *a: FlowEditorHandler(*a, editor_dir=str(editor_path.parent)))
    print(f"[Flow] Editor: http://127.0.0.1:{port}")
    print(f"[Flow] Flow dir: {os.path.abspath(flow_dir)}")
    print("[Flow] Press Ctrl+C to stop.")
    webbrowser.open(f"http://127.0.0.1:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[Flow] Server stopped.")
        server.server_close()


# ─── CLI ──────────────────────────────────────────────────────────────────────

def cmd_list(args):
    d = resolve_dir(args.dir)
    names = list_workflows(d)
    if not names:
        print("No workflows found in '{}'.".format(d))
        return
    for n in names:
        wf = load_workflow(n, d)
        if wf is None:
            continue
        dc = sum(1 for c in (wf.components if wf else []) if c.type == "dialog")
        lc = sum(1 for c in (wf.components if wf else []) if c.type == "logic")
        desc = describe_workflow(n, d)
        print(f"  {n:30s}  {dc}d {lc}l  {desc or ''}")

def cmd_show(args):
    wf = load_workflow(args.name, resolve_dir(args.dir))
    if wf is None:
        print(f"Workflow '{args.name}' not found.", file=sys.stderr)
        sys.exit(1)
    print(f"Workflow: {wf.name} ({len(wf.components)} components)")
    for c in sorted(wf.components, key=lambda x: x.id):
        if isinstance(c, FlowDialogComponent):
            pr = c.prompt[:60] + "..." if len(c.prompt) > 60 else c.prompt
            print(f"  [{c.id:02d}] DIALOG  mode={c.mode:5s}  {pr}")
        elif isinstance(c, FlowLogicComponent):
            pr = c.prompt[:60] + "..." if len(c.prompt) > 60 else c.prompt
            print(f"  [{c.id:02d}] LOGIC   T->{c.goto_true} F->{c.goto_false}  {pr}")

def cmd_validate(args):
    names = list_workflows(resolve_dir(args.dir)) if args.all else [args.name]
    if args.all:
        args.name = "(all)"
    all_ok = True
    for n in names:
        errs = validate_workflow(n, resolve_dir(args.dir))
        if errs:
            all_ok = False
            print(f"!! {n}:")
            for e in errs:
                print(f"    {e}")
        else:
            print(f"OK {n}")
    if not all_ok:
        sys.exit(1)

def cmd_new(args):
    d = resolve_dir(args.dir)
    if load_workflow(args.name, d) is not None:
        print(f"Workflow '{args.name}' already exists.", file=sys.stderr)
        sys.exit(1)
    wf = FlowWorkflow(args.name)
    save_workflow(wf, d)
    print(f"Created: {d}/{args.name}.Flow.json")

def cmd_delete(args):
    if delete_workflow(args.name, resolve_dir(args.dir)):
        print(f"Deleted: {args.name}")
    else:
        print(f"Not found: {args.name}")

def cmd_cycles(args):
    d = resolve_dir(args.dir)
    wf = load_workflow(args.name, d) if args.name else None
    if args.name and wf is None:
        print(f"Workflow '{args.name}' not found.", file=sys.stderr)
        sys.exit(1)
    if args.all or wf is None:
        names = list_workflows(d)
        all_cycles = {}
        for n in names:
            w = load_workflow(n, d)
            if w:
                c = detect_cycles_static(w)
                if c:
                    all_cycles[n] = c
        if not all_cycles:
            print("No cycles detected in any workflow.")
            return
        for n, cycles in all_cycles.items():
            print(f"\n'{n}': {len(cycles)} cycle(s)")
            for cyc in cycles:
                print(f"  [{', '.join(str(c) for c in cyc)}]")
        return
    cycles = detect_cycles_static(wf)
    if not cycles:
        print(f"No cycles detected in '{args.name}'.")
    else:
        print(f"'{args.name}': {len(cycles)} potential cycle(s):")
        for cyc in cycles:
            print(f"  [{', '.join(str(c) for c in cyc)}]")
        print(f"  [!] These logic goto-back pairs can cause infinite loops if conditions never change.")

def cmd_run(args):
    d = resolve_dir(args.dir)
    name = find_workflow(args.name, d) or args.name
    if args.eval_true:
        run_workflow(name, d, args.input, llm_eval=lambda p: True)
    elif args.eval_false:
        run_workflow(name, d, args.input, llm_eval=lambda p: False)
    else:
        run_workflow(name, d, args.input)

def cmd_auto(args):
    """Auto-trigger: scan text for matching workflow names."""
    d = resolve_dir(args.dir)
    text = args.text or " ".join(args.remaining) if hasattr(args, 'remaining') else args.text
    results = auto_trigger(text, d)
    if not results:
        print(f"[Flow] No workflow matches found in text.")
        return
    for name, score in results:
        match_type = "EXACT" if score >= 1.0 else "FUZZY" if score >= 0.5 else "WEAK"
        desc = describe_workflow(name, d) or ""
        print(f"  [{match_type:5s} {score:.2f}] {name}  {desc}")
    best = results[0]
    if best[1] >= 0.5:
        print(f"\n[Flow] Best match: {best[0]} (score={best[1]:.2f})")
        print(f"[Flow] Run with: flow run \"{best[0]}\"")

def cmd_serve(args):
    serve_editor(resolve_dir(args.dir), args.port)

def cmd_check(args):
    """Check all workflows in the Flow directory for validity and print summary."""
    d = resolve_dir(args.dir)
    names = list_workflows(d)
    if not names:
        print(f"No workflows in '{d}'.")
        sys.exit(1)
    total_d = total_l = errors = 0
    for n in names:
        wf = load_workflow(n, d)
        if wf is None:
            print(f"!! {n}: failed to load")
            errors += 1
            continue
        dc = sum(1 for c in wf.components if c.type == "dialog")
        lc = sum(1 for c in wf.components if c.type == "logic")
        total_d += dc; total_l += lc
        errs = validate_workflow(n, d)
        if errs:
            errors += 1
            print(f"!! {n}: {len(errs)} error(s)")
            for e in errs:
                print(f"    {e}")
        else:
            print(f"OK {n}: {dc} dialog + {lc} logic = {dc+lc} total")
    print(f"\nSummary: {len(names)} workflow(s), {total_d} dialog, {total_l} logic")
    if errors:
        print(f"{errors} workflow(s) have errors.")
        sys.exit(1)


# ─── Dashboard (auto-start) ─────────────────────────────────────────────────

def cmd_dashboard(args):
    d = resolve_dir(args.dir)
    Path(d).mkdir(parents=True, exist_ok=True)
    md_path = Path(d) / "Flow.md"
    if not md_path.is_file():
        md_path.write_text("""# Flow Workflows

Files in this directory: `{name}.Flow.json`

Components:
- **dialog**: mode=Build|Plan|Goal, prompt with {#prompt#}
- **logic**: condition, goto_true, goto_false

Run `flow --help` for CLI reference.
""", encoding="utf-8")
        print(f"  [Flow.md created]")

    names = list_workflows(d)
    print(f"  Flow directory: {d}")
    print()

    if not names:
        print("  No workflows found.")
        print(f"  Create one: flow new <name>  or  flow sum <name> --workspace .")
        return

    total_d = total_l = errors = 0
    for n in names:
        wf = load_workflow(n, d)
        if wf is None:
            print(f"  !! {n}: failed to load")
            errors += 1
            continue
        dc = sum(1 for c in wf.components if c.type == "dialog")
        lc = sum(1 for c in wf.components if c.type == "logic")
        total_d += dc; total_l += lc
        errs = validate_workflow(n, d)
        if errs:
            errors += 1
            print(f"  !! {n}: {len(errs)} error(s)")
            for e in errs:
                print(f"      {e}")
        else:
            desc = describe_workflow(n, d)
            print(f"  OK {n:25s}  {dc}d {lc}l  {desc or ''}")

    print(f"\n  Summary: {len(names)} workflow(s), {total_d} dialog, {total_l} logic", end="")
    if errors:
        print(f", {errors} with errors")
    else:
        print()

def main():
    parser = argparse.ArgumentParser(prog="flow", description="Flow Workflow CLI")
    parser.add_argument("--dir", "-d", help="Flow directory (default: $FLOW_DIR or 'Flow/')")
    sub = parser.add_subparsers(title="commands")

    p_list = sub.add_parser("list", help="List workflows with descriptions")
    p_list.set_defaults(func=cmd_list)

    p_show = sub.add_parser("show", help="Show workflow details")
    p_show.add_argument("name")
    p_show.set_defaults(func=cmd_show)

    p_val = sub.add_parser("validate", help="Validate a workflow")
    p_val.add_argument("name", nargs="?", default="")
    p_val.add_argument("--all", action="store_true", help="Validate all workflows")
    p_val.set_defaults(func=cmd_validate)

    p_new = sub.add_parser("new", help="Create a new workflow")
    p_new.add_argument("name")
    p_new.set_defaults(func=cmd_new)

    p_del = sub.add_parser("delete", help="Delete a workflow")
    p_del.add_argument("name")
    p_del.set_defaults(func=cmd_delete)

    p_run = sub.add_parser("run", help="Execute a workflow")
    p_run.add_argument("name")
    p_run.add_argument("--input", "-i", default="", help="User input for {#prompt#}")
    p_run.add_argument("--true", dest="eval_true", action="store_true", help="Auto-answer TRUE for all logic conditions")
    p_run.add_argument("--false", dest="eval_false", action="store_true", help="Auto-answer FALSE for all logic conditions")
    p_run.set_defaults(func=cmd_run)

    p_auto = sub.add_parser("auto", help="Auto-trigger: scan text for matching workflow names")
    p_auto.add_argument("text", nargs="?", default="", help="Text to scan for workflow names")
    p_auto.add_argument("remaining", nargs=argparse.REMAINDER, help=argparse.SUPPRESS)
    p_auto.set_defaults(func=cmd_auto)

    p_sum = sub.add_parser("sum", help="Generate workflow from workspace analysis")
    p_sum.add_argument("name", help="Workflow name to create")
    p_sum.add_argument("--workspace", "-w", default="", help="Workspace directory (default: cwd)")
    p_sum.add_argument("--force", "-f", action="store_true", help="Overwrite if exists")
    p_sum.add_argument("--print-context", action="store_true", help="Show workspace context only")
    p_sum.set_defaults(func=cmd_sum)

    p_serve = sub.add_parser("serve", help="Start editor server")
    p_serve.add_argument("--port", "-p", type=int, default=8765)
    p_serve.set_defaults(func=cmd_serve)

    p_check = sub.add_parser("check", help="Validate all workflows")
    p_check.set_defaults(func=cmd_check)

    p_gen = sub.add_parser("gen", help="Generate workflow from natural language description")
    p_gen.add_argument("text", help="Description of the workflow (use {#prompt#} for template placeholders)")
    p_gen.add_argument("--name", "-n", default="", help="Workflow name (auto-generated from text if omitted)")
    p_gen.add_argument("--force", "-f", action="store_true", help="Overwrite if exists")
    p_gen.set_defaults(func=cmd_gen)

    p_cycles = sub.add_parser("cycles", help="Analyze workflow structure for potential cycles")
    p_cycles.add_argument("name", nargs="?", default="", help="Workflow name (omit or --all for all)")
    p_cycles.add_argument("--all", action="store_true", help="Check all workflows")
    p_cycles.set_defaults(func=cmd_cycles)

    args = parser.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        cmd_dashboard(args)


if __name__ == "__main__":
    main()

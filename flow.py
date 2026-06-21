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

WORKFLOW_DIR = os.environ.get("FLOW_DIR", "Flow")

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


def run_workflow(name: str, flow_dir: str, user_input: str | None = None, llm_eval=None) -> None:
    """Execute a workflow. `llm_eval(prompt: str) -> bool` is called for logic
    components. If None, logic components prompt stdin for TRUE/FALSE input."""
    wf = load_workflow(name, flow_dir)
    if wf is None:
        print(f"[Flow] Workflow '{name}' not found.", file=sys.stderr)
        sys.exit(1)

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
    MAX_VISITS = 10

    auto_mode = llm_eval is not None

    while 0 <= idx < len(components):
        c = components[idx]
        cid = c.id

        visit_counts[cid] = visit_counts.get(cid, 0) + 1
        if visit_counts[cid] > MAX_VISITS:
            print(f"\n[Flow] Cycle detected: component {c.id} visited {visit_counts[cid]} times, stopping.")
            break

        if isinstance(c, FlowDialogComponent):
            prompt = _build_dialog_prompt(c, user_input)
            print(f"\n{'='*60}")
            print(f"[Component {c.id}] Mode: {c.mode}")
            print(f"{'='*60}")
            print(prompt)
            print(f"{'─'*60}")
            if auto_mode:
                print("[Flow] Auto mode: prompt printed — simulated run (no actual conversation injection)")
                response = ""
            else:
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
                print(f"[Response {c.id}] {response[:120]}{'...' if len(response) > 120 else ''}")
            responses[cid] = response
            idx += 1

        elif isinstance(c, FlowLogicComponent):
            prompt = c.prompt.replace("{#prompt#}", user_input or "")
            eval_prompt = f"In the current workspace, is the following condition already implemented?\nCondition: {prompt}\nAnswer only TRUE or FALSE."
            print(f"\n>>> Logic [{c.id}] Evaluating: {prompt} >>>")
            if llm_eval:
                result = llm_eval(eval_prompt)
            else:
                while True:
                    ans = input("  Condition TRUE or FALSE? (T/F): ").strip().upper()
                    if ans in ("T", "TRUE"):
                        result = True
                        break
                    elif ans in ("F", "FALSE"):
                        result = False
                        break

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

    Yields (dialog component):
        ``{"type": "dialog", "id": int, "mode": str, "prompt": str}``
    Expects via ``.send()``:
        ``{"type": "dialog_response", "response": str}``

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
    MAX_VISITS = 10

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

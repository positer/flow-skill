---
name: flow
description: "Flow workflow skill and callable plugin bridge for Codex, Claude Code, and other agents. Use when the user invokes /Flow, wants to create, edit, validate, list, fuzzy-match, auto-trigger, or run workflows saved as Flow/{name}.Flow.json; when working with dialog components in Build/Plan/Goal modes, logic components with goto_true/goto_false branching, {#prompt#} prompt templates, FlowEditor.html, Flow/Flow.md, FlowDialogPlugin, chat-area step-by-step workflow execution, UI workflow editor tasks, or Chinese-language requests about Flow workflows and workflow startup."
---

# Flow Workflow Skill

Use this skill as both:

1. A **skill**: follow these instructions when the user invokes `/Flow` or asks for Flow workflow work.
2. A **callable plugin bridge**: use `FlowDialogPlugin` or the plugin MCP tools to list, find, start, and step workflows.

## Storage

- Workflows live in `Flow/{name}.Flow.json`.
- The authoritative schema guide is `Flow/Flow.md`.
- `prompt` is the canonical JSON field; UI labels it as **base prompt**. Readers may accept `base_prompt` as an alias, but writers should save `prompt`.

## Component Schema

Dialog component:

```json
{ "type": "dialog", "id": 0, "mode": "Plan", "prompt": "Plan from this instruction: {#prompt#}" }
```

Logic component:

```json
{ "type": "logic", "id": 1, "prompt": "Is README.md already complete?", "goto_true": 3, "goto_false": 2 }
```

Rules:

- `id` is the ordered execution address.
- Dialog `mode` must be `Build`, `Plan`, or `Goal`.
- Logic TRUE means the condition is already implemented in the current workspace and jumps to `goto_true`.
- Logic FALSE means it is not implemented and jumps to `goto_false`.
- After any goto, continue sequentially from the target component.

## `/Flow` Execution

When the user invokes `/Flow <name-or-text>`:

1. Resolve exact workflow name first.
2. If no exact match, fuzzy match with `find_workflow()` or `flow auto "<text>"`.
3. Drive `run_workflow_iter()` or `FlowDialogBridge`; do not hide execution in CLI stdout.
4. For every yielded step, visibly post the step in the current conversation area before acting.

Conversation rendering:

- Dialog step: show `Flow {id} {mode}` and the rendered prompt, then execute it according to `mode`.
- Logic step: show `Flow {id} Logic`, evaluate the condition against the current workspace, then show the branch decision and next target.
- Branch step: show TRUE/FALSE and the goto target.
- Completion/error: show the final state.

If the host cannot programmatically switch Build/Plan/Goal modes, keep the mode label visible and follow the mode's intent in the same conversation.

## Prompt Substitution

- Replace `{#prompt#}` with user input.
- For the standard Chinese Plan pattern, replace the placeholder with user input and collapse redundant "set plan" wording so the prompt is a direct planning instruction.

## Goal Mode

Goal mode is internal to Flow. Do not install or reference an external goal plugin.

Execution is:

1. Run the Goal dialog like a Build-style step.
2. Inject a Logic verification step.
3. If verification is FALSE, loop back to the Goal component.
4. If TRUE, continue sequentially.

## Tools and Files

- `flow.py`: CLI, validation, matching, generator runtime.
- `FlowDialogPlugin/`: step bridge for agents and plugin tools.
- `FlowEditor.html`: UI editor for workflow trees.
- `Flow/Flow.md`: JSON schema and execution semantics.

Useful commands:

```bash
python flow.py
python flow.py list
python flow.py check
python flow.py show <name>
python flow.py auto "<text>"
python flow.py run <name> -i "<user input>"
python flow.py serve -p 8765
```

Prefer the generator/plugin path for Agent execution. Use CLI `run` only as terminal/debug fallback.

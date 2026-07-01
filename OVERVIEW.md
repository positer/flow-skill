# Flow Skill Overview

## Goal

Flow Skill provides a workflow system for Codex, Claude Code, and MCP-capable
agents. Workflows are saved as `Flow/{name}.Flow.json` and execute as visible
conversation-area steps.

## File Tree

```text
flow-skill/
├── .claude-plugin/
│   └── plugin.json
├── .codex-plugin/
│   └── plugin.json
├── .mcp.json
├── bin/
│   └── flow-mcp.py
├── Flow/
│   ├── Flow.md
│   └── *.Flow.json
├── FlowDialogPlugin/
│   ├── __init__.py
│   ├── dialog_plugin.py
│   └── README.md
├── FlowEditor.html
├── flow.py
├── SKILL.md
├── skills/
│   └── flow/
│       └── (plugin skill copy)
├── README.md
├── requirements.txt
├── pyproject.toml
└── archive/
```

## Directory Roles

- `.claude-plugin/`: Claude Code plugin manifest.
- `.codex-plugin/`: Codex plugin manifest with skill and MCP metadata.
- `bin/`: Callable MCP plugin server entrypoints.
- `Flow/`: Workflow schema and saved workflow examples.
- `FlowDialogPlugin/`: Bridge for chat-visible step execution.
- `skills/flow/`: Plugin loader copy of the standalone skill files.
- `archive/`: Local dated project history and implementation notes.

## Important Files

- `.mcp.json`: Registers the `flow-workflow` MCP server.
- `bin/flow-mcp.py`: Exposes callable workflow tools over stdio JSON-RPC.
- `flow.py`: CLI, matching, validation, generation, and iterator runtime.
- `FlowEditor.html`: UI tree editor for workflow design.
- `SKILL.md`: Agent-facing skill instructions and trigger behavior.
- `Flow/Flow.md`: Authoritative workflow file format and execution protocol.

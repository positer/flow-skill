# Initial Audit — Flow Skill Implementation Status

Date: 2026-06-21

## Source Reference: `dirt/` folder

## Gap Analysis

| Requirement | Status | Notes |
|---|---|---|
| Flow.py CLI with list/show/validate/run/sum/serve/check | ✅ Done | Full CLI implementation |
| FlowEditor.html tree editor | ✅ Done | Visual workflow editor |
| *.Flow.json data model (dialog + logic components) | ✅ Done | FlowDialogComponent, FlowLogicComponent, FlowWorkflow |
| Sequential execution by component ID | ✅ Done | Sorted by id, sequential with goto |
| Cycle detection in runner | ✅ Done | visited set per component instance |
| {#prompt#} substitution | ✅ Done | Simple string replace |
| Dialog component with mode (Build/Plan/Goal) | ✅ Done | mode field, validated |
| Logic component with goto_true/goto_false | ✅ Done | Validated against existing IDs |
| Validation (all workflows) | ✅ Done | cmd_check, validate_workflow |
| Workspace analysis → workflow generation | ✅ Done | cmd_sum |
| Flow/Flow.md exists | ⚠️ Partial | Only 9 lines, lacks detailed format spec |
| **/Flow fuzzy name matching** | ❌ Missing | Only exact name supported |
| **Agent auto-trigger** | ❌ Missing | No mechanism for agent to auto-detect/launch workflows |
| **Plan mode prompt wrapping convention** | ⚠️ Partial | Generic {#prompt#} replace works, but no Plan-mode-specific template conventions documented |
| **Logic component workspace-implementation eval** | ⚠️ Partial | llm_eval hook exists but no built-in "is this implemented?" evaluator |
| **OpenCode-goal-plugin** | ❌ Missing | Not implemented anywhere |
| **Flow.md detailed format guide** | ❌ Missing | Needs comprehensive *.Flow.json schema documentation |
| **README.md** | ❌ Missing | No project root README |
| **Archive protocol** | ❌ Missing | No archive directory |

## Action Plan

1. Enhance `flow.py`: fuzzy match, auto-trigger function, Plan mode wrapping
2. Rewrite `Flow/Flow.md` with complete format specification
3. Create `OpenCode_goal_plugin/` (built-in, conditional on agent capability detection)
4. Create `README.md` with project overview
5. Update `SKILL.md` with improved description
6. Minor FlowEditor.html updates for Plan mode annotation
7. Add static cycle detection + pre-flight warning on first run
8. Fix cycle detection algorithm (visit_counts replacement for visited set)
9. Fix llm_eval indentation bug in logic component execution

## Test Results (Flow-test)

Created 9-component workflow (5 dialog + 4 logic) covering:
- All 3 dialog modes: Plan, Build, Goal
- 4 logic goto-back pairs (intentional cycles for testing)
- {#prompt#} placeholder substitution (%s replaced with user input)

| Test | Command | Result |
|------|---------|--------|
| Happy path | `--true` | Preflight shows 4 cycle warnings → confirm → executes 0→1→2→3→4→5→6→7→8 → complete |
| Cancel at preflight | user says n | Shows all warnings → cancels, no execution |
| Runtime cycle | `--false` | Preflight → confirm → 0→1(loop) × 10 → "Cycle detected: visited 11 times" → stop |
| Static cycles | `cycles Flow-test` | Correctly identifies 4 cycles: [6,7] [4,5] [2,3] [0,1] |
| Validate | `validate Flow-test` | OK |
| Describe | `list` | Shows arrow-connected description |

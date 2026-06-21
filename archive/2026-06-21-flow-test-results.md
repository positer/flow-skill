# Flow-Test Results — 2026-06-21

## Test A: Happy path (all TRUE)

**Command:** `python flow.py run flow-test --true --input "test all components"`

**Result: PASSED**

```
  [!] 'flow-test' has 3 potential cycle(s):
    [!] Potential logic cycle detected in 'flow-test': components [4, 5] can form a loop.
    [!] Potential logic cycle detected in 'flow-test': components [2, 3] can form a loop.
    [!] Potential logic cycle detected in 'flow-test': components [0, 1] can form a loop.
  (auto mode: --true/--false, continuing)

[Component 0] Mode: Plan    -> (auto)
>>> Logic [1] -> TRUE, goto component 2
[Component 2] Mode: Build   -> (auto)
>>> Logic [3] -> TRUE, goto component 4
[Component 4] Mode: Goal    -> (auto)
>>> Logic [5] -> TRUE, goto component 6
[Component 6] Mode: Goal    -> (auto)
[Flow] Workflow complete.
```

**Execution order:** 0 → 1(T→2) → 2 → 3(T→4) → 4 → 5(T→6) → 6

## Test B: Cycle detection (all FALSE)

**Command:** `python flow.py run flow-test --false --input "test cycle detection"`

**Result: PASSED**

```
  [!] 'flow-test' has 3 potential cycle(s): (same 3 warnings)
  (auto mode: --true/--false, continuing)

[Component 0] Mode: Plan    -> (auto)
>>> Logic [1] -> FALSE, goto component 0
[Component 0] Mode: Plan    -> (auto)          [visit 2]
>>> Logic [1] -> FALSE, goto component 0
... (repeats 11 times) ...
[Component 0] visited 11 times, stopping.
[Flow] Workflow complete.
```

**Loop detected:** [0,1] — Logic ID 1 keeps FALSE→0, revisit ID 0 → ID 1 → FALSE→0...
**Guard triggers at visit 11** (MAX_VISITS=10, first visit is #1, 11th visit triggers guard).

## Test C: Generator via Python API (`run_workflow_iter`)

**Script:** `test_c_generator.py` (deleted after test)

**Result: PASSED** (after fix: initial version hung because `cycle_warning` yield was not skipped)

```
Skipped: cycle_warning - 3 warning(s)
Step 1: DIALOG id=0 mode=Plan
Step 2: LOGIC id=1 (all TRUE)
Step 3: DIALOG id=2 mode=Build
Step 4: LOGIC id=3 (all TRUE)
Step 5: DIALOG id=4 mode=Goal
Step 6: LOGIC id=5 (all TRUE)
Step 7: DIALOG id=6 mode=Goal
{'type': 'complete', 'message': 'Workflow complete.'}
Total steps (before complete): 7
```

## Test D: FlowDialogPlugin bridge (`FlowDialogBridge`)

**Script:** `test_d_bridge.py` (deleted after test)

**Result: PASSED**

```
Step 1: DIALOG id=0 mode=Plan
Step 2: LOGIC id=1 (all TRUE)
Step 3: DIALOG id=2 mode=Build
Step 4: LOGIC id=3 (all TRUE)
Step 5: DIALOG id=4 mode=Goal
Step 6: LOGIC id=5 (all TRUE)
Step 7: DIALOG id=6 mode=Goal
{'type': 'complete', 'message': 'Workflow complete.'}
Total steps (before complete): 7
```

## Summary

| Test | Status | Notes |
|------|--------|-------|
| A: Happy path (--true) | **PASS** | All 7 components in order, 3 cycle warnings auto-continued |
| B: Cycle detection (--false) | **PASS** | Loop [0,1] detected at visit 11, guard stopped execution |
| C: Generator API | **PASS** | 7 steps via `run_workflow_iter`; note: callers must skip `cycle_warning` |
| D: Bridge API | **PASS** | 7 steps via `FlowDialogBridge` (auto-skips cycle_warnings) |

**Discrepancies / Notes:**
1. Test C initially hung because `run_workflow_iter` yields `cycle_warning` as its first value before any dialog/logic step. Callers using `next()` directly must skip `cycle_warning` yields (same pattern as `FlowDialogBridge.start()`). This is documented behavior but a pitfall for naive consumers.
2. Test B only exercises the [0,1] loop (not [2,3] or [4,5]) because execution never passes ID 1's logic when all conditions are FALSE. The three cycles are independent — only the first reachable one triggers the guard.

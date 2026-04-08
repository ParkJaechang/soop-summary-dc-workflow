# Workflow Health

## Last Audit

- Date: 2026-04-08
- Auditor: workflow manager
- Scope: active board entries, shared workflow rules, and current active handoff prompts

## Findings

### W-001 Template Drift Risk

- Severity: medium
- Area: `agents/tasks/_template/handoff.md`
- Risk: the old template did not remind chats to hand back to `coordinator` or to generate a role-safe next prompt, so future tasks could regress into loose baton passing
- Action taken: updated the template to require a coordinator-first default and a role-safe next prompt

### W-002 Turn-Start Re-Anchor Was Under-Specified

- Severity: high
- Area: shared workflow rules and role files
- Risk: long-running chats can gradually absorb adjacent responsibilities if they are not forced to reread role and task files each turn
- Action taken: added turn-start re-anchor rules to `agents/shared/coding_rules.md` and checklist sections to all active role files

### W-003 Active Prompt Safety Needed Tightening

- Severity: medium
- Area: active task handoff prompts
- Risk: older prompts can still work, but they may not explicitly force role confirmation and safe baton passing
- Action taken: accepted D-013 and marked prompt safety as a required workflow rule for all future handoffs

### W-004 Active Handoff Sequence Was Partly Stale

- Severity: low
- Area: `agents/tasks/TASK-004-canonical-summary-payload-artifact-from-soop-summery-local-v3/handoff.md`
- Risk: the active baton prompt itself was role-safe, but nearby explanatory notes still referred to `TASK-002` as if it were unresolved, which could mislead the user or a later coordinator audit about the current sequence
- Action taken: corrected the TASK-004 handoff notes to reflect that TASK-002 is already closed and that the live baton is `summary_engineer -> coordinator -> reviewer` for TASK-004

### W-005 Self-Prompt Risk Was Not Yet Explicitly Blocked

- Severity: high
- Area: shared prompt rules
- Risk: without an explicit no-self-prompt rule, a specialist can accidentally hand the baton back to itself, which makes chat reuse ambiguous and weakens coordinator supervision
- Action taken: accepted D-015 and added explicit no-self-prompt plus same-chat-continuation rules

### W-006 Baton Overhead Was Too High For Small Fixes

- Severity: medium
- Area: coordinator checkpoint frequency
- Risk: too many tiny baton passes can slow momentum even when the same specialist is still the right owner for the next small fix or artifact refresh
- Action taken: accepted D-026 and D-027, allowing up to 2 same-role micro-loops before a required coordinator checkpoint

### W-007 Historical Prompts Can Reappear After The Board Has Moved On

- Severity: medium
- Area: user-pasted older handoff prompts
- Risk: a previously valid prompt can point to a closed task or pre-rule workflow path, which can send the baton to the wrong slice if the chat history is trusted more than the board
- Action taken: reaffirmed that `board/tasks.yaml` plus the active task `status.yaml` and `handoff.md` override older prompt text, and coordinator should redirect the baton to the current active task instead of reviving the old slice

## Current Expectation

- every non-coordinator pass returns to `coordinator` unless the task explicitly says otherwise
- every turn starts with role re-anchor
- every next prompt names one role, one task, and exact files to read first
- explanatory handoff notes must also reflect the current board state, not just the prompt block
- no non-coordinator role writes the next prompt to itself
- same-role continuation is allowed only as a small micro-loop, not as an open-ended specialist chain
- externally blocked tasks should stop the loop and switch to an unblock checklist rather than continue cycling roles

## If Drift Is Suspected Again

1. send the next baton to `coordinator`
2. have coordinator reread `board/tasks.yaml`, the active task `status.yaml`, and the latest `handoff.md`
3. compare requested work against ownership and task state
4. repair the task files and next prompt before any further implementation continues

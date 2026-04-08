# Coding And Collaboration Rules

## Shared Operating Rules

- read `project_brief.md`, `architecture.md`, and the role file before acting
- update `status.yaml` whenever status, owner, or blocking state changes
- keep durable decisions out of chat history and in files
- prefer small, reviewable changes with evidence
- do not silently redefine task scope

## Turn-Start Re-Anchor Rule

- at the start of every turn, reread the role file plus the task `status.yaml` and `handoff.md`
- before doing any work, restate in one line which single role you are acting as for this turn
- if the requested work does not match that role, do not silently absorb it; record the mismatch and route back to `coordinator`
- if the active task files and the chat request disagree, task files win until the coordinator updates them
- long-running chats should treat every new user message as a fresh turn and re-anchor again

## Task State Vocabulary

- `draft`: not ready for execution
- `active`: currently being worked
- `blocked`: cannot proceed without a dependency or decision
- `changes_requested`: reviewer found work to do
- `ready_for_review`: implementation is ready for review
- `ready_for_acceptance`: reviewer is satisfied and coordinator can close
- `done`: closed

External blocker rule:

- if a task is blocked by missing permissions, missing credentials, or a deployment context the current chats do not control, do not keep cycling specialists
- in that state, `coordinator` should park the task as `blocked`, explain the blocker in user terms, and stop routing further role work until the dependency changes
- the next role should be `none` while blocked, unless a real unblock event occurs

## Handoff Standard

Every handoff should answer:

1. what changed
2. what still needs work
3. what file to read first
4. who should act next
5. the exact paste-ready prompt for the next chat

Default baton rule:

- non-coordinator roles should normally hand back to `coordinator`, not skip directly to another implementation role
- coordinator becomes the supervisor gate that shows the user the evidence, results, and open questions before the next routing decision
- direct role-to-role handoff should happen only when the coordinator or task spec explicitly allows it
- if a role notices workflow drift, unclear ownership, or a task that no longer matches the current request, the baton should return to `coordinator` explicitly

## Micro-Loop Rule

- small same-role follow-up work may be bundled into one specialist pass instead of reopening the coordinator gate after every tiny change
- a micro-loop is allowed only when the role, task goal, file area, and validation method stay the same
- typical allowed micro-loop work:
  - fix plus test plus artifact refresh
  - one review finding plus regression coverage
  - one payload-field adjustment plus sample regeneration
- a micro-loop must not silently add scope, change owners, or cross into another role's responsibility

## Same-Role Continuation Limit

- the same specialist may continue for up to 2 consecutive micro-loops inside one task slice before handing back to `coordinator`
- if a third same-role pass seems necessary, return to `coordinator` first for a supervisor checkpoint
- if the user explicitly asks to inspect progress sooner, return to `coordinator` immediately

## Next-Chat Prompt Standard

- every role must end its turn with one paste-ready prompt for the next chat
- the prompt should tell the next chat exactly which shared files, role file, and task files to read first
- the prompt should name the task id and the concrete next action to take
- do not make the user ask again for the next-chat prompt after a handoff
- by default, implementation, review, and ops turns should generate the next prompt for `coordinator`
- agent-to-agent prompt bodies may stay in English for consistency across role chats
- user-facing handoff guidance must be written in Korean and must explicitly say which chat or role the user should send the next prompt to
- every next-chat prompt should explicitly name the valid role roster for this workflow:
  `summary_engineer`, `publisher_engineer`, `ops`, `reviewer`, `coordinator`
- the receiving chat should restate which one role it is responsible for in that turn before doing work
- every next-chat prompt should also say which role or chat produced that prompt, so the receiver can see who handed off the baton
- if the next prompt is not role-safe, ownership-safe, or file-specific enough, route back to `coordinator` instead of guessing

## No Self-Prompt Rule

- the sender role and receiver role must normally be different
- non-coordinator roles must not write the next prompt to the same role that just finished the turn
- if another pass from the same specialist seems needed, hand back to `coordinator` first
- `coordinator` decides whether the user should continue in the same chat, open a fresh chat for that role, or route elsewhere
- if a role catches itself preparing a prompt to itself, stop and route to `coordinator` instead

## Same-Chat Continuation Rule

- do not fake a baton pass when the real intent is "keep using the same chat"
- if the best path is same-chat continuation, record that recommendation in `handoff.md` and still return control to `coordinator`
- the actual next-chat prompt should then be authored by `coordinator`, not by the specialist to itself

## Role Drift Signals

If any of these happen, treat it as workflow drift and route back to `coordinator`:

- a chat starts proposing work owned by another role
- the task asks for implementation but the files still show planning or review-only state
- the next chat prompt does not name one role and one task clearly
- the next chat prompt sends the baton back to the same non-coordinator role that just finished
- artifacts or evidence are missing but the task is being pushed toward review or done
- the same chat is asked to keep going for many rounds without rereading the role and task files

## Supervisor Checkpoint Standard

- coordinator checkpoints are mandatory on role changes, review handoff, acceptance handoff, scope changes, or when user input is needed
- coordinator checkpoints may be skipped between tiny same-role micro-loops when the work stays inside the same role and slice
- after each implementation, review, or ops pass that ends a slice or changes the baton, the coordinator should provide a checkpoint for the user before routing the next role
- the checkpoint should summarize:
  1. what was changed
  2. which files or artifacts prove it
  3. what the user should inspect next
  4. what decisions or feature additions are now possible
  5. one paste-ready prompt for the next chat after user approval
- coordinator checkpoints should also show a short progress view whenever possible, for example:
  - current task progress
  - count of done vs active tasks on the board
  - which major slice the project is in now
- coordinator should keep `agents/board/progress.md` current enough that the user can see an easy overall percentage and workstream progress at a glance
- do not estimate overall project progress from raw task count alone when major future slices are still ahead
- if the user wants to test, inspect, or change scope, the coordinator should update task files before sending the next role onward
- user-facing coordinator replies should begin with one line in the exact format `Overall progress: XX%`
- that percentage must come from `agents/board/progress.md`
- if `agents/board/progress.md` is stale relative to the current board or milestone state, update that file first and then report the percentage
- for externally blocked tasks, coordinator should switch from "next implementation step" to "next unblock action" mode and give the user a concrete checklist

## File Update Expectations

- `spec.md`: problem, scope, acceptance criteria
- `status.yaml`: live status, owner, touched files, tests, blockers
- `handoff.md`: implementation and routing notes
- `review.md`: findings and residual risk
- `revision_log.md`: chronological summary of important changes
- `done.md`: closeout record

## Evidence Standard

- store payload samples, screenshots, logs, and test outputs under `agents/artifacts/<TASK-ID>/`
- if a claim matters, leave an artifact or a file reference

## Conflict Rule

If two chats disagree, do not overwrite each other blindly. Record the disagreement in the task folder and route it back to the coordinator.

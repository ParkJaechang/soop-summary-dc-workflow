# Decisions

## D-001 File-Based Collaboration First

- Date: 2026-04-07
- Status: accepted
- Decision: use shared files under `agents/` as the first collaboration layer between separate chats
- Why: chat memory is isolated, but shared files are durable, reviewable, and easy to control in VSCode

## D-002 Task Folder Is The Unit Of Work

- Date: 2026-04-07
- Status: accepted
- Decision: organize collaboration around task folders, not free-form role chat logs
- Why: it keeps scope, evidence, and handoff notes attached to one deliverable

## D-003 Approval Before Publish

- Date: 2026-04-07
- Status: accepted
- Decision: preserve a review or approval step before any automatic publish attempt
- Why: this matches the safer publishing direction already described in project docs

## D-004 Stabilize Separate Apps Before Integration

- Date: 2026-04-07
- Status: accepted
- Decision: treat the SOOP summary app, the live/VOD discovery app, and the DC publishing app as separate hardening tracks first, and merge them only after each track exposes a stable contract and evidence
- Why: the current tools are partially working but unstable, so merging now would hide failure boundaries, blur ownership, and make the file-based harness workflow harder to operate safely

## D-005 Canonical Source Identity At Publisher Boundary

- Date: 2026-04-07
- Status: accepted
- Decision: publisher-side dedupe must use one canonical source identity at the boundary instead of whichever fallback field happens to arrive first
- Why: mixed `source_url`, `source_id`, and `source_ref` payloads can represent the same source differently and otherwise bypass draft-job dedupe on the same target

## D-006 Every Handoff Must Carry The Next Chat Prompt

- Date: 2026-04-07
- Status: accepted
- Decision: every role handoff must include one exact paste-ready prompt for the next chat so the user does not need to ask again
- Why: the project is intentionally using separate chats as a harness workflow, so the baton pass must be explicit, durable, and low-friction

## D-007 Task-Local Review Readiness Beats Program Order Unless Acceptance Is Invalidated

- Date: 2026-04-07
- Status: accepted
- Decision: a task that is locally implementation-complete should proceed to `reviewer` even if a broader program-level planning task is still active, unless the unresolved program decision would change that task's acceptance criteria, invalidate its evidence, or force code rework inside the task scope
- Why: otherwise review gets delayed by adjacent planning work and the harness loses the ability to verify narrow slices independently

## D-008 Canonical Summary Producer For The First Stabilization Slice

- Date: 2026-04-07
- Status: accepted
- Decision: treat `soop_summery_local_v3.py` as the canonical summary producer for the first stabilization slice, keep `soop_webapp_v1.py` in parity-follow-up scope, keep `app_live_vod.py` in live/VOD discovery scope, and keep `app_dc_publisher.py` as the downstream contract target only
- Why: this matches the boundary audit, gives the summary track one source of truth for the first machine-readable payload artifact, and does not require `TASK-002` to silently choose a permanent upstream producer inside publisher work

## D-009 Coordinator Is The Supervisor Gate

- Date: 2026-04-08
- Status: accepted
- Decision: after each implementation, review, or ops pass, control should normally return to `coordinator` so the user can inspect results, artifacts, and open questions before the next baton pass
- Why: the user wants to supervise feature growth and validation directly, and the coordinator is the right place to present a concise checkpoint without losing task continuity

## D-010 Current Chat Owns The Next-Chat Prompt

- Date: 2026-04-08
- Status: accepted
- Decision: the chat that finishes a turn must write the paste-ready prompt for the next chat into the task handoff, rather than relying on an outside workflow-design chat to generate it later
- Why: this keeps baton passing local to the task, reduces ambiguity, and matches the intended harness workflow where each role hands off explicitly

## D-011 Re-Anchor The Role On Every Turn

- Date: 2026-04-08
- Status: accepted
- Decision: every role chat must reread its role file and the active task files at the start of every turn, then explicitly restate its single assigned role before acting
- Why: long-running chats can drift over time, so the workflow needs an explicit re-anchor step instead of assuming the role remains stable

## D-012 Coordinator Audits Workflow Drift

- Date: 2026-04-08
- Status: accepted
- Decision: when role confusion, ownership drift, stale prompts, or mismatched task state is suspected, the next baton pass should return to `coordinator` for a workflow audit before work continues
- Why: drift compounds quickly in multi-chat harnesses, and coordinator is the safest place to reconcile task files, prompts, and ownership

## D-013 Active Prompt Must Be Role-Safe

- Date: 2026-04-08
- Status: accepted
- Decision: every active handoff prompt must name the valid role roster, tell the receiving chat to confirm its assigned role, and point to exact task files before any work starts
- Why: ambiguous prompts are one of the main ways chats forget their role or absorb the wrong work

## D-016 User-Facing Handoff Guidance Uses Korean And Names The Recipient

- Date: 2026-04-08
- Status: accepted
- Decision: inter-role prompts may remain in English, but when presenting the next prompt to the user, the assistant must explain in Korean which role or chat should receive it
- Why: the user wants role-chat instructions to stay consistent while still receiving clear Korean guidance about where the next prompt should be sent

## D-017 Every Prompt Must Restate The Role Roster And Recipient Role

- Date: 2026-04-08
- Status: accepted
- Decision: every next-chat prompt must restate the valid workflow roles and ask the receiving chat to confirm which single role it is acting as before it starts work
- Why: this reduces baton-pass confusion and keeps the user aligned on the exact destination chat among `summary_engineer`, `publisher_engineer`, `ops`, `reviewer`, and `coordinator`

## D-014 Every Prompt Must Name The Sending Role

- Date: 2026-04-08
- Status: accepted
- Decision: every next-chat prompt must state which role or chat produced the handoff
- Why: this makes baton origin visible to both the user and the receiving chat, which reduces confusion during long multi-chat loops

## D-015 Non-Coordinator Self-Prompts Are Not Allowed

- Date: 2026-04-08
- Status: accepted
- Decision: non-coordinator roles may not write baton-pass prompts to themselves; when another pass from the same specialty is needed, the baton returns to `coordinator` first
- Why: self-prompting hides supervision checkpoints, makes chat reuse ambiguous, and increases role drift over long runs

## D-018 Coordinator Reports Progress Explicitly

- Date: 2026-04-08
- Status: accepted
- Decision: coordinator checkpoints should include a short explicit progress view whenever the board and task state make that possible
- Why: the user wants visible momentum, not just status labels, and the coordinator is the right place to summarize progress across tasks and slices

## D-019 Prioritize Live Refresh Before VOD Collector Hardening

- Date: 2026-04-08
- Status: accepted
- Decision: after the live/VOD foundation slice closes, the next live/VOD execution slice should stabilize official-API-based live refresh before broader VOD collector hardening or UI polish
- Why: live refresh has the clearest documented upstream contract in the current docs, reuses the newly verified streamer foundation directly, and reduces uncertainty before parser-heavy VOD collection work

## D-020 Prioritize One Tracked-Streamer VOD Collector Slice After Live Refresh

- Date: 2026-04-08
- Status: accepted
- Decision: after official-API live refresh is reviewed, the next live/VOD slice should stabilize one tracked-streamer VOD collection and persistence path before broader scheduler or UI work
- Why: the remaining highest-value uncertainty is replay/VOD discovery and persistence, and proving one tracked-streamer path first keeps parser risk isolated while reusing the now-reviewed foundation and live refresh slices

## D-020 Coordinator Maintains A Board-Level Progress File

- Date: 2026-04-08
- Status: accepted
- Decision: coordinator should maintain `agents/board/progress.md` with an easy overall project percentage and short workstream progress notes
- Why: the user wants one simple place to check project-level progress without reconstructing it from all task files

## D-021 Project Progress Uses Weighted Workstreams

- Date: 2026-04-08
- Status: accepted
- Decision: overall project progress should be estimated from weighted workstreams and milestones, not just the count of completed tasks
- Why: raw task count can look artificially high when future slices are still uncreated or much larger than early tasks

## D-022 User-Facing Progress Must Lead The Reply

- Date: 2026-04-08
- Status: accepted
- Decision: coordinator user-facing replies should start with one exact line formatted as `전체 진행도: XX%`, and that percentage must be sourced from `agents/board/progress.md`
- Why: the workflow manager wants one stable, glanceable progress signal at the top of every report instead of ad hoc percentages inferred from chat context

## D-023 Prioritize Scheduler And Collector-Run Hardening After First VOD Slice

- Date: 2026-04-08
- Status: accepted
- Decision: after the first tracked-streamer VOD slice closes, the next live/VOD execution slice should harden scheduler behavior, duplicate-run protection, timeout/lock behavior, and collector-run visibility before broader multi-streamer expansion
- Why: live refresh and one-streamer VOD collection are now proven, so the next highest-risk gap is operational reliability under repeated execution rather than another feature expansion

## D-024 Prioritize Multi-Streamer VOD Sweep After Guardrail Hardening

- Date: 2026-04-08
- Status: accepted
- Decision: after the first scheduler and collector-run hardening slice closes, the next live/VOD execution slice should validate multi-streamer VOD sweep behavior and mixed-result persistence before UI/admin polish
- Why: the remaining highest-value product risk is whether the reviewed one-streamer VOD path generalizes safely across multiple active streamers with mixed outcomes

## D-025 Prioritize Timeout And Backoff Hardening After Multi-Streamer Sweep

- Date: 2026-04-08
- Status: accepted
- Decision: after the first multi-streamer VOD sweep slice closes, the next live/VOD execution slice should harden timeout classification, retry or backoff behavior, and failure evidence before UI/admin polish
- Why: multi-streamer sweep correctness is now proven, so the next highest-risk gap is resilience under slower or partially failing upstream responses rather than adding more UI surface first

## D-026 Allow Small Same-Role Micro-Loops

- Date: 2026-04-08
- Status: accepted
- Decision: the workflow may keep the same specialist for up to 2 tightly related follow-up passes inside one slice when role, scope, file area, and validation method stay the same
- Why: this reduces baton overhead for tiny fixes, tests, and artifact refresh work while keeping major routing decisions visible through coordinator

## D-027 Coordinator Gate Is Mandatory Only At Meaningful Baton Changes

- Date: 2026-04-08
- Status: accepted
- Decision: coordinator checkpoints remain mandatory for role changes, review or acceptance handoff, scope changes, and user-decision points, but may be skipped between tiny same-role micro-loops
- Why: the workflow was becoming too chat-heavy relative to the amount of work completed per pass

## D-028 Coordinator Progress Line Uses ASCII Format

- Date: 2026-04-08
- Status: accepted
- Decision: coordinator user-facing replies should start with `Overall progress: XX%` sourced from `agents/board/progress.md`
- Why: this keeps the progress line stable and avoids encoding issues in workflow files

## D-029 Prioritize Collector-Run And Failure Visibility After Timeout Or Backoff Hardening

- Date: 2026-04-08
- Status: accepted
- Decision: after TASK-011 closes, the next slice should expose collector-run status, timeout class, and recent failed or skipped history in the live/VOD UI or admin-facing surface before deeper polish work
- Why: the operational evidence is now durable, but it still needs a human-visible surface so later debugging and supervised operation do not depend on raw artifact files alone

## D-030 Prioritize Restart-Persistent Backoff State After Visibility Slice

- Date: 2026-04-08
- Status: accepted
- Decision: after TASK-012 closes, the next slice should persist collector backoff state across process restarts before broader UI polish or longer-run scheduler hardening
- Why: timeout and backoff behavior is now visible, so the highest remaining operational gap is that restart currently clears retry windows and weakens supervised recovery behavior

## D-031 External Permission Blockers Pause The Workflow

- Date: 2026-04-08
- Status: accepted
- Decision: when a task is blocked by permissions, credentials, or a deployment context unavailable to the current chats, the workflow should pause that task cleanly instead of continuing to route specialists
- Why: repeated implementation or review passes cannot resolve an external permission gate and only add churn

## D-031 Prioritize Real Scheduler Mixed-Latency Hardening After Restart-Persistent Backoff

- Date: 2026-04-08
- Status: accepted
- Decision: after TASK-013 closes, the next slice should exercise the real scheduler path under mixed latency and repeated-failure conditions before pulling in publisher or ops roles
- Why: live/VOD collector behavior is now durable across restart, so the highest remaining uncertainty is longer-run scheduler behavior rather than publisher work or deployment work

## D-032 Prioritize Real Background Scheduler Lifecycle After Extracted Tick Hardening

- Date: 2026-04-08
- Status: accepted
- Decision: after TASK-014 closes, the next slice should harden and verify the actual background scheduler thread lifecycle before any publisher or ops expansion
- Why: the extracted scheduler tick is now verified, so the highest remaining operational gap is the real long-running scheduler thread lifecycle rather than publisher flow or deployment work

## D-033 Call Ops Only After In-Process Lifecycle Proof Exists

- Date: 2026-04-08
- Status: accepted
- Decision: after TASK-015 closes, the next slice should move to `ops` for external-process supervision, graceful stop signals, and runbook-oriented scheduler ownership before any publisher work
- Why: the in-process scheduler lifecycle is now proven, so `ops` becomes the first truly necessary non-summary role for deployment-shaped supervision concerns

## D-034 Prioritize Repo-Owned Launcher After External-Process Proof

- Date: 2026-04-08
- Status: accepted
- Decision: after TASK-016 closes, the next slice should stay with `ops` and harden a repo-owned scheduler launcher plus deployment-facing stop contract before returning to broader app or publisher work
- Why: external-process supervision is now proven locally, so the next highest-value operational gap is turning that pattern into repo-owned launch and stop assets that do not depend only on ad hoc manual process control

## D-035 Prioritize Supervisor-Specific Packaging After Repo-Owned Launcher

- Date: 2026-04-08
- Status: accepted
- Decision: after TASK-017 closes, the next slice should stay with `ops` and harden one supervisor-specific launcher packaging path or deployment-facing stop proof before returning to broader app or publisher work
- Why: the repo-owned launcher contract is now proven locally, so the next highest-value operational gap is proving how that contract maps into a named deployment supervisor pattern instead of leaving packaging as a purely documented future concern

## D-036 Prioritize Non-Interactive Task Scheduler Packaging After Interactive Proof

- Date: 2026-04-08
- Status: accepted
- Decision: after TASK-018 closes, the next slice should stay with `ops` and harden a non-interactive or service-account Task Scheduler packaging path before expanding to other supervisors
- Why: the interactive current-user Task Scheduler path is now proven, so the highest remaining operational gap is whether the reviewed launcher contract survives a more deployment-shaped non-interactive packaging mode

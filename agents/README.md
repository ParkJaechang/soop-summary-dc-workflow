# Agent Collaboration Workspace

This folder is a file-based collaboration layer for running multiple Codex chats with fixed roles inside VSCode.

## Goal

Use shared files as the source of truth so separate chats can:

- read the same project context
- work under a clear role
- leave handoff notes for the next role
- keep decisions and task status in one place

## Folder Map

- `roles/`: copyable role prompts and responsibilities
- `shared/`: stable project context every role should read
- `board/`: task list, decisions, ownership map, workflow health, and project progress
- `tasks/`: one folder per task with spec, status, handoff, review, and done notes
- `artifacts/`: payloads, screenshots, samples, and test evidence by task
- `scripts/`: helper scripts for scaffolding new tasks

## Recommended Read Order For Every Chat

1. `shared/project_brief.md`
2. `shared/architecture.md`
3. `shared/coding_rules.md`
4. the role file in `roles/`
5. the target task folder in `tasks/`

## Operating Loop

1. Create a new task folder from the template or with `scripts/new_task.ps1`.
2. Add the task to `board/tasks.yaml`.
3. Open the coordinator chat and paste the relevant role file.
4. The coordinator updates `spec.md` and `status.yaml`.
5. The assigned role works the task and records output in `handoff.md` or `review.md`.
6. The assigned role hands control back to the coordinator with a paste-ready next-chat prompt.
7. The coordinator summarizes deliverables, evidence, risks, and open questions for the user as a supervisor checkpoint.
8. After the user approves or adds direction, the coordinator routes the next role.
9. When the task is complete, update `done.md` and move the board entry to `done`.

## Rules That Keep This Usable

- Treat `tasks/<TASK-ID>/status.yaml` as the current source of truth.
- Put stable facts in `shared/`, task-specific facts in the task folder, and final decisions in `board/decisions.md`.
- Keep handoffs short and actionable.
- Route major baton passes through the coordinator so the user can inspect evidence before the next implementation step.
- Do not leave important instructions only in chat history.
- Prefer one task folder per real deliverable, not per conversation.
- If a role disagrees with a decision, record it in `review.md` or `decisions.md` instead of silently overriding.

## First Suggested Roles

- `coordinator`: scope, assign, accept, and route work
- `summary_engineer`: SOOP collection, transcript, summary, normalization
- `publisher_engineer`: post job generation and DC publishing pipeline
- `reviewer`: risk review, acceptance review, and regression checks
- `ops`: scripts, config, runbooks, and deployment support

## Current Bootstrap Task

The first live example is `tasks/TASK-001-collaboration-bootstrap/`.

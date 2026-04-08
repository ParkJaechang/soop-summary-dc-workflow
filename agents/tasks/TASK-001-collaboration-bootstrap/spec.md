# Task Spec

## Task ID

TASK-001

## Title

Bootstrap file-based multi-chat collaboration workspace

## Problem

Multiple Codex chats in VSCode do not share memory, so the project needs a durable structure for role prompts, shared context, handoffs, reviews, and task status.

## Scope

- create an `agents/` collaboration workspace
- add role prompts for the first operating roles
- add shared project context and operating rules
- add task board files and ownership guidance
- add a reusable task template
- add one bootstrap example task
- add a helper script for creating new task folders

## Out Of Scope

- database-backed task orchestration
- automatic synchronization between chats
- replacing app-level job storage with the collaboration folder

## Acceptance Criteria

- a new chat can read one role file and one task folder and continue work
- the workspace contains a visible board, decisions log, and ownership map
- new tasks can be scaffolded without manual copy-paste of every file
- the first task shows the intended workflow by example

## Notes

- this is the lowest-friction starting point and can later be replaced or augmented by a DB-backed board

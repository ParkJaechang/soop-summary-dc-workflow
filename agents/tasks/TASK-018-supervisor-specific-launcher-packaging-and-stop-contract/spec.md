# TASK-018 Supervisor-Specific Launcher Packaging And Stop Contract

## Goal

Prove one deployment-facing supervisor packaging path for the reviewed live/VOD launcher contract so the scheduler can be started and stopped through a named supervisor pattern instead of only ad hoc local commands.

## Scope

- add or verify one supervisor-specific launcher packaging path for the reviewed repo-owned launcher
- define the stop contract expected by that supervisor pattern
- save local evidence and runbook-shaped artifacts for that packaging path

## Out Of Scope

- summary payload changes
- publisher changes
- approval, queueing, dispatch, or browser posting
- broader UI polish
- a full cross-platform or multi-supervisor matrix

## Acceptance Criteria

1. One supervisor-specific packaging path exists for the reviewed launcher contract.
2. The packaging path documents or exercises a deployment-facing graceful stop contract.
3. Evidence shows the packaged path can start the app, observe runtime health, and stop it in a bounded way.
4. Task files record any remaining deployment-specific gaps without widening scope.

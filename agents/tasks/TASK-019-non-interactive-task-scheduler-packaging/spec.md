# TASK-019 Non-Interactive Task Scheduler Packaging

## Goal

Prove the reviewed launcher contract under a more deployment-shaped non-interactive Task Scheduler mode so the packaging path is not limited to current-user interactive semantics.

## Scope

- add or verify one non-interactive or service-account-flavored Task Scheduler packaging path for the reviewed launcher
- define the stop contract expected by that packaging mode
- save local evidence and runbook-shaped artifacts for that packaging path

## Out Of Scope

- summary payload changes
- publisher changes
- approval, queueing, dispatch, or browser posting
- broader UI polish
- alternate supervisors outside Task Scheduler

## Acceptance Criteria

1. One non-interactive or service-account-flavored Task Scheduler packaging path exists for the reviewed launcher contract.
2. The packaging path documents or exercises a deployment-facing graceful stop contract.
3. Evidence shows the packaged path can start the app, observe runtime health, and stop it in a bounded way.
4. Task files record any remaining deployment-specific gaps without widening scope.

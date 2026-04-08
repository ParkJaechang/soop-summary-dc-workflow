# TASK-017 Repo-Owned Scheduler Launcher And Stop Contract

## Goal

Turn the reviewed external-process supervision pattern into repo-owned launcher and stop-contract assets that can be operated without relying only on ad hoc manual process handling.

## Scope

- add or verify repo-owned launcher or wrapper assets for `app_live_vod.py`
- define and prove the stop contract expected by the launcher or wrapper
- save local operational evidence and runbook-shaped artifacts

## Out Of Scope

- summary payload changes
- publisher changes
- approval, queueing, dispatch, or browser posting
- broader UI polish
- cross-platform supervisor matrix beyond one reviewed local operating pattern

## Acceptance Criteria

1. A repo-owned launcher or wrapper asset exists for the reviewed live/VOD scheduler process.
2. The launcher or wrapper documents or exercises a graceful stop contract instead of requiring ad hoc manual process handling.
3. Evidence shows the launcher path can start the app, observe runtime health, and stop it in a bounded way.
4. Task files record any remaining deployment-specific gaps without widening scope.

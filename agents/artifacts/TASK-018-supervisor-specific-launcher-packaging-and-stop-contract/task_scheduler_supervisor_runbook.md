# TASK-018 Windows Task Scheduler Packaging Runbook

## Scope

This runbook covers one supervisor-specific packaging path for the reviewed live/VOD launcher: Windows Task Scheduler.

## Repo-Owned Packaging Assets

- `live_vod_scheduler_task_action.ps1`
- `install_live_vod_scheduler_task.ps1`
- `run_live_vod_scheduler_task.ps1`
- `status_live_vod_scheduler_task.ps1`
- `stop_live_vod_scheduler_task.ps1`
- `remove_live_vod_scheduler_task.ps1`

## Register The Task

```powershell
.\install_live_vod_scheduler_task.ps1
```

Optional arguments:

- `-TaskName <name>`
- `-RuntimeDir <path>`
- `-DbPath <path>`
- `-Port <port>`
- `-HealthTimeout <seconds>`

## Start Through The Supervisor Path

```powershell
.\run_live_vod_scheduler_task.ps1
```

This starts the registered Task Scheduler entry on demand and waits for the repo-owned launcher health path.

## Inspect Runtime Health

```powershell
.\status_live_vod_scheduler_task.ps1
```

This returns both scheduled-task metadata and launcher `/api/health` status for the configured runtime directory.

## Deployment-Facing Graceful Stop Contract

```powershell
.\stop_live_vod_scheduler_task.ps1 -TimeoutSeconds 10
```

- Do not use `End-ScheduledTask` for normal shutdown because it bypasses the host-side graceful stop path.
- The task stop wrapper delegates to the repo-owned launcher stop contract, which writes `stop_requested.json` inside the task runtime directory.
- The host wrapper observes that stop file and returns cleanly after joining the scheduler thread.

## Cleanup

```powershell
.\remove_live_vod_scheduler_task.ps1
```

## Verified Local Evidence

- the Task Scheduler path registered a named task and exported its task definition
- the packaged path started the app and reached `/api/health`
- the deployment-facing stop wrapper stopped the host in a bounded way without using forced task termination
- collector runs, live state, and VOD rows were still persisted through the packaged path

## Remaining Deployment Gaps

- this slice proves one Windows Task Scheduler pattern only; NSSM or Windows Service packaging can be a later ops slice if needed
- the verified task principal is current-user interactive-token based, so service-account or machine-start semantics remain later deployment-specific work
- non-Windows supervisor packaging remains out of scope

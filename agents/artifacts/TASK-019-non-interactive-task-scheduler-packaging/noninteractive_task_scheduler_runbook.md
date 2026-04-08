# TASK-019 Non-Interactive Task Scheduler Runbook

## Scope

This runbook covers one non-interactive Task Scheduler packaging path for the reviewed live/VOD launcher: current-user S4U XML registration.

## Packaging Asset

- `install_live_vod_scheduler_task_noninteractive.ps1`
- existing repo-owned task wrappers: `run_live_vod_scheduler_task.ps1`, `status_live_vod_scheduler_task.ps1`, `stop_live_vod_scheduler_task.ps1`, `remove_live_vod_scheduler_task.ps1`

## Register The Non-Interactive Task

```powershell
.\install_live_vod_scheduler_task_noninteractive.ps1
```

Optional arguments:

- `-TaskName <name>`
- `-TaskUser <DOMAIN\user>`
- `-RuntimeDir <path>`
- `-DbPath <path>`
- `-Port <port>`
- `-HealthTimeout <seconds>`
- `-TaskXmlPath <path>`

## Start, Status, And Graceful Stop

```powershell
.\run_live_vod_scheduler_task.ps1 -TaskName <name> -RuntimeDir <path> -DbPath <path>
.\status_live_vod_scheduler_task.ps1 -TaskName <name> -RuntimeDir <path> -DbPath <path>
.\stop_live_vod_scheduler_task.ps1 -TaskName <name> -RuntimeDir <path> -DbPath <path> -TimeoutSeconds 10
```

- Keep using the repo-owned stop wrapper for normal shutdown.
- Do not use `End-ScheduledTask` for normal shutdown because it bypasses the launcher stop-request-file contract.

## Packaging Mode

- registration mode: `xml_s4u_current_user_noninteractive`
- Task Scheduler logon type: `S4U`
- intended shape: no interactive desktop dependency and no stored password in the repo-owned packaging asset

## Local Verification Notes

- local verification in this medium-integrity session hit `Access is denied` during S4U task registration
- the packaging asset and task XML were still generated and saved as evidence
- a deployment context with elevated Task Scheduler rights or an approved credentialed supervisor is required to finish the start/health/stop proof for this mode

## Remaining Deployment Gaps

- if S4U registration remains blocked in the target environment, the next deployment-shaped alternative is an approved service account or elevated supervisor-owned task registration process
- alternate supervisors outside Task Scheduler remain out of scope

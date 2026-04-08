# TASK-017 Repo-Owned Scheduler Launcher Runbook

## Scope

This runbook covers the repo-owned launcher and stop contract for `app_live_vod.py`.

## Repo-Owned Assets

- `live_vod_scheduler_launcher.py`
- `live_vod_scheduler_host.py`
- `start_live_vod_scheduler.bat`
- `status_live_vod_scheduler.bat`
- `stop_live_vod_scheduler.bat`

## Start Command

```powershell
start_live_vod_scheduler.bat
```

Optional launcher arguments:

- `--runtime-dir <path>`
- `--db-path <path>`
- `--port <port>`
- `--wait-health`
- `--health-timeout <seconds>`

## Status Command

```powershell
status_live_vod_scheduler.bat
```

This reports launcher state plus `/api/health` when the process is alive.

## Graceful Stop Contract

```powershell
stop_live_vod_scheduler.bat --timeout 10
```

- The stop command writes `stop_requested.json` into the launcher runtime directory.
- The repo-owned host wrapper polls for that file and sets `uvicorn` graceful exit internally.
- This avoids relying on ad hoc console control or manual Task Manager termination.

## Runtime Files

- `launcher_state.json`
- `stop_requested.json`
- `host_runtime_summary.json`
- `launcher_stdout.log`
- `launcher_stderr.log`

## Verified Local Evidence

- launcher path started the app and reached `/api/health`
- scheduler persisted collector runs, live state, and VOD rows through the launcher path
- launcher stop completed in a bounded window and the host runtime summary showed `thread_alive=false` and `started=false`

## Remaining Deployment Gaps

- a later slice can add supervisor-specific packaging if deployment requires a Windows service, NSSM, or another process manager
- broader non-Windows launcher and stop-contract coverage remains out of scope for this slice

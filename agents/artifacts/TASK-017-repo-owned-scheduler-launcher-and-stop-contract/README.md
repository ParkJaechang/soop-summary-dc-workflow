# TASK-017 Artifacts

Artifacts for repo-owned scheduler launcher and graceful-stop contract hardening.

## Main Evidence

- `verify_repo_owned_scheduler_launcher.py`
  runs the repo-owned launcher path end to end against a local fixture server and temp SQLite DB
- `launcher_process_evidence.json`
  compact summary of launcher start, status, stop, bounded shutdown, and durable persistence
- `launcher_health_trace.json`
  health snapshots showing the launched process reached scheduler activity before stop
- `launcher_status_before_stop.json`
  saved output of the repo-owned `status` command before graceful stop
- `launcher_stop_result.json`
  saved output of the repo-owned `stop` command including bounded stop duration
- `collector_runs_after_launcher.json`
  durable collector-run rows produced by the launcher-driven process
- `live_state_after_launcher.json`
  persisted live-state rows from the launcher-driven process
- `vod_rows_after_launcher.json`
  persisted VOD rows from the launcher-driven process
- `repo_owned_scheduler_launcher_runbook.md`
  operator-facing start, status, stop, and runtime-file guidance
- `repo_owned_scheduler_launcher_notes.txt`
  short human-readable summary for coordinator and reviewer
- `launcher_runtime/host_runtime_summary.json`
  child-side final runtime summary showing the stop-request contract and final scheduler state
- `launcher_runtime/stop_requested.json`
  concrete stop-contract file written by the repo-owned launcher

## Repo-Owned Assets Proven In This Slice

- `live_vod_scheduler_launcher.py`
- `live_vod_scheduler_host.py`
- `start_live_vod_scheduler.bat`
- `status_live_vod_scheduler.bat`
- `stop_live_vod_scheduler.bat`

## Notes

- the repo-owned stop contract no longer depends on ad hoc manual Task Manager termination
- the verified local launcher path uses a runtime-directory stop-request file that the host wrapper converts into graceful `uvicorn` shutdown
- broader supervisor packaging and non-Windows launch or stop coverage remain later-slice work

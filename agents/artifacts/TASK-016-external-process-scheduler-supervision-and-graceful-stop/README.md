# TASK-016 Artifacts

External-process scheduler supervision and graceful-stop evidence for `app_live_vod.py`.

## Main Evidence

- `verify_external_scheduler_supervision.py`
  ops-owned verifier that launches the live/VOD app in a separate Python process, waits for scheduler activity, and then requests graceful stop
- `external_scheduler_child.py`
  deterministic child wrapper that configures a temp DB, fake upstream responses, and shutdown summary capture for the external-process run
- `external_scheduler_process_evidence.json`
  compact proof of external-process startup, bounded stop duration, clean exit, and post-exit scheduler state
- `external_scheduler_health_trace.json`
  health snapshots showing a live scheduler thread and collector-run growth before stop
- `external_scheduler_fetch_trace.json`
  raw upstream-call trace captured by the child process during scheduler activity
- `external_scheduler_child_runtime_summary.json`
  final child-side runtime summary written after uvicorn returned from graceful shutdown
- `collector_runs_after_external_process.json`
  durable collector-run rows produced before graceful stop
- `live_state_after_external_process.json`
  persisted live-state rows from the supervised child process
- `vod_rows_after_external_process.json`
  persisted VOD rows from the supervised child process
- `external_scheduler_service_runbook.md`
  service-style ownership notes for start, health checks, graceful stop, and remaining deployment dependencies
- `external_scheduler_verification_notes.txt`
  short human-readable summary for coordinator and reviewer

## Notes

- the verified Windows stop pattern used `CTRL_BREAK_EVENT` against a dedicated process group
- the child process exited in a bounded window and wrote a shutdown summary with `thread_alive=false` and `started=false`
- later deployment hardening may still need a repo-owned launcher or a supervisor-specific stop contract

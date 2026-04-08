# TASK-016 External Scheduler Service Runbook

## Scope

This runbook covers service-style ownership for `app_live_vod.py` as an externally supervised process.

## Proven Local Supervision Pattern

1. Start the app as its own Python process.
2. Wait for `GET /api/health` to report a live scheduler thread.
3. Use `GET /api/jobs` and `GET /api/admin/collector-visibility` for runtime visibility.
4. Stop the process with a graceful console-break style signal first, not a hard kill.
5. Confirm bounded shutdown by checking process exit time plus scheduler state in the saved runtime summary.

## Verified Local Command Shape

```powershell
python app_live_vod.py
```

The verifier for this task used a dedicated child wrapper to keep DB path, fake upstream responses, and artifact logging deterministic:

```powershell
python agents/artifacts/TASK-016-external-process-scheduler-supervision-and-graceful-stop/verify_external_scheduler_supervision.py
```

## Health Checks

- `GET /api/health`
  confirms DB reachability plus scheduler thread state
- `GET /api/jobs`
  confirms collector runs are being written
- `GET /api/admin/collector-visibility`
  confirms recent status and backoff visibility

## Graceful Stop Expectation

- On Windows, prefer sending `CTRL_BREAK_EVENT` to a dedicated process group.
- Treat hard terminate as a fallback only when graceful stop times out.
- A bounded stop is considered proven when the process exits within the configured wait window and the final scheduler snapshot shows `thread_alive=false` and `started=false`.

## Evidence Files

- `external_scheduler_process_evidence.json`
- `external_scheduler_health_trace.json`
- `external_scheduler_fetch_trace.json`
- `external_scheduler_child_runtime_summary.json`
- `collector_runs_after_external_process.json`
- `live_state_after_external_process.json`
- `vod_rows_after_external_process.json`
- `external_scheduler_verification_notes.txt`

## Remaining Dependencies

- A later product-hardening slice can add a repo-owned launcher or service wrapper if deployment moves beyond ad hoc Python process supervision.
- If the production supervisor cannot emit a graceful stop signal equivalent to the verified local pattern, that integration needs its own stop-contract evidence.


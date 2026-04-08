# TASK-018 Artifacts

Windows Task Scheduler packaging evidence for the reviewed live/VOD scheduler launcher.

## Key Evidence

- `task_scheduler_process_evidence.json`
- `task_scheduler_registration.json`
- `task_scheduler_definition.xml`
- `task_scheduler_run_result.json`
- `task_scheduler_status_before_stop.json`
- `task_scheduler_stop_result.json`
- `task_scheduler_host_runtime_summary.json`
- `task_scheduler_health_trace.json`
- `collector_runs_after_task_scheduler.json`
- `live_state_after_task_scheduler.json`
- `vod_rows_after_task_scheduler.json`
- `task_scheduler_supervisor_runbook.md`
- `task_scheduler_supervisor_notes.txt`

## Verification Command

```powershell
python agents/artifacts/TASK-018-supervisor-specific-launcher-packaging-and-stop-contract/verify_task_scheduler_packaging.py
```

## Scope Notes

- the selected supervisor-specific path is Windows Task Scheduler
- the verified stop contract is `stop_live_vod_scheduler_task.ps1`, not `End-ScheduledTask`
- current-user interactive task registration is in scope for this slice
- alternate supervisors and service-account packaging remain later deployment slices

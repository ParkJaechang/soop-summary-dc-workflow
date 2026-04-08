# TASK-015 Artifacts

Background scheduler thread lifecycle evidence for `app_live_vod.py`.

## Main Evidence

- `verify_background_scheduler_lifecycle.py`
  drives the real FastAPI startup/shutdown path with `TestClient` and a temp SQLite DB
- `background_scheduler_health_trace.json`
  per-session health snapshots proving startup, sustained ticking, and restart
- `background_scheduler_fetch_trace.json`
  raw upstream-call trace used to show bounded execution and no post-shutdown fetch growth
- `collector_runs_after_background_thread.json`
  durable `collector_runs` rows produced by the real background thread path
- `live_state_after_background_thread.json`
  persisted live-state row after scheduler-driven refresh
- `vod_rows_after_background_thread.json`
  persisted VOD rows after scheduler-driven refresh
- `background_scheduler_lifecycle_evidence.json`
  compact lifecycle summary including clean-stop and restart checks
- `background_scheduler_verification_notes.txt`
  short human-readable summary for coordinator and reviewer

## Notes

- verification stayed inside one local Python process using real FastAPI lifespan hooks
- deployment-level service supervision and external process signal handling remain later-slice work

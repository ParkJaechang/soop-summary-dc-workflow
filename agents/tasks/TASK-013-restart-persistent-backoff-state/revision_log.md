# Revision Log

- 2026-04-08 | summary_engineer | Added SQLite-backed `collector_backoffs` persistence and restart hydration in `app_live_vod.py`, then saved restart recovery evidence under `agents/artifacts/TASK-013-restart-persistent-backoff-state`
- 2026-04-08 | coordinator | Created TASK-013 after TASK-012 closeout to persist collector backoff windows across process restarts
- 2026-04-08 | coordinator | Closed TASK-013 after reviewer confirmed the restart-persistent backoff slice was acceptance-ready
- 2026-04-08 | coordinator | Reviewed the saved restart-persistent backoff evidence and routed TASK-013 to reviewer
- 2026-04-08 | reviewer | Confirmed that saved TASK-013 evidence proves persisted retry-window rows, restored skip behavior after restart, bounded upstream pressure, and later successful recovery for both live and one-streamer VOD paths; moved the task to `ready_for_acceptance`

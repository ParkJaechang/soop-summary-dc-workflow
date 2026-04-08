# TASK-012 Artifacts

This folder stores local evidence for the collector-run and failure-visibility UI/admin slice.

Saved artifacts:
- `collector_visibility_during_backoff.json`
  admin snapshot while live and VOD backoff windows are active
- `collector_visibility_after_recovery.json`
  admin snapshot after both paths recover and complete
- `jobs_api_after_visibility.json`
  enriched `/api/jobs` output with parsed message information and streamer labels
- `collector_runs_db_snapshot.json`
  raw `collector_runs` snapshot used to compare against the surfaced admin data
- `recent_state_after_visibility.json`
  persisted `streamer_live_state`, `vods`, and `/api/streamers` or `/api/streamers/{id}/vods` outputs after recovery
- `ui_visibility_markup_checks.json`
  markup checks proving the dashboard contains the new visibility panel wiring
- `collector_visibility_verification_notes.txt`
  concise verification summary for the slice

Verification shape:
- during backoff:
  admin snapshot shows 2 active backoffs, 2 failed runs, and 2 skipped runs
- after recovery:
  admin snapshot shows 0 active backoffs and 2 completed recovery runs
- persistence match:
  surfaced recent runs match `collector_runs`, and surfaced recent state matches persisted live and VOD rows

# TASK-011 Artifacts

This folder stores local evidence for the collector timeout and backoff hardening slice.

Saved artifacts:
- `timeout_backoff_fixture_notes.json`
  fixture settings, fetch-call markers, and the note that each path was exercised as fail once -> backoff skip -> delayed success
- `live_timeout_backoff_results.json`
  `POST /api/live/refresh` results for failed, skipped, and completed attempts
- `vod_timeout_backoff_results.json`
  `POST /api/streamers/{id}/vods/refresh` results for failed, skipped, and completed attempts
- `collector_runs_after_timeout_backoff.json`
  durable collector-run visibility for failed, skipped, and completed rows
- `live_state_after_timeout_backoff.json`
  final live-state persistence after the backoff window expires
- `vod_rows_after_timeout_backoff.json`
  final normalized VOD persistence after the backoff window expires
- `timeout_backoff_verification_notes.txt`
  concise verification summary with status-code and fetch-marker counts

Verification shape:
- live path:
  first call failed with a timeout-classified message, second call skipped under backoff, third call completed
- VOD path:
  first call failed with a timeout-classified message, second call skipped under backoff, third call completed
- bounded failure proof:
  fetch-call markers do not increase during the immediate backoff-skipped attempts
- durable visibility:
  `collector_runs` stores failed, skipped, and completed rows for both collector paths

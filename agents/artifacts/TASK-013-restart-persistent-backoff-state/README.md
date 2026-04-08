# TASK-013 Artifacts

This folder stores local evidence for restart-persistent collector backoff state.

Saved artifacts:
- `restart_backoff_evidence.json`
  full end-to-end restart simulation showing failed, persisted, skipped-after-restart, and completed-after-wait states
- `collector_backoff_rows_before_restart.json`
  persisted `collector_backoffs` rows immediately after timeout failures
- `collector_backoff_rows_after_recovery.json`
  empty `collector_backoffs` snapshot after the backoff window expires and recovery succeeds
- `collector_runs_after_restart_recovery.json`
  durable collector-run visibility for failed, skipped, and completed rows across the restart simulation
- `recent_state_after_restart_recovery.json`
  final `streamers` and VOD API-visible state after recovery
- `restart_backoff_verification_notes.txt`
  concise summary of persisted rows, call counts, and recovery outcome

Verification shape:
- before restart:
  2 persisted backoff rows exist for `live:global` and `vod:streamer:1`
- after simulated restart:
  active backoff count remains 2 and immediate re-entry is skipped
- bounded skip proof:
  live and VOD fetch-call counts do not increase during the immediate post-restart skip
- after backoff expiry:
  both collectors complete successfully and persisted backoff rows are cleared

Save restart-persistence evidence for collector backoff windows here.

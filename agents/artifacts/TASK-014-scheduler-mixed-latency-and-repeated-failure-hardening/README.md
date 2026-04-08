# TASK-014 Artifacts

This folder stores local evidence for scheduler-path mixed-latency and repeated-failure hardening.

Saved artifacts:
- `verify_scheduler_hardening.py`
  reproducible local verifier that drives the scheduler loop body through mixed-latency and repeated-failure ticks
- `scheduler_tick_trace.json`
  per-tick results, durations, fetch deltas, and collector-run counts
- `scheduler_fetch_pressure_trace.json`
  raw live and VOD fetch-call timestamps plus tick-level pressure deltas
- `collector_runs_after_scheduler_hardening.json`
  durable `collector_runs` rows produced by the scheduler-driven trace
- `collector_backoffs_after_scheduler_hardening.json`
  final persisted backoff rows after the scheduler trace
- `recent_state_after_scheduler_hardening.json`
  final collector visibility snapshot plus persisted live and VOD rows
- `scheduler_hardening_verification_notes.txt`
  concise summary of tick counts, fetch counts, and bounded-pressure evidence

Verification shape:
- mixed latency:
  slow live collector execution runs through the scheduler path without causing an immediate catch-up rerun on the next tick
- repeated failure:
  VOD fails on two separate scheduled ticks with durable failed rows in `collector_runs`
- bounded skip:
  the first backoff-active tick adds 0 live fetches and 0 VOD fetches
- recovery:
  later ticks recover and leave completed live/VOD rows plus no remaining persisted backoff rows

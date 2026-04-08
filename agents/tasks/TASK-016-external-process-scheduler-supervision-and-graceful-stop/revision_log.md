# Revision Log

- 2026-04-08 | coordinator | Created TASK-016 after TASK-015 closeout to harden external-process supervision and graceful stop behavior
- 2026-04-08 | ops | Added an external-process verifier and child wrapper for `app_live_vod.py`, saved bounded-shutdown evidence plus a service-style runbook under TASK-016 artifacts, and handed the slice back to coordinator for checkpoint
- 2026-04-08 | coordinator | Confirmed the saved external-process evidence satisfies TASK-016 supervisor-checkpoint scope and routed the slice to reviewer
- 2026-04-08 | coordinator | Closed TASK-016 after reviewer acceptance and opened TASK-017 for repo-owned launcher and deployment-facing stop-contract hardening
- 2026-04-08 | reviewer | Confirmed that saved TASK-016 evidence proves bounded shutdown, clean external-process exit, and service-style runbook coverage; moved the task to `ready_for_acceptance`

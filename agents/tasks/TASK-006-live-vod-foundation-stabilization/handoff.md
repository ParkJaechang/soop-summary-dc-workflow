# Handoff

## Latest Update

- Summary: TASK-006 is closed. Reviewer confirmed the saved live/VOD foundation evidence, and coordinator accepted the slice as complete for foundation scope.
- Next owner: none
- Read first: `agents/tasks/TASK-006-live-vod-foundation-stabilization/done.md`
- Remaining work: no further work inside TASK-006. Follow-up hardening remains for later live/VOD slices.

## Notes

- Primary implementation target for this slice:
  `app_live_vod.py`
- Supporting references:
  `docs/SOOP_LIVE_VOD_IMPLEMENTATION_PLAN.md`
  `docs/SOOP_LIVE_VOD_WEBAPP_ARCHITECTURE.md`
- Do not reopen summary payload or publisher draft scope in this task.
- Keep this slice focused on the live/VOD foundation only:
  schema, registered streamers, and basic CRUD behavior.
- What changed:
  `init_db()` now ensures the optional `vods.duration_seconds` baseline column exists on older local DBs, and the foundation slice was verified with local CRUD evidence.
- Evidence:
  `agents/artifacts/TASK-006-live-vod-foundation-stabilization/foundation_verification_notes.txt`
  `agents/artifacts/TASK-006-live-vod-foundation-stabilization/schema_snapshot.json`
  `agents/artifacts/TASK-006-live-vod-foundation-stabilization/crud_api_results.json`
  `agents/artifacts/TASK-006-live-vod-foundation-stabilization/db_rows_after_crud.json`
- Final reviewer outcome:
  no blocking findings remain. The saved evidence was sufficient for acceptance of the live/VOD foundation slice.

## Remaining Dependencies For Later Slices

- Live refresh slice still depends on:
  official SOOP API hardening, stale/offline transition checks, and collector-run failure visibility under real refresh calls
- VOD collector slice still depends on:
  parser hardening, stable `published_at` normalization, and writing `duration_seconds` alongside or instead of the current `duration_text`
- Scheduler/ops slice still depends on:
  explicit lock behavior verification, timeout/backoff policy checks, and startup/shutdown runbook evidence
- UI-facing slice still depends on:
  dashboard verification against stored rows after more than one registered streamer exists

## Foundation Contract Confirmed In This Slice

- `streamers` table exists with:
  `soop_user_id`, `nickname`, `channel_url`, `replay_url`, `category_no`, `active`, timestamps
- `streamer_live_state` baseline row is created when a streamer is registered
- `GET /api/streamers` returns registered rows plus `live_state` and `latest_vod`
- `POST /api/streamers` creates a streamer and auto-fills canonical `channel_url` when omitted
- `PATCH /api/streamers/{id}` updates the tracked streamer record
- `DELETE /api/streamers/{id}` performs soft deactivation by setting `active = 0`
- `vods.duration_seconds` now exists as an optional baseline column for later collector population

## Paste-Ready Next Chat Prompt

No next-chat baton is attached to TASK-006 because the task is closed. The next step is to create a new task from coordinator based on overall board priority.

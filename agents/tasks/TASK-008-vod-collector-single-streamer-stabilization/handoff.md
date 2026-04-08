# Handoff

## Latest Update

- Summary: TASK-008 is closed. Reviewer confirmed the saved one-streamer VOD evidence, and coordinator accepted the slice as complete for one-streamer VOD collection scope.
- Next owner: none
- Read first: `agents/tasks/TASK-008-vod-collector-single-streamer-stabilization/done.md`
- Remaining work: no further work inside TASK-008. Follow-up scheduler and collector-run hardening continues in TASK-009.

## Notes

- Primary implementation target for this slice:
  `app_live_vod.py`
- Supporting references:
  `docs/SOOP_LIVE_VOD_IMPLEMENTATION_PLAN.md`
  `docs/SOOP_LIVE_VOD_WEBAPP_ARCHITECTURE.md`
- Do not reopen summary payload or publisher draft scope in this task.
- Keep this slice focused on one tracked-streamer VOD collection only:
  source parsing, normalized `vods` persistence, API-visible results, and `collector_runs` visibility.
- Reuse the reviewed foundation and live refresh slices rather than reworking streamer CRUD or live refresh unless a blocking bug is discovered.
- What changed:
  `parse_vod_items()` now isolates each matched VOD anchor block instead of scanning too far backward into the previous card, which prevents title/thumbnail/published-at bleed between adjacent VOD items.
- Evidence:
  `agents/artifacts/TASK-008-vod-collector-single-streamer-stabilization/vod_source_fixture.html`
  `agents/artifacts/TASK-008-vod-collector-single-streamer-stabilization/vod_collection_api_results.json`
  `agents/artifacts/TASK-008-vod-collector-single-streamer-stabilization/vod_rows_after_collection.json`
  `agents/artifacts/TASK-008-vod-collector-single-streamer-stabilization/collector_runs_after_vod_collection.json`
- Final reviewer outcome:
  no blocking findings remained. The saved evidence was sufficient for acceptance of the one-streamer VOD collection slice.

## Remaining Dependencies For Later Slices

- Broader VOD hardening still depends on:
  more fixture coverage for alternate SOOP replay layouts, duplicate-update behavior over repeated runs, and clearer `published_at` normalization rules when pages expose relative timestamps
- Multi-streamer VOD sweep still depends on:
  verification of `collect_vods_for_all()` behavior across mixed success/failure cases
- Scheduler hardening still depends on:
  repeated-run timing checks, per-streamer lock contention evidence, and startup/shutdown execution behavior
- Optional fallback hardening still open later:
  browser fallback verification if the HTML-only path fails on real pages

## VOD Collection Contract Confirmed In This Slice

- `POST /api/streamers/{id}/vods/refresh`
  runs the one-streamer VOD collection path
- `candidate_station_urls(...)`
  selects replay/channel candidates for the tracked streamer
- `parse_vod_items(...)`
  extracts normalized `vod_id`, `title`, `vod_url`, `thumbnail_url`, `published_at`, and `duration_text`
- `collect_vods_for_streamer(...)`
  persists rows into `vods` by `vod_url` identity and records collector status
- `GET /api/streamers/{id}/vods`
  exposes collected rows through the current API surface

## Paste-Ready Next Chat Prompt

No next-chat baton is attached to TASK-008 because the task is closed. Follow-up scheduler and collector-run work continues in TASK-009.

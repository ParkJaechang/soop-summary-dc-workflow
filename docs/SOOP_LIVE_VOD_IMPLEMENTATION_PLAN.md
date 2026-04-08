# SOOP Live + VOD WebApp Implementation Plan

## Phase 1: Foundation
- create a new FastAPI entry file such as `app_live_vod.py`
- add SQLite initialization and schema creation
- add `streamers`, `streamer_live_state`, `live_snapshots`, `vods`, `collector_runs` tables
- implement `GET/POST/PATCH/DELETE /api/streamers`
- build a simple dashboard HTML file at `webapp/live_vod.html`

## Phase 2: Live Collector
- add SOOP Open API client for `broad/list`
- implement global live refresh endpoint
- map tracked `soop_user_id` values to live results
- save current live state and append live snapshots
- show live badges and timestamps in UI

## Phase 3: VOD Collector
- define parser interface returning normalized VOD items
- implement HTML-based VOD page collector first
- add Playwright fallback collector only if needed
- upsert new VODs by `vod_id` or normalized `vod_url`
- expose `GET /api/streamers/{id}/vods` and refresh endpoints

## Phase 4: Scheduling and Operations
- add in-process scheduler for live and VOD refresh
- add duplicate-run locks and timeouts
- log collector runs and failures in `collector_runs`
- surface recent runs in UI or debug panel

## Phase 5: Hardening
- add search, filters, pagination
- add webhook notifications for new live and new VOD events
- move from SQLite to PostgreSQL if scale requires it
- split monolithic file into `api`, `services`, `collectors`, and `repositories`

## Immediate Next Coding Tasks
1. create DB schema and streamer CRUD
2. add live refresh using official SOOP API
3. build a dashboard page wired to those endpoints
4. implement one-streamer VOD scraping and persistence
5. generalize VOD collection to all active streamers

# SOOP Live + VOD WebApp Architecture

## 1. Goal
Build a web app that:
- tracks whether registered SOOP streamers are live now
- collects replay/VOD links automatically
- shows recent live status and VOD lists in one UI
- supports later expansion to alerts, downloads, and summarization

This document is for an MVP-first implementation that fits the current Python/FastAPI-based workspace.

## 2. Product Scope

### In Scope for MVP
- register and manage a list of SOOP streamers
- check current live status on a schedule
- collect recent VOD/replay links for each streamer
- store normalized results in a database
- expose a web UI for search, filtering, and detail viewing
- provide a manual refresh action per streamer

### Out of Scope for MVP
- account login on behalf of SOOP users
- playback embedding that depends on protected/private content
- mass crawling across all SOOP channels
- video download/transcode
- push notifications beyond a simple webhook hook point

## 3. Constraints and Assumptions

### Confirmed
- SOOP Open API provides live broadcast listing via `GET /broad/list`.
- SOOP Open API provides category listing via `GET /broad/category/list`.
- SOOP Open API provides VOD embed metadata via `GET/POST /oembed/embedinfo`, but not an obvious public "list all VODs for this streamer" endpoint in the public docs reviewed.

### Assumptions
- live status should use the official Open API whenever possible
- VOD list collection will likely require page parsing or browser automation unless a hidden but stable endpoint is discovered during implementation
- VOD collection must be isolated behind an adapter so selector or page changes do not leak into the rest of the system

## 4. Recommended Architecture

### Stack
- Backend: `FastAPI`
- Frontend: server-served SPA or static `index.html` with vanilla JS for MVP
- Database: `SQLite` for MVP, `PostgreSQL` when multi-user or larger history is needed
- Scheduler: in-process scheduler for MVP, later `APScheduler` or `Celery/BullMQ`
- Collector tools:
  - official API client for live status
  - `httpx + BeautifulSoup/lxml` for static VOD pages
  - `Playwright` fallback for JS-rendered pages

### High-Level Components
1. `api`
   - serves UI data
   - accepts streamer management actions
   - triggers refresh jobs
2. `live_collector`
   - queries official SOOP live API
   - updates current live state and history snapshots
3. `vod_collector`
   - resolves streamer channel/replay pages
   - extracts VOD identifiers and links
   - upserts only new items
4. `scheduler`
   - runs periodic live and VOD refresh jobs
   - avoids duplicate concurrent jobs per streamer
5. `storage`
   - normalized database tables
   - repository/service layer
6. `frontend`
   - dashboard for streamers, live cards, replay table, filters, refresh controls

## 5. Data Flow

### Live Check Flow
1. Scheduler runs every 2 minutes.
2. Backend calls SOOP `broad/list` with configured filters or scans pages until tracked streamers are matched.
3. Matching broadcast rows are mapped by `user_id`.
4. Current streamer state is updated:
   - `is_live = true`
   - `current_broad_no`
   - `live_title`
   - `viewer_count`
   - `last_live_seen_at`
5. A live snapshot row is inserted for history.
6. Streamers missing from the latest result set are marked offline with `last_checked_at`.

### VOD Collection Flow
1. Scheduler runs every 10 to 30 minutes.
2. Collector opens each streamer's replay/VOD page.
3. Parser extracts:
   - `vod_id`
   - `title`
   - `vod_url`
   - `thumbnail_url`
   - `published_at`
4. New records are upserted by unique `vod_id` or normalized `vod_url`.
5. Optional metadata enrichment runs through `oembed/embedinfo`.
6. The UI refreshes from stored data, not from live scraping.

## 6. Proposed Database Schema

### `streamers`
Registered targets.

| column | type | notes |
| --- | --- | --- |
| id | integer pk | local id |
| soop_user_id | text unique | SOOP channel/user id |
| nickname | text | display name |
| channel_url | text | optional canonical channel URL |
| replay_url | text | optional replay page URL override |
| category_no | text null | optional tracking category |
| active | boolean | default true |
| created_at | datetime | |
| updated_at | datetime | |

### `streamer_live_state`
One current row per streamer.

| column | type | notes |
| --- | --- | --- |
| streamer_id | integer pk/fk | one-to-one |
| is_live | boolean | |
| broad_no | text null | current live broadcast no |
| live_title | text null | |
| viewer_count | integer null | |
| started_at | datetime null | |
| last_checked_at | datetime | |
| last_live_seen_at | datetime null | |
| raw_json | text null | debug payload |

### `live_snapshots`
History for charts/auditing.

| column | type | notes |
| --- | --- | --- |
| id | integer pk | |
| streamer_id | integer fk | |
| is_live | boolean | |
| broad_no | text null | |
| live_title | text null | |
| viewer_count | integer null | |
| checked_at | datetime | indexed |

### `vods`
Normalized replay entries.

| column | type | notes |
| --- | --- | --- |
| id | integer pk | |
| streamer_id | integer fk | |
| vod_id | text | unique when available |
| title | text | |
| vod_url | text unique | normalized canonical URL |
| thumbnail_url | text null | |
| published_at | datetime null | |
| duration_seconds | integer null | optional |
| collected_at | datetime | |
| last_seen_at | datetime | |
| raw_json | text null | debug payload |

### `collector_runs`
Operational visibility.

| column | type | notes |
| --- | --- | --- |
| id | integer pk | |
| collector_type | text | `live` or `vod` |
| streamer_id | integer null | null for global live sweep |
| status | text | `running`, `completed`, `failed` |
| started_at | datetime | |
| finished_at | datetime null | |
| message | text null | |

## 7. Backend Module Layout

Recommended new package:

```text
app/
  main.py
  api/
    streamers.py
    live.py
    vods.py
    jobs.py
  core/
    config.py
    db.py
    scheduler.py
  models/
    streamer.py
    live_state.py
    live_snapshot.py
    vod.py
    collector_run.py
  services/
    streamer_service.py
    live_service.py
    vod_service.py
  collectors/
    soop_live_api.py
    soop_vod_scraper.py
    soop_vod_playwright.py
  parsers/
    vod_page_parser.py
  repositories/
    streamer_repo.py
    live_repo.py
    vod_repo.py
```

For the current workspace, this can start as `soop_live_vod_webapp.py` and later be split into modules once the flow is verified.

## 8. API Design

### Streamers
- `GET /api/streamers`
  - list registered streamers with current live status and latest VOD summary
- `POST /api/streamers`
  - add streamer by `soop_user_id`, optional nickname and replay URL
- `PATCH /api/streamers/{id}`
  - update nickname, URLs, active flag
- `DELETE /api/streamers/{id}`
  - soft-delete or deactivate

### Live
- `GET /api/live`
  - list currently live streamers only
- `POST /api/live/refresh`
  - run global live refresh
- `POST /api/streamers/{id}/live/refresh`
  - run single-streamer refresh where supported

### VOD
- `GET /api/vods`
  - query params: `streamer_id`, `q`, `page`, `limit`, `from`, `to`
- `GET /api/streamers/{id}/vods`
  - latest VODs for one streamer
- `POST /api/vods/refresh`
  - run VOD collection for all active streamers
- `POST /api/streamers/{id}/vods/refresh`
  - run VOD collection for one streamer

### Jobs/Health
- `GET /api/jobs`
  - recent collector runs
- `GET /api/health`
  - DB and scheduler health

## 9. Frontend Screen Design

### Main Dashboard
- top summary cards:
  - tracked streamers
  - currently live
  - VODs collected today
  - last refresh status
- left pane: streamer list
- right pane: selected streamer detail

### Streamer List
Each row shows:
- nickname / `soop_user_id`
- live badge
- current title if live
- latest VOD publish time
- actions: `Refresh Live`, `Refresh VOD`, `Open Channel`

### Streamer Detail
- current live panel
- latest 20 VODs table
- collector status
- source URLs and debug metadata

### VOD Table Columns
- title
- publish date
- link
- thumbnail
- collected at

## 10. Scheduling Policy

### MVP Defaults
- live sweep: every 2 minutes
- VOD sweep: every 15 minutes
- manual refresh: allowed, but deduplicated if a job is already running

### Guardrails
- per-streamer lock for VOD collection
- global lock for live sweep
- timeout per collector run
- exponential backoff on repeated failure
- store last success/failure for visibility

## 11. VOD Collection Strategy

### Preferred Order
1. official/public endpoint if later discovered and documented
2. static HTML fetch and parse
3. browser automation with Playwright

### Parser Contract
The VOD parser should return:

```json
{
  "source_url": "https://...",
  "items": [
    {
      "vod_id": "71021072",
      "title": "sample title",
      "vod_url": "https://vod.sooplive.co.kr/player/71021072",
      "thumbnail_url": "https://...",
      "published_at": "2026-03-22T11:00:00+09:00"
    }
  ]
}
```

### Why This Matters
- page structure changes stay localized
- you can swap parsers without rewriting API/database code
- failures can fall back from HTML parser to Playwright

## 12. Error Handling

### Expected Failures
- SOOP API quota or temporary failure
- page layout change in replay pages
- adult/private/member-only VOD pages
- network timeout

### Handling Rules
- never delete existing VODs on collector failure
- mark collector run as failed with message
- retain last known live state until next successful check, but show stale timestamp
- show parser source and last error in admin/debug view

## 13. Security and Compliance

- keep SOOP API credentials on the server only
- do not expose secrets in frontend responses
- respect rate limits and conservative crawl intervals
- check SOOP terms and robots behavior before broader crawling
- keep scraping scope limited to registered streamers for MVP

## 14. Recommended MVP Build Order

### Phase 1
- DB schema
- streamer CRUD
- manual VOD collector for one streamer
- dashboard showing stored rows

### Phase 2
- scheduled live collector using official API
- current live badges on dashboard
- collector run logs

### Phase 3
- automated VOD collector for all active streamers
- parser fallback to Playwright
- search/filter/pagination

### Phase 4
- Discord/webhook alerts for new live or new VOD
- thumbnail caching
- PostgreSQL migration

## 15. Implementation Notes for This Workspace

The current workspace already has:
- a FastAPI-based local app pattern in `soop_webapp_v1.py`
- a static HTML frontend pattern in `webapp/index.html`
- a docs folder for packaging and deployment notes

Recommended approach here:
- keep the current STT app untouched
- create a new backend entry file for this feature
- add a dedicated UI file under `webapp/` or a subfolder like `webapp/live-vod/`
- start with SQLite to move quickly

## 16. Suggested Initial Deliverables

1. `app_live_vod.py`
   - FastAPI app
   - SQLite connection
   - streamer CRUD endpoints
   - collector stubs
2. `webapp/live_vod.html`
   - dashboard UI
3. `docs/SOOP_LIVE_VOD_WEBAPP_ARCHITECTURE.md`
   - this design doc
4. `docs/SOOP_LIVE_VOD_IMPLEMENTATION_PLAN.md`
   - task breakdown for actual coding

## 17. Decision Summary

Best practical MVP:
- `FastAPI + SQLite + static dashboard`
- official SOOP API for live checks
- adapter-based scraper for VOD list collection
- scheduler with conservative refresh intervals
- normalized storage so UI reads from DB, not directly from SOOP

This keeps the first version simple while leaving a clean path to a more robust production service later.

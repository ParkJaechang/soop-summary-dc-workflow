# TASK-003 Summary And Live/VOD Boundary Audit

## Purpose

Record the current boundary between the summary app and the live/VOD app, then define the first stabilization slice without starting integration work yet.

## Files Audited

- `soop_summery_local_v3.py`
- `soop_webapp_v1.py`
- `app_live_vod.py`
- `soop_remote_service.py`
- `app_dc_publisher.py`
- `agents/tasks/TASK-002-summary-payload-to-draft-post-job-pipeline/*`

## Current Boundary

### Summary Track

Primary summary generation happens in `soop_summery_local_v3.py`.

- `_summarize(...)` rebuilds `transcripts/full_transcript.txt`
- it writes `summaries/cleaned_full_script.txt`
- it writes grouped timeline files under `summaries/parts/`
- it writes `summaries/timeline.txt`
- it writes `summaries/final_summary.txt`

`soop_webapp_v1.py` contains a second summary flow with the same output pattern.

- it also rebuilds `transcripts/full_transcript.txt`
- it also writes `summaries/cleaned_full_script.txt`
- it also writes `summaries/parts/*`
- it also writes `summaries/timeline.txt`
- it also writes `summaries/final_summary.txt`

Observed summary-track rule:

- summary output is file-based and folder-local
- there is no normalized machine-readable payload file yet
- there is no stable handoff into publisher draft-job creation yet

### Live/VOD Track

Primary live/VOD collection happens in `app_live_vod.py`.

- it owns `data/soop_live_vod.db`
- it defines `streamers`, `streamer_live_state`, `live_snapshots`, `vods`, and `collector_runs`
- `collect_vods_for_streamer(...)` parses VOD cards and upserts rows into `vods`
- `refresh_live_status(...)` updates live state and snapshots
- API endpoints expose streamer, live, VOD, and collector-run data

`soop_remote_service.py` overlaps with live/VOD discovery, but it is not the main persistence path.

- it reads and writes `soop_channel_cards.json`
- it fetches streamer profile, live info, and VOD previews
- it is closer to a lightweight card/feed helper than a stable summary source

Observed live/VOD-track rule:

- live/VOD output is database-backed in `app_live_vod.py`
- `soop_remote_service.py` provides overlapping fetch logic but not a normalized summary payload
- live/VOD files do not create transcript or summary artifacts

### Publisher Track

`app_dc_publisher.py` already expects normalized content fields for draft jobs.

- `title`
- `body`
- `metadata`
- `dedupe_key`

This confirms that the missing contract is between summary output and publisher draft-job creation, not between live/VOD collection and publisher directly.

## Boundary Risks

1. Summary has two producers.
One producer is desktop-style (`soop_summery_local_v3.py`) and one is web-style (`soop_webapp_v1.py`). They generate similar files, but there is no declared source of truth.

2. Summary output is human-readable first, machine-readable second.
The main artifact is `final_summary.txt`, which is useful for people but weak as a stable interface.

3. Live/VOD discovery is duplicated.
`app_live_vod.py` and `soop_remote_service.py` both fetch live/VOD information with different storage models.

4. TASK-002 can accidentally absorb stabilization work.
If TASK-002 starts bridging directly from whichever summary file exists today, it will silently choose a source-of-truth decision that belongs in TASK-003.

## First Stabilization Slice

### Slice Goal

Stabilize the upstream summary contract before any summary-to-publisher bridge is implemented.

### File-Level Scope

1. `soop_summery_local_v3.py`
- treat this as the recommended first canonical summary producer for slice 1
- reason: it is the newest summary-focused app in the workspace and already writes deterministic folder artifacts
- next change in a later implementation task should add a normalized payload artifact next to `final_summary.txt`

2. `soop_webapp_v1.py`
- do not make it the source of truth yet
- keep it in parity-follow-up scope
- after the canonical payload contract is defined, either reuse the same writer or explicitly declare it a secondary adapter

3. `app_live_vod.py`
- keep this outside the first summary-contract slice
- its role in slice 1 is only to define what upstream metadata may later be attached to a summary payload
- no summary generation responsibility should be added here yet

4. `soop_remote_service.py`
- keep this outside the first summary-contract slice
- treat it as overlapping live/VOD helper logic, not as the bridge source for publisher payloads

5. `app_dc_publisher.py`
- no behavior change in slice 1
- use its existing `title/body/metadata/dedupe_key` requirement as the downstream contract target

### Slice Deliverable

The first implementation slice after this planning pass should produce one normalized summary payload artifact from `soop_summery_local_v3.py` without invoking publisher automation.

## Contract Ownership For The Future Bridge

These ownership notes are recorded now so later tasks do not blur responsibilities.

### `title`

- owned by the summary track
- derived from broadcast/VOD title plus summary-side normalization rules
- must be stable enough for a reviewer to understand the source content without opening raw transcript files

### `body`

- owned by the summary track
- derived from `final_summary.txt` or the same internal summary text before it is written
- must remain reviewable and human-readable

### `metadata`

- owned by the summary track, with live/VOD metadata attached from upstream collection when available
- should include source references such as `streamer_id`, `vod_url`, `vod_id`, timestamps, source app, and summary generation mode/version

### `dedupe`

- shared boundary
- summary track should emit source identity fields strong enough to derive dedupe
- publisher track should keep ownership of the final `dedupe_key` written into draft jobs
- recommended basis: streamer identity + canonical source URL or source ID + summary contract version

## TASK-002 Relationship

### What TASK-002 Still Owns

- normalized summary payload contract details that are specifically needed by the draft post-job bridge
- artifact examples for publisher-side consumption
- creation of draft post jobs from normalized summary data

### What TASK-003 Must Set First

- which summary file/app is the canonical upstream producer
- that live/VOD discovery is a separate hardening track
- that `app_live_vod.py` is not the first publisher bridge source

### Overlap Rule

If TASK-002 proceeds before slice-1 stabilization lands, it should use a sample or mocked normalized payload and should not silently choose between `soop_summery_local_v3.py` and `soop_webapp_v1.py` as the permanent source of truth.

## Coordinator Decision Needed

Confirm whether `soop_summery_local_v3.py` is the canonical summary producer for the first bridge slice, with `soop_webapp_v1.py` following later for parity.

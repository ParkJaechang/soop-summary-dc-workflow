# Task Spec

## Task ID

TASK-006

## Title

Live and VOD app foundation stabilization

## Problem

The project now has reviewed summary and publisher draft slices, but the live/VOD discovery track is still not stabilized as a reviewed foundation. The workspace needs one focused slice that proves `app_live_vod.py` can hold the core tracked-streamer data model and basic CRUD flow before broader live refresh and VOD collection hardening continues.

## Scope

- use `app_live_vod.py` as the implementation target for the first live/VOD stabilization slice
- verify or implement the DB schema and streamer CRUD baseline described in the docs
- save concrete evidence showing the basic app foundation works locally
- keep the slice limited to foundation and data management, not full collector automation
- record what later live-refresh and VOD-collector work still depends on this foundation

## Out Of Scope

- full scheduled live polling
- VOD scraping or Playwright fallback logic
- webhook notifications, packaging, or deployment polish
- summary payload generation or publisher draft creation work

## Acceptance Criteria

- `app_live_vod.py` exposes a stable foundation for streamer registration and storage
- the task saves evidence for schema creation and basic streamer CRUD behavior
- task files identify what remains for live refresh and VOD collection after this slice
- the handoff keeps the baton inside the live/VOD stabilization track rather than reopening publisher scope

## Notes

- this is the first execution slice for the live/VOD app track after summary and publisher integration reached reviewed draft-only flow

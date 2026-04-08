# Task Spec

## Task ID

TASK-007

## Title

Live refresh stabilization with official SOOP API

## Problem

The live/VOD foundation slice proved schema and streamer CRUD behavior in `app_live_vod.py`, but the app still has not produced reviewed evidence that active tracked streamers can be refreshed against the official SOOP live API and persisted into `streamer_live_state`, `live_snapshots`, and `collector_runs`.

## Scope

- use `app_live_vod.py` as the implementation target for the next live/VOD stabilization slice
- verify or implement one official-API-based live refresh flow for tracked streamers
- persist current live state updates and live snapshot history through the existing foundation tables
- save concrete evidence showing live refresh behavior locally
- record what later slices still depend on after the live refresh slice closes

## Out Of Scope

- VOD page scraping, Playwright fallback, or VOD parser hardening
- UI/dashboard polish beyond what is required to support live refresh evidence
- summary payload generation or publisher draft creation work
- scheduler hardening, packaging, or deployment work

## Acceptance Criteria

- `app_live_vod.py` can run a reviewed live refresh path against the official SOOP API contract or a controlled test double that exercises the same mapping path
- the task saves evidence for live refresh results, persisted `streamer_live_state`, appended `live_snapshots`, and collector run visibility
- the task files identify what still remains for VOD collection and later scheduler hardening
- the handoff keeps the baton inside the live/VOD stabilization track

## Notes

- this slice follows TASK-006 and should reuse its verified streamer foundation rather than reworking CRUD behavior
- prefer proving one clean global or targeted live refresh path before any broader collector automation

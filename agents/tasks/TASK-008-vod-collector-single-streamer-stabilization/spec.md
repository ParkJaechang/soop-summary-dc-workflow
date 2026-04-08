# Task Spec

## Task ID

TASK-008

## Title

VOD collector stabilization for a tracked streamer

## Problem

The live/VOD track now has reviewed foundation and live refresh slices, but it still lacks reviewed evidence that `app_live_vod.py` can collect and persist VODs for a tracked streamer through one stable replay/VOD source path.

## Scope

- use `app_live_vod.py` as the implementation target for the next live/VOD stabilization slice
- verify or implement one tracked-streamer VOD collection path and persistence flow
- persist normalized VOD rows into `vods` and expose them through the current API surface
- save concrete evidence showing one tracked-streamer VOD collection path works locally
- record what later slices still depend on after the VOD collector slice closes

## Out Of Scope

- multi-streamer scaling or scheduler hardening
- Playwright fallback unless the current HTML path cannot be validated without it
- summary payload generation or publisher draft creation work
- UI polish beyond what is needed to support VOD collector evidence

## Acceptance Criteria

- `app_live_vod.py` can run a reviewed one-streamer VOD collection path and persist normalized rows into `vods`
- the task saves evidence for collected VOD rows, API-visible VOD results, and collector run visibility
- the task files identify what still remains for broader VOD hardening and scheduler work
- the handoff keeps the baton inside the live/VOD stabilization track

## Notes

- this slice follows TASK-007 and should reuse the reviewed foundation and live refresh slices rather than reworking them
- prefer proving one clean tracked-streamer VOD path before multi-streamer or scheduler concerns

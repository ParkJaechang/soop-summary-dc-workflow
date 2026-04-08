# Task Spec

## Task ID

TASK-010

## Title

Multi-streamer VOD sweep hardening

## Problem

The live/VOD track now has reviewed one-streamer VOD collection and scheduler guardrails, but it still lacks reviewed evidence that VOD collection generalizes correctly across multiple active streamers with mixed results and durable collector visibility.

## Scope

- use `app_live_vod.py` as the implementation target for the next live/VOD stabilization slice
- verify or implement multi-streamer VOD sweep behavior across multiple active streamers
- verify persistence and collector-run visibility under mixed results across the sweep
- save concrete evidence showing multi-streamer VOD sweep behavior works locally
- record what later broader UI/admin and timeout/backoff slices still depend on after this sweep closes

## Out Of Scope

- summary payload generation or publisher draft creation work
- UI polish beyond what is needed to support sweep evidence
- packaging and deployment work
- broader non-VOD product polish

## Acceptance Criteria

- `app_live_vod.py` can run a reviewed multi-streamer VOD sweep path across multiple active streamers
- the task saves evidence for mixed-result persistence, per-streamer outcomes, and collector-run visibility
- the task files identify what still remains for timeout/backoff and UI/admin hardening
- the handoff keeps the baton inside the live/VOD stabilization track

## Notes

- this slice follows TASK-009 and should reuse the reviewed foundation, live refresh, one-streamer VOD, and scheduler slices rather than reworking them
- prefer proving mixed-result multi-streamer sweep behavior before broader UI/admin polish

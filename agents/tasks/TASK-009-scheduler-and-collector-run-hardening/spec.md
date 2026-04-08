# Task Spec

## Task ID

TASK-009

## Title

Scheduler and collector-run hardening

## Problem

The live/VOD track now has reviewed foundation, live refresh, and one-streamer VOD collection slices, but it still lacks reviewed evidence that repeated execution is controlled safely through scheduler behavior, duplicate-run protection, timeout/lock handling, and visible collector-run state.

## Scope

- use `app_live_vod.py` as the implementation target for the next live/VOD stabilization slice
- verify or implement scheduler-facing guardrails for repeated collector execution
- verify or implement duplicate-run protection, timeout/lock behavior, and collector-run visibility for live and VOD refresh paths
- save concrete evidence showing the operational guardrails work locally
- record what later broader multi-streamer and UI slices still depend on after this scheduler slice closes

## Out Of Scope

- broader multi-streamer feature expansion
- summary payload generation or publisher draft creation work
- UI polish beyond what is needed to support scheduler/run visibility evidence
- packaging and deployment work

## Acceptance Criteria

- `app_live_vod.py` exposes a reviewed scheduler/collector-run hardening path with visible run-state evidence
- the task saves evidence for duplicate-run prevention or lock behavior, collector-run recording, and timeout/run-state handling
- the task files identify what still remains for broader multi-streamer and product hardening
- the handoff keeps the baton inside the live/VOD stabilization track

## Notes

- this slice follows TASK-008 and should reuse the reviewed foundation, live refresh, and one-streamer VOD slices rather than reworking them
- prefer proving safe repeated execution and visibility before broader multi-streamer scale-up

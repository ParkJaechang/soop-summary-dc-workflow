# Task Spec

## Task ID

TASK-011

## Title

Collector timeout and backoff hardening

## Problem

The live/VOD track now has reviewed multi-streamer sweep behavior, but it still lacks reviewed evidence that slower or partially failing upstream collection attempts are classified clearly, bounded by time, and leave retry or backoff evidence instead of ambiguous failures.

## Scope

- use `app_live_vod.py` as the implementation target for the next live/VOD stabilization slice
- verify or implement timeout classification and retry or backoff behavior for collector paths
- save concrete evidence showing bounded collector behavior and durable failure-state visibility
- record what later UI/admin slices still depend on after this timeout or backoff slice closes

## Out Of Scope

- summary payload generation or publisher draft creation work
- broader product polish beyond what is needed to support timeout or failure evidence
- packaging and deployment work
- unrelated UI redesign

## Acceptance Criteria

- `app_live_vod.py` exposes a reviewed timeout or retry/backoff hardening path for collectors
- the task saves evidence for timeout or bounded-failure behavior plus durable collector-run visibility
- the task files identify what still remains for UI/admin and broader polish work
- the handoff keeps the baton inside the live/VOD stabilization track

## Notes

- this slice follows TASK-010 and should reuse the reviewed foundation, live refresh, VOD sweep, and scheduler slices rather than reworking them
- prefer proving bounded failure handling before UI/admin polish

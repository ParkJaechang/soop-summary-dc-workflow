# TASK-012 Spec

## Title

Collector-run and failure visibility in UI and admin views

## Problem

The live and VOD collector paths now leave durable evidence in `collector_runs`, but operators still need to inspect raw artifacts or database snapshots to understand recent failures, skipped backoff windows, and recovery. The next slice should expose this state through the app-facing UI or admin surface without reopening deeper collector behavior.

## Scope

- stay inside `app_live_vod.py` and its current UI or admin-facing surface
- expose recent collector-run history and failure or backoff visibility for the reviewed live/VOD flows
- show enough information to make timeout class, skipped backoff state, and recent run outcomes visible to a human operator
- save evidence artifacts that prove the new visibility path

## Out Of Scope

- reopening summary payload or publisher work
- changing collector semantics beyond what is needed to surface existing state
- broader UI polish, search, pagination, packaging, or auth
- persistent backoff state across restarts

## Acceptance Criteria

1. a UI or admin-facing path exposes recent collector-run status for the reviewed live and VOD flows
2. failed or skipped backoff states are visible without reading raw artifact files directly
3. local evidence proves the surfaced data matches persisted collector-run records
4. task files record any remaining product-hardening follow-up without widening scope

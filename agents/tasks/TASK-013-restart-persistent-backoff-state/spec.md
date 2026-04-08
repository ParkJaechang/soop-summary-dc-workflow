# TASK-013 Spec

## Title

Restart-persistent backoff state for live and VOD collectors

## Problem

Current timeout and backoff behavior is visible and durable in `collector_runs`, but the actual backoff window still lives only in process memory. If the app restarts, retry windows are lost and collectors may re-hit upstream sooner than intended.

## Scope

- keep work inside `app_live_vod.py` and the existing local persistence layer
- persist enough backoff state for the reviewed live and one-streamer VOD collector paths to survive process restart
- expose evidence that restart restores the remaining backoff window correctly
- preserve existing timeout classification and visibility behavior

## Out Of Scope

- broader scheduler redesign
- summary payload or publisher work
- broader UI polish
- long-run retry budgets or per-upstream tuning beyond what restart persistence needs

## Acceptance Criteria

1. live and one-streamer VOD backoff state survives process restart
2. immediate re-entry after restart still produces bounded skip behavior instead of a premature upstream hit
3. saved evidence proves persisted backoff state, restored remaining retry window, and durable collector-run visibility
4. later product-hardening follow-up is recorded without widening scope

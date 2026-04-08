# TASK-014 Spec

## Title

Scheduler mixed-latency and repeated-failure hardening

## Problem

Collector behavior is now durable across timeout, restart, and visibility slices, but the real scheduler path still lacks proof under mixed latency and repeated-failure conditions. The next slice should validate scheduler-driven execution, bounded retries, and durable run evidence without pulling in unrelated roles.

## Scope

- keep work inside `app_live_vod.py` and the current scheduler or collector orchestration path
- exercise scheduler-driven live and VOD execution under mixed latency or repeated-failure fixtures
- prove durable run visibility, bounded upstream pressure, and eventual recovery behavior
- save local evidence artifacts for reviewer inspection

## Out Of Scope

- summary payload or publisher work
- deployment or packaging work
- broader UI polish
- unrelated structural refactors

## Acceptance Criteria

1. scheduler-driven execution is exercised under mixed latency or repeated-failure conditions
2. saved evidence proves bounded retries or skips, durable `collector_runs`, and no uncontrolled upstream hammering
3. later follow-up work is recorded without widening scope

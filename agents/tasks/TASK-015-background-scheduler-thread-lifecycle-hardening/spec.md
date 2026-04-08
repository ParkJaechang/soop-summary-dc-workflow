# TASK-015 Spec

## Title

Background scheduler thread lifecycle hardening

## Problem

The extracted scheduler tick logic is now verified, but the actual long-running background scheduler thread lifecycle still lacks direct proof. The next slice should exercise startup, sustained running, and clean stop behavior of the real scheduler path without widening into deployment or publisher work.

## Scope

- keep work inside `app_live_vod.py` and the current background scheduler path
- verify or implement background scheduler startup, sustained tick execution, and clean stop behavior
- save evidence that collector runs remain durable and bounded under the real thread lifecycle
- capture any later ops or product-hardening dependencies without widening scope

## Out Of Scope

- summary payload or publisher work
- packaging or deployment changes
- broad UI polish
- unrelated refactors

## Acceptance Criteria

1. the real background scheduler lifecycle is exercised and leaves durable evidence
2. saved artifacts prove bounded execution and clean stop behavior under the real thread path
3. later follow-up work is recorded without widening scope

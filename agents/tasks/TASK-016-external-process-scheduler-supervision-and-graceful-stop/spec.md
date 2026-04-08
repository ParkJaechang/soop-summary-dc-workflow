# TASK-016 Spec

## Title

External-process scheduler supervision and graceful stop hardening

## Problem

The in-process background scheduler lifecycle is now verified, but we still lack evidence for external-process supervision, stop-signal handling, and runbook-shaped ownership. This is the first slice where `ops` becomes the necessary execution role.

## Scope

- keep work focused on external-process supervision and graceful stop behavior for the live/VOD scheduler
- produce evidence or runbook-oriented artifacts that show clean stop and bounded behavior outside the in-process verifier
- capture any remaining dependencies for later product hardening without widening scope

## Out Of Scope

- summary payload or publisher work
- broader UI polish
- unrelated refactors

## Acceptance Criteria

1. external-process or service-style supervision behavior is exercised or documented with durable evidence
2. graceful stop expectations and bounded scheduler shutdown behavior are captured clearly
3. later follow-up work is recorded without widening scope

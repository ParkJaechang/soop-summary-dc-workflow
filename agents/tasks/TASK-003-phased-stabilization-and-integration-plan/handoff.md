# Handoff

## Latest Update

- Summary: Closed the planning decision loop. The coordinator confirmed `soop_summery_local_v3.py` as the canonical summary producer for slice 1 under D-008, clarified via D-007 that TASK-002 should still proceed to reviewer now, and split the first upstream implementation into TASK-004.
- Next owner: summary_engineer via TASK-004
- Read first: `agents/tasks/TASK-004-canonical-summary-payload-artifact-from-soop-summery-local-v3/spec.md`
- Remaining work: execute the upstream summary-payload artifact slice in TASK-004; TASK-003 itself is complete as a planning task.

## Read Order

1. `agents/tasks/TASK-003-phased-stabilization-and-integration-plan/chat_starter.md`
2. `agents/artifacts/TASK-003-phased-stabilization-and-integration-plan/summary_live_vod_boundary_audit.md`
3. `agents/tasks/TASK-003-phased-stabilization-and-integration-plan/spec.md`
4. `agents/tasks/TASK-003-phased-stabilization-and-integration-plan/status.yaml`

## Decision Outcome

- `soop_summery_local_v3.py` is the canonical summary producer for the first stabilization slice.
- `soop_webapp_v1.py` remains parity-follow-up scope, not the source of truth.
- `app_live_vod.py` stays in live/VOD discovery scope and does not become the first publisher bridge source.
- TASK-002 proceeds to reviewer now because the local bridge contract and evidence remain valid without choosing the permanent producer inside publisher work.

## Concrete Next Work

- reviewer should review TASK-002 now
- summary_engineer should execute TASK-004 to add a normalized payload artifact on the summary side only
- future integration should consume those results explicitly rather than reopening this planning task

## Notes

- Start from upstream collection and normalized summary boundaries before expanding publisher automation.
- If overlap with `TASK-002` is discovered, record the overlap explicitly instead of silently changing either task.
- Current recommended boundary:
  `soop_summery_local_v3.py` is the first candidate source of truth for summary output, `soop_webapp_v1.py` is parity-follow-up, `app_live_vod.py` stays in live/VOD discovery scope, and `app_dc_publisher.py` remains the downstream contract target only.
- Contract ownership recorded in the audit file:
  `title` and `body` belong to the summary track, `metadata` is summary-owned with upstream source fields attached, and final publisher `dedupe_key` remains publisher-owned even if summary emits the identity basis.
- TASK-002 relationship:
  TASK-002 still owns the draft post-job bridge, but it should not silently choose between `soop_summery_local_v3.py` and `soop_webapp_v1.py` as the permanent source of truth.
- Copy/paste prompt for the next implementation chat:
  see TASK-004 handoff after this planning task.

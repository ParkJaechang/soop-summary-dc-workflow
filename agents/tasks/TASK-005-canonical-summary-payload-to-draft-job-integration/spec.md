# Task Spec

## Task ID

TASK-005

## Title

Canonical summary payload to draft post job integration

## Problem

The workspace now has a reviewed canonical summary payload artifact from `soop_summery_local_v3.py` and a reviewed publisher-side draft bridge in `app_dc_publisher.py`, but there is not yet one explicit integration slice that proves the real summary artifact can become a reviewable draft post job without manual contract guessing.

## Scope

- consume the canonical summary payload shape emitted by `soop_summery_local_v3.py`
- map or submit that payload into the publisher-side draft bridge
- save one end-to-end example showing canonical summary artifact in and draft post job out
- keep the flow reviewable and limited to `draft`
- record exact field mapping and any remaining gaps between summary-owned fields and publisher-owned fields

## Out Of Scope

- automatic approval, queueing, dispatch, or posting
- browser automation or site-specific publish behavior
- parity work for `soop_webapp_v1.py`
- live/VOD collector changes in `app_live_vod.py`

## Acceptance Criteria

- one documented path exists from canonical `summary_payload.json` into `POST /api/summary-bridge/draft-job`
- at least one end-to-end example artifact is saved under TASK-005 artifacts
- the task files make the summary-to-publisher field mapping explicit
- the flow remains draft-only and reviewable
- handoff notes make it clear whether reviewer or follow-up publisher work acts next

## Notes

- use the reviewed canonical payload from TASK-004 rather than inventing a new producer shape
- keep ownership boundaries explicit: summary owns payload content, publisher owns dedupe key and draft job state

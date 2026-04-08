# Handoff

## Latest Update

- Summary: Coordinator accepted the task. Reviewer found no blocking issues, the refreshed sample draft artifact matches the contract, and the bridge slice is now closed as done.
- Next owner: none
- Read first: `agents/tasks/TASK-002-summary-payload-to-draft-post-job-pipeline/done.md`
- Remaining work: none inside TASK-002; follow-up implementation continues in TASK-004.

## Notes

- Exact bridge entry point: `POST /api/summary-bridge/draft-job` in `app_dc_publisher.py`
- Workflow decision:
  per `agents/board/decisions.md`, D-007 says task-local review readiness beats broader program order unless the unresolved program decision would invalidate the task's evidence. That exception does not apply here because TASK-002 intentionally stayed producer-agnostic and only consumes a normalized payload contract.
- Upstream boundary decision:
  D-008 separately confirms `soop_summery_local_v3.py` as the canonical producer for the first stabilization slice, with parity follow-up left to `soop_webapp_v1.py`. That decision belongs to the upstream track and does not block TASK-002 reviewer acceptance.
- Downstream draft fields now map like this:
  `title` and `body` pass through from normalized summary payload after trim, `metadata` is preserved and enriched with `metadata.publisher_bridge`, and `dedupe_key` is computed by publisher from `contract_version + target_id + producer + canonical_source_ref`.
- Source identity handling now works like this inside the publisher boundary:
  `source_url`, `source_id`, and `source_ref` may all be provided, but every populated value must resolve to the same canonical SOOP VOD identity such as `soop_vod:123456`. The first populated value is still stored in `post_jobs.source_ref` for review visibility, while dedupe uses `metadata.publisher_bridge.canonical_source_ref`.
- Publisher safety updates in this slice:
  generic `PATCH /api/jobs/{job_id}` still blocks workflow `status` or `error` edits, now writes editable fields in the correct SQL placeholder order, and still checks dedupe collisions on both create and update.
- Reviewer outcome before this ops pass:
  code-level fixes passed review, but the contract evidence was not fully acceptance-ready because `sample_draft_post_job.json` still reflected the pre-canonical dedupe shape.
- Test command:
  `python -m unittest tests.test_app_dc_publisher_summary_bridge -v`
- Test log:
  `agents/artifacts/TASK-002-summary-payload-to-draft-post-job-pipeline/test_results.txt`
- Reproduction and rerun notes:
  `agents/artifacts/TASK-002-summary-payload-to-draft-post-job-pipeline/review_fix_runbook.md`
- Artifact refresh log:
  `agents/artifacts/TASK-002-summary-payload-to-draft-post-job-pipeline/sample_draft_post_job_refresh_log.txt`
- Files to inspect for implementation:
  `app_dc_publisher.py`
  `tests/test_app_dc_publisher_summary_bridge.py`
- Files to inspect for acceptance after fixes:
  `agents/tasks/TASK-002-summary-payload-to-draft-post-job-pipeline/review.md`
  `agents/artifacts/TASK-002-summary-payload-to-draft-post-job-pipeline/summary_bridge_contract.md`
  `app_dc_publisher.py`
  `tests/test_app_dc_publisher_summary_bridge.py`
- Evidence to inspect:
  `agents/artifacts/TASK-002-summary-payload-to-draft-post-job-pipeline/sample_summary_payload.json`
  `agents/artifacts/TASK-002-summary-payload-to-draft-post-job-pipeline/sample_draft_post_job.json`
  `agents/artifacts/TASK-002-summary-payload-to-draft-post-job-pipeline/sample_draft_post_job_refresh_log.txt`
  `agents/artifacts/TASK-002-summary-payload-to-draft-post-job-pipeline/review_fix_runbook.md`
  `agents/artifacts/TASK-002-summary-payload-to-draft-post-job-pipeline/test_results.txt`
- Supervisor checkpoint note:
  the stale artifact mismatch called out by reviewer has been addressed in the refreshed sample draft artifact. Coordinator should compare `sample_draft_post_job.json` against `summary_bridge_contract.md` and then decide whether to route directly to reviewer for final confirmation.
- Coordinator checkpoint outcome:
  `sample_draft_post_job.json` now includes `metadata.publisher_bridge.canonical_source_ref`, and `metadata.publisher_bridge.dedupe_basis` now uses `canonical_source_ref` instead of the stale `source_ref` shape. The refresh log also records `canonical_source_ref: soop_vod:123456` and the canonical dedupe basis keys.
- Final reviewer outcome:
  no blocking findings remain for TASK-002. The stale evidence blocker is cleared and the task is ready for acceptance.
- Coordinator closeout outcome:
  TASK-002 is closed. The bridge now has a reviewed draft-creation path, aligned contract artifacts, and passing regression evidence for this slice.
- Boundary decision intentionally deferred:
  per `summary_live_vod_boundary_audit.md`, this task does not choose between `soop_summery_local_v3.py` and `soop_webapp_v1.py` as the permanent producer. It only defines the normalized payload contract that publisher can safely consume.
- Durable coordinator note:
  `agents/board/decisions.md` now records that publisher-side dedupe must use a canonical source identity at the boundary instead of mixed fallback fields.
- Parallel work note:
  upstream summary-producer stabilization now continues under `TASK-004`, not under TASK-002 review.
- Paste-ready next chat prompt for summary_engineer:
  ```text
  Valid workflow roles for this project are:
  - summary_engineer
  - publisher_engineer
  - ops
  - reviewer
  - coordinator

  This chat must act only as `summary_engineer`.
  First, restate in one line that your assigned role for this turn is `summary_engineer`.

  Then read the files below and follow them exactly.
  - C:\python\agents\shared\project_brief.md
  - C:\python\agents\shared\architecture.md
  - C:\python\agents\shared\coding_rules.md
  - C:\python\agents\roles\summary_engineer.md
  - C:\python\agents\board\ownership.md
  - C:\python\agents\board\decisions.md
  - C:\python\agents\tasks\TASK-004-canonical-summary-payload-artifact-from-soop-summery-local-v3\spec.md
  - C:\python\agents\tasks\TASK-004-canonical-summary-payload-artifact-from-soop-summery-local-v3\status.yaml
  - C:\python\agents\tasks\TASK-004-canonical-summary-payload-artifact-from-soop-summery-local-v3\handoff.md
  - C:\python\agents\artifacts\TASK-003-phased-stabilization-and-integration-plan\summary_live_vod_boundary_audit.md

  Execute TASK-004 only. Treat `soop_summery_local_v3.py` as the canonical producer for this slice, add or expose one stable machine-readable summary payload artifact, save an example artifact under the TASK-004 artifacts folder, update the task files with exact downstream field definitions, and end with one paste-ready next prompt for the correct next role.
  ```

# Summary To Draft Contract

## Scope

This contract covers only the bridge from a normalized summary payload into a reviewable draft post job in `app_dc_publisher.py`.

- It does not approve jobs.
- It does not queue jobs.
- It does not dispatch jobs.
- It stops at `draft`.

## Bridge Entry Point

- API: `POST /api/summary-bridge/draft-job`
- Code owner for this slice: `publisher_engineer`
- Upstream producer remains unresolved by design in this task.
- Until TASK-003 stabilization is closed, the bridge should consume normalized payloads or sample payloads without declaring a permanent source-of-truth app.

## Input Contract

Required request fields:

- `target_id`: publisher target registry id
- `title`: reviewable post title prepared by the summary track
- `body`: reviewable post body prepared by the summary track
- `producer`: summary producer name such as `soop_summery_local_v3`
- one or more of `source_url`, `source_id`, or `source_ref`, as long as the provided values resolve to the same canonical SOOP VOD identity

Optional request fields:

- `metadata`: summary-owned source metadata to preserve in the draft job
- `attachments`: file paths for future manual-safe posting review
- `contract_version`: defaults to `summary-publisher-bridge/v1`

## Publisher Contract Mapping

- `title`
  summary payload passes it through directly after trim
- `body`
  summary payload passes it through directly after trim and preserves line breaks
- `metadata`
  summary-owned metadata is preserved and `metadata.publisher_bridge` is added for traceability
- `dedupe_key`
  publisher-owned field derived from `contract_version + target_id + producer + canonical_source_ref`

## Source Identity Rules

The bridge keeps a reviewable `source_ref` and a separate canonical dedupe identity:

1. `source_url`
2. `source_id`
3. `source_ref`

- The first populated field still becomes `post_jobs.source_ref` for operator visibility.
- Dedupe uses a canonical source identity derived inside the publisher boundary.
- Supported canonical forms include:
  `https://vod.sooplive.co.kr/player/123456` -> `soop_vod:123456`
  `vod-123456` -> `soop_vod:123456`
  `123456` -> `soop_vod:123456`
- If multiple source identity fields are sent, they must resolve to the same canonical value.
- If the bridge cannot derive a canonical SOOP VOD identity, it rejects the request instead of falling back to a mixed or raw dedupe basis.

## Dedupe Rule

- Dedupe is scoped by `target_id` so the same summary source can still become separate draft jobs for different publish targets.
- The persisted key shape is `summary-draft:v1:<target_id>:<sha256-prefix>`.
- The unhashed basis is copied into `metadata.publisher_bridge.dedupe_basis` for review.
- `metadata.publisher_bridge.canonical_source_ref` stores the resolved canonical source identity alongside the display-oriented `source_ref`.

## Draft Output Guarantees

The created post job must have:

- `source_type = summary_payload`
- `status = draft`
- no approval side effects
- no queue side effects
- no publish attempts

## Evidence

- `sample_summary_payload.json`
- `sample_draft_post_job.json`
- `test_results.txt`

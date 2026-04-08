# TASK-005 Field Mapping

## Proven Path

1. canonical input artifact:
   `TASK-004 .../sample_job/summaries/summary_payload.json`
2. publisher helper:
   `app_dc_publisher.build_summary_bridge_payload_from_canonical_summary(...)`
3. bridge endpoint:
   `POST /api/summary-bridge/draft-job`
4. draft-only output artifact:
   `draft_post_job_output.json`

## Field Mapping

- canonical `title`
  -> bridge `title`
  -> post job `title`

- canonical `body`
  -> bridge `body`
  -> post job `body`

- canonical `producer.name`
  -> bridge `producer`
  -> `metadata.publisher_bridge.producer`

- canonical `metadata.source.canonical_source_url`
  -> bridge `source_url` when present
  -> post job `source_ref`
  -> publisher canonical dedupe identity `soop_vod:<vod_id>`

- canonical `metadata.source.source_url`
  -> fallback bridge `source_url` if `canonical_source_url` is missing

- canonical `metadata.source.source_id`
  -> bridge `source_id`
  -> `metadata.publisher_bridge.source_id`

- canonical `metadata`
  -> preserved as bridge `metadata`
  -> preserved in post job `metadata`

- canonical `contract_version`, `producer`, `dedupe_basis`
  -> copied into `metadata.summary_payload`
  -> preserved for review alongside publisher-owned bridge metadata

- publisher-owned derivations
  -> `dedupe_key` from bridge contract version + target_id + producer + canonical source ref
  -> `status = draft`
  -> `source_type = summary_payload`

## Remaining Contract Gap

- The canonical summary payload does not carry `target_id`, so the publisher side still needs a caller-provided target selection at bridge time.
- The canonical summary payload contract version is `summary_payload.v1`, while the publisher bridge contract version is `summary-publisher-bridge/v1`; both are now preserved, but they remain separate contracts by design.
- Attachments are not produced by the current canonical summary payload and therefore remain empty in this integration slice.

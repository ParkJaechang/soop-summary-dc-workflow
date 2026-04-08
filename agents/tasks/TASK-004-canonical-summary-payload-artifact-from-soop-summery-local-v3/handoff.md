# Handoff

## Latest Update

- Summary: Coordinator accepted and closed TASK-004. Reviewer found no blocking issues, and the canonical producer slice now has a documented machine-readable payload artifact path plus sample evidence.
- Next owner: none
- Read first: `agents/tasks/TASK-004-canonical-summary-payload-artifact-from-soop-summery-local-v3/done.md`
- Remaining work: none inside TASK-004; future parity or hardening work should happen in a new task.

## Notes

- D-008 already confirms the source of truth for this slice: `soop_summery_local_v3.py`.
- Do not add publisher draft creation logic here; that belongs to TASK-002.
- Do not move parity work for `soop_webapp_v1.py` into this task.
- What changed:
  `soop_summery_local_v3.py` writes `summary_job_context.json` at job-folder level during download and writes `summaries/summary_payload.json` after summary generation.
- Evidence:
  `agents/artifacts/TASK-004-canonical-summary-payload-artifact-from-soop-summery-local-v3/example_summary_payload.json`
  `agents/artifacts/TASK-004-canonical-summary-payload-artifact-from-soop-summery-local-v3/payload_generation_notes.txt`
  `agents/artifacts/TASK-004-canonical-summary-payload-artifact-from-soop-summery-local-v3/sample_job/summaries/summary_payload.json`
- Coordinator checkpoint outcome:
  the example payload contains stable `title`, `body`, source metadata, artifact provenance, and `dedupe_basis`; the generation notes confirm the artifact was produced by the new helper path; and the sample job payload proves the canonical producer writes the machine-readable artifact at job level.
- Current workflow clarification:
  `TASK-002` is already closed as done, so it is not part of this task's active scope or baton.
- Remaining parity work:
  `soop_webapp_v1.py` does not yet emit the same payload artifact and remains out of scope for this task.
- Known limitation:
  legacy folders created before `summary_job_context.json` existed can still export a payload, but `metadata.source` may be incomplete unless a source URL is available at rerun time.
- Final reviewer outcome:
  no blocking findings remain. This slice is ready for acceptance based on the canonical producer implementation and saved evidence.
- Coordinator closeout outcome:
  TASK-004 is closed. `soop_summery_local_v3.py` is now the reviewed canonical producer for this slice and writes `summary_job_context.json` plus `summaries/summary_payload.json` as the machine-readable artifact path.

## Downstream Field Definition

### Top-Level Fields

- `contract_version`
  fixed artifact contract string for this slice: `summary_payload.v1`
- `producer`
  producer identity and payload generation timestamp
- `title`
  stable review-facing summary title; currently derived from the canonical job title
- `body`
  plain-text summary body; currently sourced from `summaries/final_summary.txt` with `timeline.txt` fallback
- `metadata`
  machine-readable source, summary, and artifact provenance block
- `dedupe_basis`
  source-identity basis emitted by summary for downstream dedupe derivation; this is not the final publisher `dedupe_key`

### `metadata.source`

- `platform`
  fixed `soop`
- `content_type`
  fixed `vod` for this slice
- `source_url`
  normalized source URL when known
- `canonical_source_url`
  canonicalized URL for downstream identity matching
- `source_id`
  extracted source identifier such as SOOP player id
- `source_kind`
  parsed source type such as `vod_player`, `station`, or `channel`

### `metadata.summary`

- `summary_mode`
  current summary mode string from the canonical producer
- `body_format`
  fixed `plain_text`
- `reference_notes`
  reference note text used during summary generation
- `reference_notes_present`
  boolean flag for downstream handling
- `generated_at`
  payload write timestamp
- `job_folder_name`
  folder-level job identifier for audit/debug use
- `transcript_part_count`
  count of transcript chunks used in the job

### `metadata.job_context`

- `context_version`
  fixed context schema string for the producer sidecar
- `downloaded_at`
  first context save timestamp
- `original_title`
  raw source title captured during download when available
- `duration_seconds`
  source duration when available
- `entry_count`
  playlist/entry count when available
- `extractor`
  upstream extractor name when available
- `uploader`
  upstream uploader/channel value when available

### `metadata.artifacts`

- `job_folder`
  absolute job folder path
- `full_transcript_path`
  path to the rebuilt transcript when available
- `cleaned_full_script_path`
  path to the cleaned transcript helper file when available
- `final_summary_path`
  path to the main human-readable summary
- `timeline_path`
  path to the timeline file when available
- `payload_path`
  path to the machine-readable payload artifact itself

### `dedupe_basis`

- `platform`
  fixed `soop`
- `content_type`
  fixed `vod`
- `canonical_source_url`
  preferred canonical source identity field
- `source_id`
  parsed SOOP content identifier when available
- `source_kind`
  parsed source type
- `producer`
  fixed canonical producer file: `soop_summery_local_v3.py`
- `contract_version`
  fixed `summary_payload.v1`

## Paste-Ready Next Chat Prompt

No automatic next prompt is required from TASK-004 itself.

# TASK-002 Review Fix Runbook

## Scope

This runbook covers only the reviewer-requested fixes inside the draft post-job slice of `app_dc_publisher.py`.

- It does not touch approval.
- It does not touch queueing.
- It does not touch dispatch.

## Test Command

```powershell
python -m unittest tests.test_app_dc_publisher_summary_bridge -v
```

## Test Log

- `agents/artifacts/TASK-002-summary-payload-to-draft-post-job-pipeline/test_results.txt`

## Reproduction 1: PATCH field-order regression

1. Create a target with `POST /api/targets`.
2. Create a draft summary job with `POST /api/summary-bridge/draft-job`.
3. Patch the job with:

```json
{"dedupe_key": "   "}
```

Expected after the fix:

- `dedupe_key` is trimmed to `""`
- `updated_at` remains populated
- unrelated editable fields such as `title` remain unchanged

## Reproduction 2: mixed source identity dedupe regression

1. Create a target with `POST /api/targets`.
2. Create the first draft with only:

```json
{
  "source_id": "vod-123456",
  "source_url": "",
  "source_ref": ""
}
```

3. Create the second draft for the same `target_id` with:

```json
{
  "source_id": "vod-123456",
  "source_url": "https://vod.sooplive.co.kr/player/123456"
}
```

Expected after the fix:

- first request returns `200`
- second request returns `409`
- `metadata.publisher_bridge.canonical_source_ref` is `soop_vod:123456`

## Operational Notes

- The publisher bridge now requires source identity inputs that can be canonicalized to a SOOP VOD identity.
- If multiple source identity fields are present, they must resolve to the same canonical value.

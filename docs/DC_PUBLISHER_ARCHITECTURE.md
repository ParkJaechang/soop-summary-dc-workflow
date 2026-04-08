# DC Publisher MVP Architecture

## Goal

Build a posting pipeline that can take outputs from existing tools in this workspace and move them through a safe publish flow:

1. generate result
2. store a normalized post job
3. review and approve
4. dispatch through a publisher adapter
5. record attempts and outcomes

This MVP intentionally does not implement site-specific bypass logic. It prepares the project for a future browser automation adapter while keeping the rest of the system stable and testable.

## Why This Direction

Public examples of auto-posting bots tend to converge on the same shape:

- content generation is separate from publishing
- jobs are persisted in a database
- approval and retry states are explicit
- browser automation is isolated behind one adapter
- failures are logged per attempt

That same pattern fits this workspace well because:

- `soop_webapp_v1.py` already has in-memory job handling
- `app_live_vod.py` already uses `FastAPI` and `SQLite`
- the current tools already produce file-based outputs that can become post sources

## MVP Scope

### In Scope

- publish target registry
- post job storage
- approval flow
- queueing flow
- publish attempt logs
- adapter interface for future browser automation
- manual adapter for safe end-to-end testing

### Out of Scope

- gallery-specific selector automation
- captcha handling or anti-detection work
- account creation or account farming
- bulk posting logic

## Proposed Tables

### `publish_targets`

Stores where content is intended to be posted.

- `id`
- `name`
- `platform`
- `gallery_id`
- `board_url`
- `active`
- `created_at`
- `updated_at`

### `post_jobs`

Stores normalized content waiting for publication.

- `id`
- `target_id`
- `source_type`
- `source_ref`
- `title`
- `body`
- `attachments_json`
- `metadata_json`
- `dedupe_key`
- `status`
- `approved_at`
- `queued_at`
- `posted_at`
- `error`
- `created_at`
- `updated_at`

### `publish_attempts`

Stores each dispatch or publish attempt.

- `id`
- `job_id`
- `adapter`
- `status`
- `started_at`
- `finished_at`
- `message`

## Recommended Status Flow

- `draft`
- `approved`
- `queued`
- `prepared`
- `posted`
- `failed`
- `cancelled`

## Adapter Strategy

### `ManualPublisherAdapter`

Used first for dry runs. It records that a payload is ready without actually submitting it to a site.

### `DcInsidePublisherAdapter`

Planned next step. This should:

- load a logged-in browser session
- open the write page
- fill title/body/files
- stop safely when extra verification is required
- record full attempt logs and screenshots

The adapter should remain isolated so selector changes do not affect the rest of the app.

## Integration Path With Existing Tools

Suggested first integrations:

1. `soop_webapp_v1.py` summary output creates a `post_job`
2. a reviewer approves the job in API or UI
3. dispatch creates a prepared publish attempt
4. the future browser adapter handles the actual post submission

## Immediate Next Step After This MVP

Add a browser publisher module that reads a saved authenticated session, but keep the approval gate and attempt logging in place.

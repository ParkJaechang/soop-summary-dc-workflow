# Ownership Map

## Role To Area

- `coordinator`: task scope, routing, acceptance, board updates
- `summary_engineer`: SOOP collection, normalization, summary payloads
- `publisher_engineer`: post jobs, approval flow, publish adapters, attempt logging
- `reviewer`: risk review, acceptance review, test gap review
- `ops`: scripts, packaging, environment checks, runbooks, artifacts

## Current File-Level Guidance

- summary-related Python files default to `summary_engineer`
- publish-related Python files default to `publisher_engineer`
- batch files and setup notes default to `ops`
- task files and board files default to `coordinator`

If work crosses boundaries, the coordinator should record the temporary owner in the task `status.yaml`.

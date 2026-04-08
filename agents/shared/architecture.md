# Architecture Snapshot

This is a lightweight map of the current workspace so role boundaries line up with real files.

## Main Areas

- `app_live_vod.py`: FastAPI-style live and VOD application entry point
- `soop_summery_local_v3.py`: local summary workflow with the newest summary-focused filename in the workspace
- `soop_remote_service.py`: remote or service-oriented SOOP support
- `app_dc_publisher.py`: publisher-side app and post flow foundation
- `dc_manual_post_test.py`: safe manual publish testing area
- `soop_webapp_v1.py` and `webapp/`: UI surface and earlier web app flow

## Planned Logical Boundaries

- ingestion: fetch live or VOD data from SOOP
- summary: clean source text and produce normalized summary payloads
- review: human or controlled approval before dispatch
- publishing: create post jobs and adapter-specific attempts
- ops: scripts, configs, packaging, runbooks, and evidence

## Existing Document References

- `docs/SOOP_LIVE_VOD_IMPLEMENTATION_PLAN.md`
- `docs/SOOP_LIVE_VOD_WEBAPP_ARCHITECTURE.md`
- `docs/DC_PUBLISHER_ARCHITECTURE.md`

## Design Direction

- keep state explicit
- isolate publishing adapters from the rest of the system
- allow file-based collaboration now and app-level automation later

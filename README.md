# SOOP Summary to DC Workflow Workspace

This repository contains a file-driven workflow and application workspace for:

- collecting or refreshing SOOP live and VOD data
- generating normalized summary payloads
- converting summaries into reviewable draft post jobs
- packaging and operating the live/VOD scheduler on Windows
- coordinating multi-chat Codex work through task, handoff, and evidence files

## What Is Included

- application entry points such as `app_live_vod.py` and `app_dc_publisher.py`
- summary and SOOP support modules such as `soop_summery_local_v3.py`
- workflow state under `agents/`
- future multi-project scaffolding under `portfolio/`
- architecture and implementation notes under `docs/`
- tests and supporting scripts used during development

## What Is Not Committed By Default

The `.gitignore` intentionally excludes local-only or sensitive material:

- virtual environments
- build and dist outputs
- cookies and local auth/session files
- large machine-local binaries such as `ffmpeg.exe`, `ffprobe.exe`, and `aria2c.exe`

If another PC needs those binaries, provision them separately or document their install path there.

## Important Folders

- `agents/`: file-based collaboration harness for multi-chat Codex workflows
- `portfolio/`: additive multi-project wrapper for future projects
- `docs/`: architecture and implementation notes
- `tests/`: test and verification code
- `webapp/`: UI-side assets and earlier web app surfaces

## Current Status

The committed roadmap captured in `agents/board/progress.md` is currently marked complete. New work should be opened as new tasks rather than silently reopening closed slices.

## Recommended First Read On Another PC

1. `agents/board/progress.md`
2. `agents/README.md`
3. `agents/shared/project_brief.md`
4. `agents/shared/architecture.md`
5. `docs/SOOP_LIVE_VOD_WEBAPP_ARCHITECTURE.md`
6. `docs/DC_PUBLISHER_ARCHITECTURE.md`

## Cross-PC Workflow

See `docs/GITHUB_SYNC_SETUP.md` for the recommended upload and restore flow.

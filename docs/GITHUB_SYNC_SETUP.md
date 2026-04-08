# GitHub Sync Setup

This guide is for sharing the current workspace to GitHub so another PC can open the repo and continue work with Codex immediately.

## Goal

Preserve the current source, workflow harness, task history, and documentation without committing local-only secrets or heavyweight machine-specific binaries.

## Recommended Repository Contents

Commit these areas:

- `agents/`
- `portfolio/`
- `docs/`
- `tests/`
- `webapp/`
- application and script files in the repo root such as:
  - `app_live_vod.py`
  - `app_dc_publisher.py`
  - `soop_summery_local_v3.py`
  - scheduler `.ps1` and `.bat` files
  - config templates that do not contain secrets

Do not commit:

- `.venv/`
- `build/`, `dist/`
- `cookies_*.pkl`
- machine-local binaries such as `ffmpeg.exe`, `ffprobe.exe`, `aria2c.exe`
- private env or secret files

## Before Upload

1. Review `.gitignore`.
2. Make sure any secret-bearing config is excluded or sanitized.
3. Decide whether the repository should be `private` or `public`.
   For this workspace, `private` is the safer default.

## GitHub Upload Options

### Option A: Create an Empty GitHub Repo First

This is the cleanest route if there is no suitable target repo yet.

1. In GitHub, create a new empty repository such as `soop-summary-dc-workflow`.
2. Keep it private unless you intentionally want broader sharing.
3. After the repo exists, this workspace can be uploaded into that owner/name target.

### Option B: Reuse an Existing Empty Repo

Only do this if the repo name and purpose fit this project. Avoid reusing unrelated repositories just because they are available.

## Restoring On Another PC

1. Clone the repository.
2. Prefer cloning it back to `C:\python` if you want the existing absolute-path workflow prompts to keep working unchanged.
3. Provision Python and project dependencies.
4. Recreate any ignored local assets:
   - cookies/session files
   - large helper binaries
   - machine-local runtime config
5. Open the repo in VSCode.
6. Start with:
   - `agents/board/progress.md`
   - `agents/README.md`
   - the active or next task under `agents/tasks/`

## First Codex Prompt On Another PC

Open a fresh `coordinator` chat and point it at:

- `agents/shared/project_brief.md`
- `agents/shared/architecture.md`
- `agents/shared/coding_rules.md`
- `agents/roles/coordinator.md`
- `agents/board/tasks.yaml`
- `agents/board/progress.md`

Then ask it to summarize the current roadmap state and recommend the next task.

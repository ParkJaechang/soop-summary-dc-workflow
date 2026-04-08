# Other PC Quickstart

This is the fastest path to continue this project from another PC with VSCode and Codex.

## 1. Clone

If possible, clone to `C:\python` so the existing absolute-path workflow prompts continue to work unchanged.

```bash
git clone https://github.com/ParkJaechang/soop-summary-dc-workflow.git C:\python
```

## 2. Open In VSCode

Open `C:\python` in VSCode.

## 3. Recreate Local-Only Prerequisites

The repository intentionally does not include some machine-local items:

- cookies/session files
- heavy helper binaries such as `ffmpeg.exe`, `ffprobe.exe`, `aria2c.exe`
- local runtime data
- local virtual environment

Recreate only what you need for the slice you want to work on.

## 4. Read First

Open these files first:

1. `agents/board/progress.md`
2. `agents/README.md`
3. `agents/shared/project_brief.md`
4. `agents/shared/architecture.md`
5. `docs/SOOP_LIVE_VOD_WEBAPP_ARCHITECTURE.md`
6. `docs/DC_PUBLISHER_ARCHITECTURE.md`

## 5. First Codex Chat

Start with a fresh `coordinator` chat and use the existing workflow files under `agents/`.

Suggested first message:

```text
이번 채팅은 coordinator 역할만 맡아줘.

먼저 아래 파일을 읽고 그 규칙대로만 행동해.
- C:\python\agents\shared\project_brief.md
- C:\python\agents\shared\architecture.md
- C:\python\agents\shared\coding_rules.md
- C:\python\agents\roles\coordinator.md
- C:\python\agents\board\tasks.yaml
- C:\python\agents\board\progress.md

현재 저장소를 다른 PC에서 처음 열었다.
현 상태를 요약하고, 지금 바로 시작하기 가장 좋은 다음 task 또는 개선 slice를 제안해줘.
```

## 6. If You Want To Start New Work

- open a new task under `agents/tasks/`
- update `agents/board/tasks.yaml`
- let the coordinator route the next role

## 7. If You Want To Start A Different Project Later

Use the portfolio wrapper:

- `portfolio/projects.yaml`
- `portfolio/scripts/new_project.ps1`
- `projects/README.md`

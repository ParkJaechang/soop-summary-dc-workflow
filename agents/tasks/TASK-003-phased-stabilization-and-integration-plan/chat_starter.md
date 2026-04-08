# TASK-003 Chat Starter

## Recommended Next Chat

Use this in the next chat after the coordinator confirms the slice direction, or use it as the decision-driving prompt if the coordinator chat is the next step now.

## Copy/Paste Prompt

```text
이번 채팅은 coordinator 역할로만 행동해줘.

먼저 아래 파일을 읽고 그 규칙대로만 행동해.
- C:\python\agents\shared\project_brief.md
- C:\python\agents\shared\architecture.md
- C:\python\agents\shared\coding_rules.md
- C:\python\agents\tasks\TASK-003-phased-stabilization-and-integration-plan\spec.md
- C:\python\agents\tasks\TASK-003-phased-stabilization-and-integration-plan\status.yaml
- C:\python\agents\tasks\TASK-003-phased-stabilization-and-integration-plan\handoff.md
- C:\python\agents\artifacts\TASK-003-phased-stabilization-and-integration-plan\summary_live_vod_boundary_audit.md

TASK-003 기준으로 아래만 처리해.
1. summary_engineer가 정리한 경계 감사 결과를 검토해.
2. 첫 안정화 slice의 canonical summary producer를 확정해.
3. TASK-002와 TASK-003의 경계를 다시 확인하고, TASK-002가 바로 진행 가능한 범위와 대기해야 하는 범위를 파일에 분리해서 적어.
4. 다음 실행 owner와 바로 실행할 구현 task를 파일 기준으로 지정해.
5. 작업 후 status.yaml, handoff.md, revision_log.md를 업데이트해.

중요:
- 구현은 아직 하지 말고, coordinator 결정과 라우팅만 남겨.
- 다음 담당자가 파일만 읽어도 이어받을 수 있게 써.
- soop_summery_local_v3.py, soop_webapp_v1.py, app_live_vod.py, app_dc_publisher.py의 역할 경계를 흐리지 마.
- title, body, metadata, dedupe 기준은 유지하되, 어떤 파일이 그것을 먼저 책임질지 분명히 적어.
```

## Intent

This prompt is designed to force the next chat to:

- read the current durable task files first
- make the pending coordinator decision explicitly
- keep TASK-002 active without silently expanding it
- route the first implementation slice cleanly

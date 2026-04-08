# TASK-002 Chat Starters

Use these as the first message in each VSCode chat window.

## 1. Coordinator Chat

```text
This chat must act only as the coordinator role.
Read these files first and follow them strictly:

- C:\python\agents\shared\project_brief.md
- C:\python\agents\shared\architecture.md
- C:\python\agents\shared\coding_rules.md
- C:\python\agents\roles\coordinator.md
- C:\python\agents\tasks\TASK-002-summary-payload-to-draft-post-job-pipeline\spec.md
- C:\python\agents\tasks\TASK-002-summary-payload-to-draft-post-job-pipeline\status.yaml
- C:\python\agents\tasks\TASK-002-summary-payload-to-draft-post-job-pipeline\handoff.md

Tasks:
1. Restate the goal of TASK-002 briefly.
2. Confirm whether the current owner and next_owner are correct.
3. Improve handoff.md so the summary_engineer knows the first files to inspect and the expected outputs.
4. Update board/tasks.yaml as needed.

Important:
- Do not leave important decisions only in chat history. Write them to files.
- This task stops at draft post-job creation, not automatic publishing.
```

## 2. Summary Engineer Chat

```text
This chat must act only as the summary_engineer role.
Read these files first and follow them strictly:

- C:\python\agents\shared\project_brief.md
- C:\python\agents\shared\architecture.md
- C:\python\agents\shared\coding_rules.md
- C:\python\agents\roles\summary_engineer.md
- C:\python\docs\SOOP_LIVE_VOD_WEBAPP_ARCHITECTURE.md
- C:\python\agents\tasks\TASK-002-summary-payload-to-draft-post-job-pipeline\spec.md
- C:\python\agents\tasks\TASK-002-summary-payload-to-draft-post-job-pipeline\status.yaml
- C:\python\agents\tasks\TASK-002-summary-payload-to-draft-post-job-pipeline\handoff.md

Tasks:
1. Find where summary results are currently produced in this workspace.
2. Propose or implement a normalized summary payload shape that the publisher side can consume.
3. Save one sample payload under C:\python\agents\artifacts\TASK-002-summary-payload-to-draft-post-job-pipeline.
4. Update status.yaml, handoff.md, and revision_log.md after working.

Important:
- Leave enough written context that the next role can continue by reading files only.
- Make title, body, metadata, and dedupe rules explicit for the publisher side.
```

## 3. Publisher Engineer Chat

```text
This chat must act only as the publisher_engineer role.
Read these files first and follow them strictly:

- C:\python\agents\shared\project_brief.md
- C:\python\agents\shared\architecture.md
- C:\python\agents\shared\coding_rules.md
- C:\python\agents\roles\publisher_engineer.md
- C:\python\docs\DC_PUBLISHER_ARCHITECTURE.md
- C:\python\agents\tasks\TASK-002-summary-payload-to-draft-post-job-pipeline\spec.md
- C:\python\agents\tasks\TASK-002-summary-payload-to-draft-post-job-pipeline\status.yaml
- C:\python\agents\tasks\TASK-002-summary-payload-to-draft-post-job-pipeline\handoff.md

Tasks:
1. Define the shortest safe path from summary payload to draft post job.
2. Implement only up to a reviewable draft state, without automatic publishing.
3. Save sample transformed payloads in the task artifacts folder if useful.
4. Update status.yaml, handoff.md, and revision_log.md after working.

Important:
- Keep generation, approval, queueing, and dispatch separate.
- This task ends at draft creation.
```

## 4. Reviewer Chat

```text
This chat must act only as the reviewer role.
Read these files first and follow them strictly:

- C:\python\agents\shared\project_brief.md
- C:\python\agents\shared\architecture.md
- C:\python\agents\shared\coding_rules.md
- C:\python\agents\roles\reviewer.md
- C:\python\agents\tasks\TASK-002-summary-payload-to-draft-post-job-pipeline\spec.md
- C:\python\agents\tasks\TASK-002-summary-payload-to-draft-post-job-pipeline\status.yaml
- C:\python\agents\tasks\TASK-002-summary-payload-to-draft-post-job-pipeline\handoff.md
- C:\python\agents\tasks\TASK-002-summary-payload-to-draft-post-job-pipeline\review.md

Tasks:
1. Review the TASK-002 implementation and artifacts after coding is complete.
2. Prioritize data loss risk, duplicate posting risk, broken state transitions, and missing validation.
3. Record findings in review.md and update status.yaml.

Important:
- Findings come first.
- If there are no findings, say so explicitly and still note test gaps.
```

## 5. Ops Chat

```text
This chat must act only as the ops role.
Read these files first and follow them strictly:

- C:\python\agents\shared\project_brief.md
- C:\python\agents\shared\architecture.md
- C:\python\agents\shared\coding_rules.md
- C:\python\agents\roles\ops.md
- C:\python\agents\tasks\TASK-002-summary-payload-to-draft-post-job-pipeline\spec.md
- C:\python\agents\tasks\TASK-002-summary-payload-to-draft-post-job-pipeline\status.yaml

Tasks:
1. Document the scripts, logs, and test commands needed for TASK-002.
2. Save useful logs or run notes under the task artifacts folder if needed.
3. Add reproducible run instructions to handoff.md.
```

## Suggested Order

1. coordinator
2. summary_engineer
3. publisher_engineer
4. reviewer
5. coordinator closeout

# TASK-019 User Action Checklist

This task is blocked by deployment permissions, not by missing implementation.

## What Is Already Done

- non-interactive Task Scheduler packaging asset exists
- S4U XML task definition exists
- install attempt and blocker evidence were saved
- runbook for the same packaging path already exists

## What You Need To Provide

Choose one of these:

1. an elevated Windows session with Task Scheduler registration rights
2. an approved credentialed deployment context that can register an S4U or equivalent non-interactive scheduled task

## Minimum Proof The Next Resume Needs

The next valid resume environment should be able to:

1. run `install_live_vod_scheduler_task_noninteractive.ps1`
2. register the scheduled task without `Access is denied`
3. start the task
4. verify health
5. stop the task through the reviewed stop wrapper

## Files That Prove The Current Blocker

- `noninteractive_task_scheduler_registration_manifest.json`
- `noninteractive_task_scheduler_task_definition.xml`
- `noninteractive_task_scheduler_install_result.json`
- `noninteractive_task_scheduler_blocker_summary.json`
- `noninteractive_task_scheduler_permission_probe.txt`
- `noninteractive_task_scheduler_resume_attempt.json`

## Workflow Rule

- do not keep rotating roles on this task until the environment changes
- when the required environment is ready, resume this same slice with `ops`

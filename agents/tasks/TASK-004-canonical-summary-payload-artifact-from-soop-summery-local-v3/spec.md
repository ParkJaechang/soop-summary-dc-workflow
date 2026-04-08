# Task Spec

## Task ID

TASK-004

## Title

Canonical summary payload artifact from soop_summery_local_v3

## Problem

The project now has a publisher-side bridge contract and a planning decision that `soop_summery_local_v3.py` is the first canonical summary producer, but the summary track still does not emit one stable machine-readable payload artifact that downstream tasks can consume.

## Scope

- treat `soop_summery_local_v3.py` as the source of truth for slice 1
- add one normalized summary payload artifact alongside the existing summary output files
- keep the artifact machine-readable and stable enough for downstream bridge consumption
- save an example artifact and update task evidence
- avoid coupling this slice to automatic publishing or live/VOD app changes

## Out Of Scope

- publisher-side draft creation changes
- parity changes in `soop_webapp_v1.py`
- live/VOD collector changes in `app_live_vod.py`
- browser automation or posting behavior

## Acceptance Criteria

- `soop_summery_local_v3.py` produces or can export one normalized summary payload artifact
- the artifact includes stable `title`, `body`, and source metadata fields needed by downstream work
- task artifacts show an example payload and any run/test notes
- handoff notes make the downstream contract and remaining parity work explicit

## Notes

- this task implements the D-008 upstream decision without reopening publisher-scope work from TASK-002

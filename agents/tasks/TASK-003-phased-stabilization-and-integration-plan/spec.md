# Task Spec

## Task ID

TASK-003

## Title

Phased stabilization plan for SOOP summary, live/VOD, and DC publisher apps

## Problem

The workspace already contains partially working apps for SOOP VOD-to-summary generation, live/VOD link discovery, and DC publishing, but they are still unstable and not yet aligned around explicit contracts. Integrating them immediately would increase risk, so the project needs a harness-style coordination task that stabilizes each app separately before merge.

## Scope

- define three workstreams: summary generation, live/VOD discovery, and DC publishing
- map the current files and docs that belong to each workstream
- record the phase order, merge preconditions, and role routing for the first stabilization slice
- keep durable decisions in task files and board files rather than chat only
- preserve the current project scope of SOOP summary data and DC upload pipeline

## Out Of Scope

- immediate code-level merger of all apps
- direct implementation of unstable posting automation in this coordination task
- captcha bypass, anti-detection work, or unsafe automation shortcuts
- broad UI polish or packaging work unless a later task explicitly requests it

## Acceptance Criteria

- the task documents the three workstreams and their boundaries
- the phase order and merge preconditions are recorded clearly enough for another chat to continue by reading files only
- one first execution owner is assigned in `status.yaml`
- `handoff.md` tells the next role what to read first and what concrete planning work comes next
- `board/decisions.md` records why stabilization happens before integration

## Notes

- existing `TASK-002` remains active as a focused bridge task and is not silently redefined here
- the first practical slice should stabilize upstream data and interface boundaries before publisher automation expands

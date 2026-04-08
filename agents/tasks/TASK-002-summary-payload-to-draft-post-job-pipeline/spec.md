# Task Spec

## Task ID

TASK-002

## Title

Summary payload to draft post job pipeline

## Problem

The workspace already has summary-generation code and a publisher-side architecture, but there is no clearly defined bridge from a SOOP summary result into a normalized draft post job that can be reviewed before publishing.

## Scope

- define a normalized summary payload shape that publisher logic can consume
- identify the source module or output path that will provide this payload
- implement or wire a draft post-job creation path
- keep the result reviewable and non-destructive
- save one or more example payload artifacts for later testing

## Out Of Scope

- automatic live posting to DC
- gallery-specific browser automation
- captcha bypass or anti-detection work
- full UI polish beyond what is needed to test the flow

## Acceptance Criteria

- the task folder names the exact files and roles involved in the bridge
- a normalized summary payload example is saved under task artifacts
- there is an implementation path that creates a draft post job from summary data
- the flow stops before automatic publish and remains reviewable
- handoff notes make it clear whether publisher or reviewer acts next

## Notes

- best first slice: bridge summary output into a safe draft queue before touching real post submission

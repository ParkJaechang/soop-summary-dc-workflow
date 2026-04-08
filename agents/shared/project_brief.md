# Project Brief

## Working Goal

Build a controlled pipeline that can:

1. collect or receive SOOP broadcast data
2. generate normalized summary data
3. review and approve a post job
4. upload or prepare content for DC safely
5. preserve logs, evidence, and retry context

## Product Principles

- summaries should be reusable across UI, API, and publisher flows
- publish behavior must be reviewable before dispatch
- unsafe automation shortcuts are out of scope
- every important state change should be visible in files or logs

## Near-Term Deliverables

- stable summary payload format
- task-based collaboration workflow for multiple chats
- reviewable post-job pipeline
- artifacts that prove what was generated and what was attempted

## Success Signals

- another chat can continue work by reading files only
- task ownership is always visible
- summary data and publish data are separated cleanly
- failed runs leave enough evidence to debug

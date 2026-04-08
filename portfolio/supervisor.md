# Portfolio Supervisor

Use this file when you are supervising more than one project.

## Goal

Keep project-level workflow isolation while making it easy to see:

- which project is active
- which coordinator chat belongs to which project
- which project is waiting on review, implementation, or acceptance

## Rules

- one project should have one active workflow root
- each project keeps its own `agents/board/tasks.yaml`
- do not mix task ids, progress files, or handoffs across projects
- when switching projects, read that project's local `agents/board/progress.md` first

## Recommended Naming

- project folder: short slug such as `soop_dc_bot` or `new_project_a`
- task ids: project-scoped prefix such as `BOT-001`, `A-001`, `SHOP-001`
- coordinator chat title: `<project-slug>-coordinator`

## Switching Rule

Before work begins in another project:

1. confirm the target project in `projects.yaml`
2. open that project's own workflow root
3. use that project's own coordinator, not the current project's coordinator

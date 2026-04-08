# Portfolio Workspace

This folder is a multi-project wrapper for future projects.

It exists to let you run the same harness workflow on more than one project without changing the current `C:\python\agents` setup.

## Safety Rule

- do not move or rewrite the current project's `agents/` folder from here
- treat `portfolio/` as an additive layer only
- start future projects from `portfolio/templates/project_template/`

## Main Files

- `projects.yaml`: registry of projects and their status
- `supervisor.md`: top-level supervision rules across projects
- `rules/common_workflow.md`: reusable workflow guidance
- `templates/project_template/`: starter structure for future projects
- `scripts/new_project.ps1`: scaffolds a new project from the template

## Suggested Future Layout

```text
C:\python
  agents\                      # current project only
  portfolio\
  projects\
    project_a\
    project_b\
```

## Current State

- the active SOOP/DC project stays where it is today
- future projects should be created under a separate root such as `C:\python\projects\`

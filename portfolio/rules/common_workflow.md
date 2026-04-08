# Common Workflow Rules

These are reusable rules for future projects copied from the current harness pattern.

## Reusable Defaults

- coordinator is the supervisor gate
- non-coordinator roles hand back to coordinator by default
- every turn starts with role re-anchor
- non-coordinator self-prompts are not allowed
- progress should be visible in a board-level progress file

## Keep Project-Specific Rules Local

Do not centralize these here unless they truly apply to every project:

- domain-specific architecture rules
- project-specific file ownership
- special safety or compliance boundaries
- milestone percentages and roadmap estimates

## Template Usage

- copy the template into a new project root
- rename role and project docs as needed
- keep the template generic; specialize inside the new project, not here

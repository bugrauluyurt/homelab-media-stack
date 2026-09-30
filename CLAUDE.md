@AGENTS.md
@AGENTS.local.md

## Required validation

Before handing off changes or opening/updating a PR, run the relevant focused tests and the full
`scripts/repo-check` on the final source, including new files. Rerun after subsequent edits and report
commands, results and any blockers in the PR. Add regression tests for fixes and control external
inputs such as clock and boot time. Never skip failing tests or claim unrun checks passed.

Follow `AGENTS.md` for secret-safe source validation and health checks after authorized deployment.
These requirements do not authorize service restarts or changes to live VPN settings.

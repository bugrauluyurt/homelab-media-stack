- `repo-check` fails on a missing compose bind source, a broken link to a repo file, a script
  without its executable bit or its `Runs:` header; `stack-health` checks that installed units run
  scripts that exist and that the repo has no root-owned paths.

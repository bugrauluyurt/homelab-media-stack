# Contributing

Thanks for helping. Issues and pull requests are welcome; for anything larger than a fix, open
an issue first so we can agree on the approach.

## How the code is written

[AGENTS.md](AGENTS.md) is the guide for people and coding agents alike: the layout, the safety
rules the stack depends on (P2P only inside the VPN, the untrusted home network, read-only
SFTPGo, secrets out of git), and the code style. Read it before changing anything; the rules
there are the review checklist.

## Making a change

1. Fork, branch, and change the smallest thing that solves the problem.
2. Keep configure scripts idempotent: a second run prints only `=` lines.
3. Add a line under `## Unreleased` in [CHANGELOG.md](CHANGELOG.md), under the heading that
   matches the change (`### Added`, `### Changed`, `### Fixed`, `### Security`, `### Removed`,
   `### Breaking`). The heading decides the next version; see
   [docs/operations/releasing.md](docs/operations/releasing.md).
4. Run `scripts/check` (Docker is enough: every tool runs in a container). CI runs the same.
5. Enable the pre-commit hook once, so secrets never reach a commit:
   `git config core.hooksPath .githooks`.
6. If the change touches the server, run it on real hardware and include the output of
   `scripts/health-check` in the pull request. Say which platform you tested on
   (Raspberry Pi 5 or x86-64; Debian, Ubuntu or Arch).

Commit messages are an imperative summary line and a body that explains why. A pull request
merges into `main` once it is up to date with `main`, its `checks` run passes and a maintainer
approves it; maintainers merge their own through the admin bypass.

By contributing you agree that your work is released under the [MIT license](LICENSE) and that
you follow the [code of conduct](CODE_OF_CONDUCT.md).

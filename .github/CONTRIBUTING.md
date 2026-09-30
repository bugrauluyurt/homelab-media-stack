# Contributing

Thanks for helping. Issues and pull requests are welcome; for anything larger than a fix, open
an issue first so we can agree on the approach.

## How the code is written

[AGENTS.md](../AGENTS.md) is the guide for people and coding agents alike: the layout, the safety
rules the stack depends on (P2P only inside the VPN, the untrusted home network, read-only
SFTPGo, secrets out of git), and the code style. Read it before changing anything; the rules
there are the review checklist.

## Making a change

1. Fork, branch, and change the smallest thing that solves the problem.
2. Keep configure scripts idempotent: a second run prints only `=` lines.
3. Add your changelog entry as a file, `changelog.d/<name>.<heading>.md`, instead of editing
   `CHANGELOG.md` ([format](../changelog.d/README.md)). The heading (`added`, `changed`, `fixed`,
   `security`, `removed`, `breaking`) decides the next version; see
   [docs/operations/releasing.md](../docs/operations/releasing.md). One file per change means your
   pull request never conflicts with another one over the changelog.
4. Run `scripts/repo-check` (Docker is enough: every tool runs in a container). CI runs the same.
5. Enable the hooks once: `git config core.hooksPath .githooks`. `pre-commit` keeps secrets
   out of commits, and `commit-msg` checks the commit message format below.
6. If the change touches the server, run it on real hardware and include the output of
   `scripts/stack-health` in the pull request. Say which platform you tested on
   (Raspberry Pi 5 or x86-64; Debian, Ubuntu or Arch).

## Commit messages

Commits follow [Conventional Commits](https://www.conventionalcommits.org), the format
[commitizen](https://commitizen-tools.github.io/commitizen/) writes. `.cz.toml` configures it, so
`cz commit` asks for each part and `cz check` validates a message.

```text
<type>(<scope>)!: <summary>

<body: why the change was needed, wrapped at 72 characters>

<footer: BREAKING CHANGE: what users must do, Refs #12>
```

- **Type** says what kind of change it is:

  | Type | Use it for |
  |---|---|
  | `feat` | A new capability for the people running the stack |
  | `fix` | A bug fix |
  | `docs` | Documentation only |
  | `refactor` | Code that changes shape but not behaviour |
  | `perf` | Faster or lighter, same behaviour |
  | `test` | Tests only |
  | `build` | Images, compose, dependencies |
  | `ci` | GitHub workflows and `scripts/repo-check` |
  | `chore` | Upkeep that fits nothing above, such as releases |
  | `style` | Formatting only |
  | `revert` | Undoing an earlier commit |

- **Scope** is optional: the area touched, in lowercase, such as a service (`glance`, `gluetun`,
  `jellyfin`), `scripts`, `systemd`, `docs`, `skills`, `agent` or `release`.
- **`!`** after the scope marks a breaking change; explain it in a `BREAKING CHANGE:` footer.
- **Summary:** imperative mood ("add", not "added" or "adds"), lowercase, no final period, and
  the whole line at most 72 characters. Say what changes for the user, not which files moved.
- **Body:** optional for small changes. Explain why, not what; the diff shows what.

```text
fix(jellyfin): read the startup user before renaming it

Jellyfin 12 refuses to rename a startup user it has not returned yet, so
a fresh install stopped at the setup wizard.
```

Not `Fixed stuff`, `update glance.yml` or `Improve security and docs`: none has a type, and none
says what changed for the user.

The type doesn't pick the version: the heading in the `changelog.d/` file name does
([releasing](../docs/operations/releasing.md)). A `feat` usually pairs with `.added.md` and a `fix`
with `.fixed.md`.

## Pull requests

Pull requests are squash-merged, so the pull request **title** becomes the commit on `main`: write
it in the same format. The **PR title** check runs the commit hook on it. A pull request merges into `main` once it is up to date with `main`, its
`checks` run passes and a maintainer approves it; maintainers merge their own through the admin
bypass.

By contributing you agree that your work is released under the [MIT license](../LICENSE) and that
you follow the [code of conduct](CODE_OF_CONDUCT.md).

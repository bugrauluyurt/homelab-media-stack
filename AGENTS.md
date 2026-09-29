# Agent guide: homelab media stack

A media server managed as code. Docker Compose runs the *arr apps, Jellyfin, Seerr and
the downloaders, with torrents and Soulseek confined to a WireGuard VPN (gluetun), plus
optional modules picked with `COMPOSE_PROFILES` in `.env`: music (Lidarr, slskd,
Navidrome, Needle), games (Questarr, SFTPGo), monitoring, stats, dashboards and Plex.
It runs on arm64 and amd64, on Debian, Ubuntu and Arch. The home network reaches only
Jellyfin, Seerr and the games page; everything else goes through Tailscale.

**This deployment:** when `AGENTS.local.md` exists next to this file, read it first. It
names the server, how to reach it from this checkout, and rules specific to this install.

## Skills
Operating skills live in `ai/homelab-plugin/skills/` (linked into `.claude/skills` and
`.agents/skills`). Run them on the server; from another checkout, run them there.

| Skill | Use |
|---|---|
| `stack-health` | Is everything OK? (read-only diagnosis first) |
| `vpn-check` | Is P2P traffic confined to the VPN? (read-only) |
| `drive-health` | SMART status and temperature of the media drive (read-only) |
| `stack-logs` | Diagnose a service; `references/known-issues.md` lists solved problems |
| `stack-update` | Check, apply and roll back image updates (**ask first**) |
| `stack-backup` | Backup status, backup now, restore settings (**restore: ask first**) |
| `stack-power` | Stop the stack or unmount the drive, and start it again (**ask first**) |

## Layout
- `docker-compose.yml`: every service; `compose.gpu.yml`: opt-in GPU transcoding.
- `.env` holds every secret and this machine's values (gitignored); `.env.example` documents each key.
- `scripts/`: idempotent `configure-*.py` API setup, the operational scripts, and their shared
  helpers `stack_env.py` (Python) and `stack-env.sh` (bash). New helpers go into those two files.
- `systemd/`: unit and udev templates with `@PLACEHOLDERS@`, rendered by `scripts/install-host`.
- `docs/`: how everything works. Start at `docs/architecture.md`; each script and unit has an entry in
  `docs/reference/scripts.md` and `docs/reference/systemd.md`, each `.env` key in `docs/reference/configuration.md`.
- App data lives in `$CONFIG_ROOT`; media in `$DATA_ROOT`, inside the `$STORAGE_MOUNT` mount.

## Safety rules
- **Ask the user first** before restarting services, changing the VPN, editing `.env`,
  restoring data, applying updates or powering the stack or drive. Check that nothing is
  playing in Jellyfin before restarting it. Two automatic exceptions are approved:
  `sync-port` restarts gluetun after 15 minutes without a forwarded port, and
  `throttle-downloads` caps downloads at 20 MB/s while someone watches or the load is high
  and keeps the permanent 10 Mbps upload cap. Downloads are otherwise unlimited by choice.
- **P2P stays in the VPN:** qBittorrent and slskd share gluetun's network, and the exit
  stays inside `VPN_COUNTRIES`. SABnzbd (Usenet) is the only downloader outside it.
- **The home network is untrusted** (guests share it): it reaches only the firewall's
  `HOME_APPS`. New access goes through Tailscale; SSH stays keys-only on the tailnet, and
  every `authorized_keys` entry carries a `from="..."` restriction (`health-check` fails otherwise).
- **SFTPGo stays read-only:** accounts get `list` and `download` only and are managed through
  `scripts/games_accounts.py`; game folders mount `read_only`; the admin API answers only the
  host and Docker; its ports stay IPv4-only; FTP and WebDAV stay off.
- **Music ownership:** Lidarr owns `$DATA_ROOT/media/music`; Needle writes only
  `$DATA_ROOT/media/singles`, Navidrome's second library.
- **Secrets:** read `.env` values into variables and keep them out of output, logs and commits.
  A pre-commit hook blocks common key formats.

## Changing the code
- Configure scripts stay idempotent: a second run prints only `=` lines
  (`+` changed, `=` already right, `~` skipped, `-` removed, `!` warning).
- Code style: blank lines between logical steps; a comment only for a non-obvious reason, in
  one line; names that say what they hold; `${VAR:-x}` and `ENV.get()` defaults; no em or en dashes.
- Verify a change with `scripts/check` (needs only Docker; CI runs the same), then
  `scripts/health-check` on the server. health-check writes a test file on the drive and starts
  throwaway containers, so keep it for validating changes rather than read-only investigations.
- A new script or unit gets an entry in the reference pages; `scripts/check` fails without one.
- Every user-visible change adds its entry as `changelog.d/<name>.<heading>.md`, never an edit to
  `CHANGELOG.md` (headings: breaking or removed, added, changed or deprecated, fixed or security;
  `changelog.d/README.md` has the format). The headings decide the next version; merging the bot's
  release PR writes them into `CHANGELOG.md` and publishes it (`docs/operations/releasing.md`).
- Edit skills only under `ai/homelab-plugin/skills/`. They reach Codex with the next release, which
  sets `version` in `ai/homelab-plugin/plugin.json`.
- Commits and pull request titles follow Conventional Commits (`type(scope): summary`, at most
  72 characters, lowercase, imperative); the body says why. `CONTRIBUTING.md` has the types.

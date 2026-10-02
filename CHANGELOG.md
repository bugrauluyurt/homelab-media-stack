# Changelog

What changed in each release. The stack uses [semantic versioning](https://semver.org): a major
version means you need to change your setup (a renamed setting, a removed module, a new mount),
a minor version adds features, and a patch fixes bugs. A change records its entry as a file in
[`changelog.d/`](changelog.d/README.md), named for the heading that matches it; the headings decide the
next version, and merging the release pull request writes the entries here and publishes it
([how releases work](docs/operations/releasing.md)).

## 3.1.0 - 2026-10-02

### Added
- Glance gets a persistent Meeting mode control to pause torrents, optionally for one hour,
  preserving manually stopped transfers and retrying after qBittorrent outages.
  The control sits below Releases, follows the Glance theme, and shows loading and confirmation states.

## 3.0.0 - 2026-09-30

### Breaking
- The repository layout is tidier, and upgrading needs two steps after `git pull`: run
  `scripts/host-install`, then `scripts/stack-up`.
  - Scripts are named area first: `health-check` is now `stack-health`, `update` is `stack-update`,
    `backup-config` is `stack-backup`, `check-updates` is `stack-update-check`, `notify-failure` is
    `stack-failure-notify`, `storage-off` is `drive-off` (the alias too), `sync-port` is
    `vpn-port-sync`, `leak-test` is `vpn-leak-test`, `install-host` is `host-install`, `firewall` is
    `host-firewall`, `install-agent` is `agent-install`, `check-indexers` is `indexers-check`,
    `add-indexers.py` is `configure-indexers.py`, `render-scraparr-config` is `configure-scraparr`,
    `throttle-downloads` is `downloads-throttle`, `watch-activity` is `activity-watch`,
    `sync-youtube.py` is `youtube-sync.py`, `add-viewer.py` is `viewer-add.py` and `check` is
    `repo-check`. `host-install` points the installed units at the new names.
  - The per-app config folders moved into `apps/`, so `stack-up` recreates the containers that
    mount them (gluetun with qBittorrent and slskd, Jellyfin, Glance, Homepage, Grafana,
    Prometheus, Scrutiny, Recyclarr). A local edit in one of them survives
    `git stash && git pull --ff-only && git stash pop`.
  - The unit templates moved to `host/systemd/`, and the community files to `.github/`.

### Added
- `repo-check` fails on a missing compose bind source, a broken link to a repo file, a script
  without its executable bit or its `Runs:` header; `stack-health` checks that installed units run
  scripts that exist and that the repo has no root-owned paths.

### Fixed
- `configure-grafana-watch.py` is executable, as the setup guide assumes, and indents its output
  like the other configure scripts.
- An empty `NTFY_SERVER` in `.env` now falls back to ntfy.sh in the Python scripts too, as it
  already did in the bash ones, instead of sending alerts to an empty address.

## 2.7.0 - 2026-09-30

### Changed
- French series (tagged `french` in Sonarr) grab torrents without the 60-minute wait for Usenet,
  so new episodes reach the ratio trackers' swarms early, when seeding them earns ratio. Re-run
  `configure-arr.py` to apply it.
- The ratio-based trackers (Draupnirr, TR4KER) now serve new releases only: the apps grab from their
  RSS feeds and interactive search, never from a backlog search, whose old releases cost ratio that
  seeding can't earn back. Re-run `add-indexers.py` to apply it.

### Fixed
- `add-indexers.py` no longer stops when a site times out while being added (TorrentProject2 is
  down); it reports that one as failed and carries on.

## 2.6.0 - 2026-09-30

### Added
- NZBFinder can join NZBgeek as a Usenet indexer: set `NZBFINDER_API_KEY` in `.env` and re-run
  `configure-arr.py`, which adds it to Prowlarr and so to every app.

### Changed
- Cleanuparr now removes stalled private torrents too, such as those a tracker refuses for a low
  ratio, and watches Lidarr's downloads. Re-run `configure-cleanuparr.py` to apply it.

## 2.5.0 - 2026-09-30

### Added
- The maintenance guide explains how to upgrade the stack itself to a new release, apart from
  image updates.

### Fixed
- VPN recovery no longer recreates downloaders while the tunnel is unhealthy. The existing
  port-sync timer restores stopped or detached downloaders after the VPN recovers, without
  restarting unrelated services. Invalid qBittorrent API responses no longer result in guessed
  preference writes, and recovery is reported only after port verification.
- VPN recovery tests now use a controlled clock and boot time, so release checks also pass
  on freshly booted CI runners. Regression coverage preserves the production reboot safeguard
  and verifies the recovery delay and restart cooldown without changing runtime behavior.
- Agent instructions now explicitly require focused tests, full source checks, regression
  coverage and accurate validation results before handing off changes or opening/updating PRs.

## 2.4.0 - 2026-09-29

### Added
- A copy of `glance/youtube-channels.json` in `$CONFIG_ROOT/glance/` replaces the repository's
  sample, so your pinned YouTube channels stay out of git.
- Music docs explain ListenBrainz discovery in Needle: each listener connects their ListenBrainz
  token in Needle's Settings, Navidrome sends the listens, and missing songs from the weekly
  playlists come through slskd into `media/singles`. Lidarr and Tubifarry are unchanged.
- The troubleshooting notes cover game searches that always take 30 seconds: one slow indexer
  holds Questarr to its timeout, and switching it off in Prowlarr fixes it.
- The troubleshooting notes cover a VPN that drops soon after torrents start and recovers about
  an hour later: what was observed, the suspected cause, and why DHT stays enabled.

### Changed
- Changelog entries are files in `changelog.d/` instead of lines under `## Unreleased`, so pull
  requests no longer conflict with each other or with a release. `changelog.d/README.md` shows the
  format.
- Glance's subreddits, stock list and pinned YouTube channels are now generic samples; edit them
  in `glance/glance.yml` and `glance/youtube-channels.json`.

### Fixed
- `scripts/check` passes on a Raspberry Pi 5. ruff's arm64 build crashes on its 16 KiB-page
  kernel, so the check skips ruff there and says so; CI still runs it.
- Glance's YouTube rows show videos again. YouTube's RSS feed answers 404 for hours at a time, so
  `sync-youtube.py` now fetches the latest uploads hourly, through the Data API once you are signed
  in, and keeps a channel's last videos when it can't be read. `arr-youtube.timer` runs hourly
  instead of weekly; rerun `install-host` to pick up the new schedule.
- The plugin description, script messages and comments say "the server" instead of "the Pi",
  since the stack runs on any supported machine.
- Grafana's network panels show the server's real traffic. node-exporter now runs on the host
  network; in a container network it counted only its own container. `configure-uptime-kuma.py`
  updates the URL of a monitor whose service moved, so re-run it after updating.

### Security
- `.gitignore` and the pre-commit hook also keep `.env.*` copies (`.env.bak`, `.env.local`) and
  `*.local.*` files out of commits, not only `.env` itself.
- `render-scraparr-config` and `backup-config` create the scraparr config and the restic key file
  private from the start, instead of making them private right after writing.

## 2.3.0 - 2026-09-29

### Added
- Each release carries its source archive, `homelab-media-stack-X.Y.Z.tar.gz`, with signed build
  provenance (`.intoto.jsonl`) that `gh attestation verify` checks; SECURITY.md shows how.

## 2.2.0 - 2026-09-29

### Added
- `ARR_SUBNET` sets the `arr` Docker network's subnet, and `install-host` reports when it overlaps
  another Docker network on the machine (Docker hands the default `172.18.0.0/16` to the first
  other compose project) or doesn't hold `PROWLARR_IP`.

### Fixed
- A fresh install works with Jellyfin 12: `configure-jellyfin.py` reads the startup user before
  naming it, which Jellyfin 12 needs.
- On a fresh install, services that run as your user (Prometheus, Navidrome, Needle, Seerr,
  Questarr, SFTPGo, ChangeDetection) could not write their settings, because Docker created their
  folders as root. `stack-up` now creates every bind-mount folder as the stack user first.
- A stalled download of the Jellyfin Spotlight theme no longer keeps Jellyfin from starting; the
  download times out and Jellyfin starts with the files it has.

## 2.1.0 - 2026-09-29

### Changed
- The documented checkout is `~/homelab-media-stack`: the terminal aliases and the skills look there
  unless `MEDIA_STACK_DIR` says otherwise (it replaces `ARR_STACK_DIR`), and the example
  `CONFIG_ROOT` is `~/homelab-media-stack-data/config`. An install in another folder keeps working;
  set `MEDIA_STACK_DIR` for the aliases.
- Push notifications start with "media stack:" instead of "arr-stack:".

## 2.0.0 - 2026-09-29

### Added
- Runs on x86-64 as well as on a Raspberry Pi 5, and on Arch (and CachyOS) as well as Debian and
  Ubuntu. `install-host` checks every prerequisite first and prints the exact `apt-get` or
  `pacman` command for anything missing.
- Optional modules: the core (VPN, downloaders, Prowlarr, Radarr, Sonarr, Bazarr, Seerr,
  Jellyfin) always runs, and `COMPOSE_PROFILES` picks music, games, monitoring, stats,
  dashboards and Plex. Every script and check follows the choice.
- Hardware transcoding on Intel and AMD graphics with `compose.gpu.yml` and `HWACCEL`.
- `STORAGE_MOUNT` sets where the media disk is mounted, and an always-on disk (fstab or a bind
  mount) works without the hand-switched drive's udev rule.
- Documentation rewritten around diagrams of every flow, with a reference for every script,
  unit and setting, published as a site.
- Releases cut automatically from this changelog, immutable and signed.

### Changed
- Needle now comes from its published multi-arch image, `ghcr.io/bugrauluyurt/needle:1`,
  instead of a local build (`NEEDLE_IMAGE=needle:local` still runs your own).
- Update checks compare the image for the server's own architecture.
- health-check reads SMART data the same way for SATA, NVMe and USB drives.

### Security
- Jellyfin, Seerr and the games page answer only to home-network addresses, over IPv4 and IPv6,
  so a global IPv6 address or a router port forward no longer exposes them.
- The firewall refuses to load next to ufw or firewalld, or when Docker's nftables backend would
  bypass it, instead of leaving published ports open.
- qBittorrent keeps its CSRF and Host-header checks on, so a web page opened on a tailnet device
  can't forge requests to its login-free API.

### Removed
- The players for a TV plugged into the server (Kodi, Jellyfin Desktop) and their HDMI audio
  rule. Use a TV app such as Jellyfin's, Swiftfin or Neptune instead.

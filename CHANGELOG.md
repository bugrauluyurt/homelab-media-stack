# Changelog

What changed in each release. The stack uses [semantic versioning](https://semver.org): a major
version means you need to change your setup (a renamed setting, a removed module, a new mount),
a minor version adds features, and a patch fixes bugs. Write new entries under **Unreleased**,
under the heading that matches the change; the headings decide the next version, and merging
the release pull request publishes it ([how releases work](docs/operations/releasing.md)).

## Unreleased

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

# Changelog

What changed in each release. The stack uses [semantic versioning](https://semver.org): a major
version means you need to change your setup (a renamed setting, a removed module, a new mount),
a minor version adds features, and a patch fixes bugs. Write new entries under **Unreleased**,
under the heading that matches the change; the headings decide the next version, and merging
the release pull request publishes it ([how releases work](docs/operations/releasing.md)).

## Unreleased

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

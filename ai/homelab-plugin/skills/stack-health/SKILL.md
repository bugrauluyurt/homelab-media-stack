---
name: stack-health
description: Check whether the home media stack (Jellyfin, Seerr, Radarr, Sonarr, Lidarr, Prowlarr, Bazarr, qBittorrent behind the ProtonVPN tunnel, Navidrome, monitoring, backups) is healthy, and explain any failures. Use when asked if everything is working, after a reboot or change, or when something seems broken.
---

# Stack health

Safe to run at any time, but not strictly read-only: it creates and deletes a
hardlink test file on the media drive and starts short-lived `curlimages/curl`
containers. When the user asked for a look without changing anything, say so
before running it, or check individual services instead.

## Run it

```bash
STACK=${ARR_STACK_DIR:-$(git rev-parse --show-toplevel 2>/dev/null)}; [ -x "$STACK/scripts/health-check" ] || STACK=~/arr-stack
"$STACK/scripts/health-check"
```

It prints sections (STORAGE, SYSTEMD, SERVICES, BACKUPS, VPN, ...). Each line is
`OK` or `FAIL`, and the summary is `N passed, M failed`. The exit code is 0 only
when nothing failed. A yellow `UPDATES` line is information, not a failure.

For history ("since when is it down?", "has it been flaky?"), the Uptime
Kuma status page has every service's recent checks. Its JSON is at
`http://127.0.0.1:3003/api/status-page/heartbeat/stack?t=<now>`; the `t`
parameter avoids its 5-minute cache. Kuma also pushes DOWN/UP alerts to ntfy,
and `arr-health.timer` runs `health-check --notify` every 6 hours, pushing any
failure there too.

## Report

- If everything passed, say so in one line and include the count.
- For each FAIL, name the check in plain words, give the likely cause and the
  next step. The `stack-logs` skill has a list of known issues and their fixes.
- A FAIL just after a restart or update is often just a service still starting.
  Wait about a minute and run it again before calling it a problem.
- Don't fix anything without asking first. Recreating containers, restarting
  the VPN or editing `.env` all need the user's go-ahead.

## Common FAILs

| FAIL | Usual meaning |
|---|---|
| `<STORAGE_MOUNT> is mounted` | The media drive is off or unplugged; every other check depends on it |
| `forwarded port is in sync` | The VPN reconnected with a new port. `scripts/sync-port` fixes it, and a 15-minute timer also does. If `sync-port` says "no valid forwarded port", Proton gave none: see "No forwarded port at all" in the known issues |
| `qbittorrent bound to the tunnel` | qBittorrent lost gluetun's network after gluetun restarted. `scripts/stack-up` re-attaches it |
| `byparr ... healthy` | The Cloudflare solver's probe timed out while it was busy; usually clears by itself |
| `last backup under 48h old` | The nightly backup was skipped, usually because the drive was off at 04:30 |
| `firewall loaded ...` | The rules are missing, e.g. right after boot or a Docker restart. `arr-firewall.timer` restores them within 15 minutes; `sudo scripts/firewall` does it now |
| `qbittorrent: home network must log in` | Someone re-added the LAN to qBittorrent's no-login list. The next `scripts/sync-port` run (every 15 minutes) removes it |

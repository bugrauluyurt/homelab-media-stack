---
name: stack-logs
description: Troubleshoot a misbehaving media-stack service (Jellyfin, Seerr, Radarr, Sonarr, Lidarr, Prowlarr, Bazarr, qBittorrent, gluetun, slskd, Questarr, SFTPGo, Navidrome, Homepage, Glance, Scrutiny, ChangeDetection) by reading its logs and matching them against known issues. Use when a download, request, subtitle, playback or app problem needs diagnosing.
---

# Logs and troubleshooting

Read-only diagnosis. Propose fixes; don't apply them without asking.

```bash
STACK=${MEDIA_STACK_DIR:-$(git rev-parse --show-toplevel 2>/dev/null)}; [ -x "$STACK/scripts/stack-health" ] || STACK=~/homelab-media-stack
cd "$STACK"
docker compose ps --format '{{.Name}} {{.Status}}'            # what's running
docker logs --since 30m <service> 2>&1 | grep -iE 'error|warn|fatal|exception' | tail -30
```

Every container's name matches its compose service. The user can see the
same logs live in **Dozzle** (`http://<hostname>:8888`, read-only), and when a
service went down in **Uptime Kuma** (`:3003/status/stack`). Settings live in
`$CONFIG_ROOT/<service>` (see `.env`), outside the repo.

Before diagnosing, read `references/known-issues.md`. Most problems seen so far
are already listed there with their cause and fix.

## Rules
- Never print values from `.env` (API keys, passwords, the WireGuard key). Read
  them into variables and use them.
- The arr apps' API keys can be read with `sudo grep -oPm1 '(?<=<ApiKey>)[^<]+' $CONFIG_ROOT/<app>/config.xml`.
- `stack-health` confirms a fix; run it after any change the user approves.

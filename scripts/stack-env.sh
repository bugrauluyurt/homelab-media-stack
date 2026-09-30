# shellcheck shell=bash
# Sourced by the bash scripts: repo path and every .env value, exported.
# Used by: every bash script in scripts/.
# Changes: nothing itself.
REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
set -a; . "$REPO/.env"; set +a
export STORAGE_MOUNT=${STORAGE_MOUNT:-/mnt/storage}
# Every module runs unless .env lists the wanted profiles.
export COMPOSE_PROFILES=${COMPOSE_PROFILES:-*}

STATE_ROOT="$(dirname "$CONFIG_ROOT")/state"

# notify TITLE TAGS BODY: push to the ntfy channel, if one is configured.
notify() {
  [ -n "${NTFY_TOPIC:-}" ] || return 0
  curl -s -o /dev/null --max-time 15 -H "Title: $1" -H "Tags: $2" -d "$3" "${NTFY_SERVER:-https://ntfy.sh}/$NTFY_TOPIC"
}

# Pending image updates for node-exporter's textfile collector, renamed into place so a scrape never sees half a file.
write_update_metrics() {
  local dir="$STATE_ROOT/metrics" checked pending
  mkdir -p "$dir"

  checked=$(sed -n 's/^checked=//p' "$STATE_ROOT/updates" 2>/dev/null)
  pending=$(grep -c '^update ' "$STATE_ROOT/updates" 2>/dev/null)

  {
    echo "arr_image_updates_available ${pending:-0}"
    echo "arr_image_updates_checked_timestamp_seconds $(date -d "${checked:-@0}" +%s)"
  } > "$dir/updates.prom.tmp" && chmod 644 "$dir/updates.prom.tmp" && mv "$dir/updates.prom.tmp" "$dir/updates.prom"
}

# disk_of_mount PATH: the whole disk a mount lives on (a bind mount reads "/dev/x[/dir]").
disk_of_mount() {
  local source pkname
  source=$(findmnt -no SOURCE "$1" | sed 's/\[.*//')
  pkname=$(lsblk -no PKNAME "$source" | head -1)
  echo "/dev/${pkname:-${source#/dev/}}"
}

# service_enabled NAME: whether NAME is in an active compose profile.
service_enabled() {
  [ -n "${ENABLED_SERVICES:-}" ] || ENABLED_SERVICES=$(docker compose --project-directory "$REPO" config --services 2>/dev/null)
  grep -qx "$1" <<< "$ENABLED_SERVICES"
}

# json_get KEY: one top-level field of the JSON on stdin.
json_get() { python3 -c 'import json, sys; print(json.load(sys.stdin).get(sys.argv[1], ""))' "$1" 2>/dev/null; }

tunnel_ip() { docker exec gluetun sh -c "ip -4 -o addr show tun0 2>/dev/null | awk '{print \$4}' | cut -d/ -f1" 2>/dev/null; }
forwarded_port() { docker exec gluetun cat /tmp/gluetun/forwarded_port 2>/dev/null | tr -d '[:space:]'; }
qbit_prefs() { docker exec qbittorrent curl -s --max-time 10 "http://127.0.0.1:$QBIT_PORT/api/v2/app/preferences" 2>/dev/null; }

vpn_healthy() {
  [ "$(docker inspect -f '{{.State.Health.Status}}' gluetun 2>/dev/null)" = healthy ]
}

wait_gluetun_healthy() {
  timeout "${1:-180}" bash -c 'until [ "$(docker inspect -f "{{.State.Health.Status}}" gluetun 2>/dev/null)" = healthy ]; do sleep 3; done'
}

# qBittorrent and slskd share gluetun's network namespace; when gluetun is restarted or
# recreated under them they keep "running" with a dead network until they are recreated too.
vpn_apps_attached() {
  curl -sf -o /dev/null --max-time 8 "http://127.0.0.1:$QBIT_PORT" &&
    { ! service_enabled slskd || curl -sf -o /dev/null --max-time 8 http://127.0.0.1:5030/health; }
}

# Naming a service starts it even when its profile is off, so slskd is named only when enabled.
reattach_vpn_apps() {
  local vpn_apps=(qbittorrent)
  service_enabled slskd && vpn_apps+=(slskd)

  vpn_healthy || { echo "VPN is not healthy; leaving downloaders untouched."; return 1; }
  docker compose --project-directory "$REPO" up -d --no-deps --force-recreate "${vpn_apps[@]}" || return 1

  for _ in $(seq 1 30); do
    vpn_healthy || return 1
    vpn_apps_attached && return 0
    sleep 2
  done
  echo "Downloaders are not ready yet; the next port-sync run will retry."
  return 1
}

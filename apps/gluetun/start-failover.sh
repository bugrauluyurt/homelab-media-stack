#!/bin/sh
set -eu

for server_file in /gluetun/verified-servers/manifest.json /gluetun/verified-servers/protonvpn.json; do
  if [ ! -f "$server_file" ] || [ ! -r "$server_file" ] || [ ! -s "$server_file" ]; then
    echo "Required VPN server file is missing, empty, or unreadable: $server_file" >&2
    exit 1
  fi
done

exec /gluetun-entrypoint "$@"

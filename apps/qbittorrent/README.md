# qBittorrent seed config

Copied to `$CONFIG_ROOT/qbittorrent/qBittorrent/` before first start.

- `LocalHostAuth=false` lets gluetun's port-forward hook set the listen port
  via the local API when Proton hands out a new forwarded port.
- `AuthSubnetWhitelist` is only a starting value: `scripts/vpn-port-sync` sets
  the login-free networks to exactly the tailnet (`100.64.0.0/10`) and the
  Docker bridge (`172.16.0.0/12`), so Radarr and Sonarr reach it at
  `gluetun:8080` without storing another credential. The home network always
  has to log in; `stack-health` fails if a login-free range overlaps `LAN_CIDR`.
- `CSRFProtection` and `HostHeaderValidation` stay on: the login-free tailnet
  would otherwise let any web page open on a tailnet device forge requests to
  the API. `scripts/vpn-port-sync` keeps the accepted Host names (`gluetun`,
  `127.0.0.1`, the host's names and IPv4 addresses) current. Dashboard links
  still work because Homepage and Glance send no Referer. Browser extensions
  that send torrents are refused (their Origin is the extension).
- Limit: qBittorrent matches accepted hosts as substrings, so a targeted DNS
  rebinding attack (a page on a name like `gluetun.attacker.example` that
  resolves to this host) is not stopped. Only a login on the tailnet would
  close that.
- Categories `radarr` and `sonarr` save into `/data/torrents/{movies,tv}`,
  on the same filesystem as the library so imports hardlink instead of copy.

---
name: vpn-check
description: Verify that all torrent and Soulseek traffic goes through the ProtonVPN tunnel and cannot leak to the home IP, including the kill switch. Use when asked whether the VPN is working, whether torrents are safe or private, or after any change to gluetun, qBittorrent or slskd.
---

# VPN and kill-switch check

Read-only. P2P must never leave from the home IP, so treat any leak as urgent and
say so plainly.

## 1. Exit IP and forwarded port

```bash
STACK=${MEDIA_STACK_DIR:-$(git rev-parse --show-toplevel 2>/dev/null)}; [ -x "$STACK/scripts/health-check" ] || STACK=~/homelab-media-stack
"$STACK/scripts/leak-test"
```

PASS means qBittorrent's public IP differs from the host's and matches gluetun's,
and Proton's forwarded port is wired into qBittorrent.

## 2. Structural checks (a snapshot can't prove these)

```bash
G=$(docker inspect -f '{{.Id}}' gluetun)
for c in qbittorrent slskd; do echo "$c: $(docker inspect -f '{{.HostConfig.NetworkMode}}' $c | grep -q "$G" && echo inside gluetun || echo NOT IN TUNNEL)"; done
docker exec gluetun wget -qO- -T 10 https://ipv4.icanhazip.com        # slskd shares this exit
docker exec qbittorrent curl -s http://127.0.0.1:8080/api/v2/app/preferences | python3 -c 'import json,sys;p=json.load(sys.stdin);print("bound:",p["current_network_interface"],p.get("current_interface_address"))'
docker exec qbittorrent sh -c 'curl -s -m 8 --interface eth0 https://ipv4.icanhazip.com && echo LEAK || echo "bypass blocked"'
docker exec gluetun sh -c 'iptables -S OUTPUT | head -1; cat /proc/sys/net/ipv6/conf/all/disable_ipv6'
```

Expected:
- Both P2P clients are inside gluetun.
- qBittorrent is bound to `tun0`.
- Going around the tunnel via eth0 is blocked.
- The firewall's default is `-P OUTPUT DROP` and IPv6 is disabled (`1`).

## Report

A table with each check against what's expected, then one conclusion. Mention
that the indexer searches (Prowlarr, the *arr apps, Byparr) are ordinary HTTPS from
the home IP and not P2P, unless the user has already chosen to route them through
the VPN. Don't change VPN settings without asking. The VPN must never exit in
the US; it uses `VPN_COUNTRIES` from `.env`.

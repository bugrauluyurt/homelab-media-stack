# VPN and ports

This page explains how torrent and Soulseek traffic is kept inside the VPN, how Proton's forwarded
port reaches qBittorrent, and how the stack repairs itself when the tunnel reconnects or the port
goes missing. It is for anyone running the stack or debugging the downloaders. Setting the VPN up
for the first time is in [Getting started](../getting-started.md).

```mermaid
flowchart LR
  subgraph ns["gluetun's network namespace"]
    gluetun["gluetun: WireGuard and firewall"]
    qbit["qBittorrent, bound to tun0"]
    slskd["slskd"]
  end
  apps["Radarr, Sonarr, Lidarr, Questarr, Cleanuparr, Needle"] -->|"gluetun:8080, gluetun:5030"| ns
  kuma["Uptime Kuma"] -->|"gluetun:8000, port only"| gluetun
  gluetun ==>|"WireGuard tunnel"| proton["Proton VPN server"]
  proton --> peers["Trackers, peers, Soulseek"]
  sab["SABnzbd, outside the VPN"] -->|SSL| provider["Usenet provider"]
```

## gluetun

The VPN runs inside the `gluetun` container, not on the server itself. The server, Tailscale,
Jellyfin, Plex and the arr apps are untouched by it, so your own streams stay direct.

- **Custom WireGuard by default.** gluetun runs with `VPN_SERVICE_PROVIDER=custom` and
  `VPN_TYPE=wireguard`. The client private key lives only in `.env` (`WIREGUARD_PRIVATE_KEY`); the
  Proton server's endpoint and public key are in `$CONFIG_ROOT/gluetun/wireguard/wg0.conf`
  (mode `0600`), without a `PrivateKey` line, because values in that file override the environment.
  Use a dedicated Proton configuration for a P2P server with NAT-PMP on and Moderate NAT off (they
  conflict). Custom mode has no automatic server failover: changing the endpoint or key, and
  recreating gluetun with its downloaders, is a deliberate step.
- **Exit country.** `VPN_COUNTRIES` lists the countries the exit may be in. It doesn't choose a
  server in custom mode (the endpoint in `wg0.conf` does); `stack-health` reads the country from gluetun's log and
  fails if it isn't listed, and always fails for the United States.
- **Port forwarding.** `VPN_PORT_FORWARDING=on` with Proton's provider. gluetun asks the server for
  a port over NAT-PMP and writes it to `/tmp/gluetun/forwarded_port` inside the container.
- **`VPN_PORT_FORWARDING_UP_COMMAND`.** Each time gluetun gets a port, it posts it straight to
  qBittorrent's local API as `listen_port` (random port and UPnP off). This works without a login
  because qBittorrent's `LocalHostAuth` is off. A line in gluetun's log saying the up command exited
  with status 4 only means qBittorrent wasn't up yet.
- **The shared namespace.** qBittorrent and slskd run with `network_mode: service:gluetun`: they
  have no network of their own, only gluetun's, and start once gluetun is healthy. gluetun publishes
  their ports (`QBIT_PORT` and 5030), and other containers reach them as `gluetun:8080` and
  `gluetun:5030`.
- **The kill switch.** gluetun's firewall drops everything that doesn't go through the tunnel. If
  the tunnel drops, qBittorrent and slskd lose the internet instead of falling back to your home
  address. `FIREWALL_OUTBOUND_SUBNETS` lets them answer your home network (`LAN_CIDR`) and the
  tailnet (`100.64.0.0/10`), so their web pages still work.
- **IPv6 off.** The namespace has IPv6 disabled (`net.ipv6.conf.all.disable_ipv6=1`), since the
  tunnel carries none. `DOT_IPV6: "off"` stops gluetun's DNS from handing out AAAA records: those
  addresses have no route out, and every tracker would fail with "Operation not permitted".
- **`BLOCK_MALICIOUS: "off"`.** gluetun's malicious-domain blocklist also blocks public torrent
  trackers, which then fail DNS with NXDOMAIN.
- **One forwarded port.** Proton forwards a single port and qBittorrent holds it, so slskd reaches
  only Soulseek peers that accept incoming connections.
- **SABnzbd stays outside.** Usenet is SSL and download only, nothing is shared, so SABnzbd runs on
  the normal Docker network at full line speed. Adding Usenet changed nothing about the torrents'
  VPN. See [Media requests](media-requests.md).

## Verified Proton server pool

The optional `compose.vpn-failover.yml` preset enables Proton's provider mode with an ordered
pool of P2P servers. It leaves the base custom-mode setup unchanged. When gluetun's health
recovery reconnects, ordered selection advances through the eligible servers. Failover can take
several minutes because health checks and NAT-PMP retries have their own delays. A simulated
gateway outage on the pinned build recovered in about 5 minutes 13 seconds; this is an
observation, not a recovery deadline. An outage affecting every endpoint still needs intervention.

The preset keeps the existing firewall, IPv6 policy, published ports, and downloader namespace.
It requires both `VPN_COUNTRIES` and `VPN_SERVER_NAMES`, filters to port-forwarding servers,
and disables the automatic server-list updater. The importer accepts standard server names
and rejects free and Secure Core configurations.
Imported records are preferred over the bundled catalog in the pinned gluetun build. The
importer checks downloaded configuration data offline; it does not prove that a server is
reachable or currently grants a forwarded port.

### Import and enable

1. Download configurations for at least two different Proton P2P servers in the same allowed
   country from [Proton's downloads page](https://account.protonvpn.com/downloads). Enable
   **NAT-PMP** and disable **Moderate NAT**. Use the standard IPv4 address `10.2.0.2/32` and
   endpoint port `51820`; the importer rejects other layouts. Keep these secret-bearing files
   outside the repository. Each server name must match its `# NL#1` style label in `[Peer]`.
2. Back up `.env` and `$CONFIG_ROOT/gluetun`. Before importing into an existing installation,
   stop qBittorrent, slskd when its module is enabled, and gluetun. Coordinate with any running
   recovery or update job so it cannot restart them during this operation.
3. Import the endpoint and public-key records. Replace the example names and paths with your
   downloaded files. Loading `.env` supplies `CONFIG_ROOT` to this shell; the importer itself
   neither loads nor edits `.env`:

   ```bash
   set -a; . ./.env; set +a
   ./scripts/vpn-import-servers --country Netherlands \
     --output-dir "$CONFIG_ROOT/gluetun/verified-servers" \
     --server 'NL#1=/path/to/first.conf' \
     --server 'NL#2=/path/to/second.conf'
   ```

   This writes `manifest.json` and `protonvpn.json`, containing public peer records and no
   client private key. Every input is validated before either file changes. The country is
   the label you provide, so verify the actual exit country after connecting.
4. Copy the client `PrivateKey` from one of those configurations into `WIREGUARD_PRIVATE_KEY`
   in `.env`. Set `VPN_COUNTRIES` to the imported country and `VPN_SERVER_NAMES` to the
   comma-separated names printed by the importer. Set:

   ```dotenv
   COMPOSE_FILE=docker-compose.yml:compose.vpn-failover.yml
   ```

   If GPU transcoding is enabled, include both presets:

   ```dotenv
   COMPOSE_FILE=docker-compose.yml:compose.gpu.yml:compose.vpn-failover.yml
   ```

5. Validate the Compose configuration and recreate gluetun by itself:

   ```bash
   set -a; . ./.env; set +a
   docker compose config -q
   docker compose up -d --no-deps --force-recreate gluetun
   docker inspect -f '{{.State.Health.Status}}' gluetun
   docker compose logs --tail 100 gluetun
   docker exec gluetun cat /tmp/gluetun/forwarded_port
   ```

   Wait for healthy status and a valid forwarded port, and confirm the connection logs name
   an imported server and an allowed exit country. Check every imported endpoint individually
   before relying on it, temporarily selecting its name, recreating gluetun, and checking health,
   country and NAT-PMP each time. Restore the complete `VPN_SERVER_NAMES` pool and recreate
   gluetun once more before starting downloaders. Reload `.env` in this shell after every
   selector change; exported values otherwise override edits to the file.
6. After the VPN is ready, the existing recovery script recreates enabled downloaders in
   gluetun's current namespace and synchronizes qBittorrent's port:

   ```bash
   ./scripts/vpn-port-sync
   ./scripts/vpn-leak-test
   ./scripts/stack-health
   ```

The repository's `apps/gluetun/failover-wg0.conf` mounts read-only over
`/gluetun/wireguard/wg0.conf`. It contains only the standard address, allowed IPs, and keepalive.
This prevents a previously installed fixed `Endpoint`, `PublicKey`, or `PrivateKey` from
overriding pool selection or `.env`. The old host file is preserved for rollback. The seed and
`apps/gluetun/start-failover.sh` wrapper mount read-only. The imported server directory mounts
read-write because gluetun updates its storage manifest and caches during startup even with
the automatic updater disabled. Every mount uses `create_host_path: false`, so a missing source
directory or repository file fails container creation. The wrapper requires both imported JSON
files to be readable, nonempty regular files before starting gluetun. It does not validate JSON
content or guarantee that gluetun will accept a corrupt or incompatible catalog.

### Refresh, restore, and upgrade

When Proton changes an endpoint, download replacement configurations and repeat the stopped
import and validation sequence above. The importer atomically replaces changed files.
**Recreate gluetun after each refresh** to apply the current pool, selectors, and Compose settings
together. Recreate the downloaders through `vpn-port-sync`
after gluetun is healthy and has a port. A private key remains valid until revoked or otherwise
rejected by Proton; an endpoint failure alone does not establish that the key needs rotating.

`stack-backup` includes `$CONFIG_ROOT/gluetun/verified-servers` and `.env`; it excludes the
regenerable default `gluetun/servers` cache. A full restore needs both imported JSON files,
the matching `.env` selectors and private key, and this repository's Compose preset, seed, and wrapper.
Confirm the files exist before recreating gluetun, then validate the VPN before its clients.
To return to custom mode, remove `compose.vpn-failover.yml` from `COMPOSE_FILE`, retain any GPU
preset, and confirm the preserved host `wg0.conf` and `.env` key still work together before
recreating gluetun and its clients.

The preset pins a gluetun multi-platform image digest for amd64 and arm64 because the imported
server schema and `preferred` behavior depend on that build. `stack-update-check` reports
digest-pinned images as current without registry comparisons. Upgrading this image is a manual
repository change: validate the provider JSON schema, ordered selection, country and name
filters, file precedence, NAT-PMP, failover, and leak protection against the new build first.
The preferred server file is not a fail-closed boundary: a corrupt file, incompatible schema,
or changed image can cause gluetun to fall back to its bundled catalog. The explicit filters
still constrain selection, but verify the selected endpoint in startup logs after changes.

## qBittorrent's side

The seed config,
[`apps/qbittorrent/qBittorrent.conf`](https://github.com/bugrauluyurt/homelab-media-stack/blob/main/apps/qbittorrent/qBittorrent.conf),
is copied into `$CONFIG_ROOT/qbittorrent/qBittorrent/` before the first start, and
[`vpn-port-sync`](../reference/scripts.md#vpn-port-sync) keeps the live settings in line with it.

- **Bound to the tunnel.** qBittorrent binds to `tun0` and its current address. gluetun routes
  anything sent from the container's Docker bridge address back out `eth0`, so the published web
  page can reply; a qBittorrent bound there would send tracker traffic outside the tunnel, where the
  firewall drops it, and every tracker would report "Operation not permitted". Bound to the tunnel
  address, traffic goes through `tun0`, and it can't leak if the tunnel disappears.
- **DHT remains enabled.** Both DHT-on established sessions and DHT-off cold starts passed
  testing, while a reboot with DHT on failed. These observations do not isolate DHT as the cause;
  startup traffic volume and transient upstream issues remain hypotheses. Recovery scripts do
  not override DHT or impose new peer, queueing or bandwidth limits. Before replacing credentials
  or changing peer discovery, inspect the tunnel and traffic evidence. See the
  [troubleshooting notes](https://github.com/bugrauluyurt/homelab-media-stack/blob/main/ai/homelab-plugin/skills/stack-logs/references/known-issues.md#vpn-fails-shortly-after-torrents-start-then-recovers-about-an-hour-later).
- **Login-free networks.** The Docker network (`172.16.0.0/12`: the arr apps, Homepage) and the
  tailnet (`100.64.0.0/10`: your phone) skip the login, so the apps need no stored credential. The
  home network always has to log in; `stack-health` fails if a login-free range overlaps
  `LAN_CIDR`.
- **CSRF and Host checks stay on.** Without them, any web page open on a tailnet device could forge
  requests to the login-free API. The accepted host names are `gluetun`, `127.0.0.1`, `HOST_NAME`,
  `HOST_NAME.local`, `HOST_NAME.*.ts.net` and the server's own IPv4 addresses. Dashboard links still
  work because Homepage and Glance send no Referer; browser extensions that send torrents are
  refused, since their Origin is the extension.
- **A known limit.** qBittorrent matches accepted hosts as substrings, so a targeted DNS rebinding
  attack (a page on a name like `gluetun.attacker.example` that resolves to the server) isn't
  stopped. Only a login on the tailnet would close that.

## vpn-port-sync

[`vpn-port-sync`](../reference/scripts.md#vpn-port-sync) reconciles qBittorrent with the live tunnel. It
runs from [`arr-port-sync.timer`](../reference/systemd.md#arr-port-synctimer) 90 seconds after boot
and then every 15 minutes, from `stack-up` as soon as the tunnel is healthy after the stack starts,
and by hand. In order, it:

1. Reads VPN health, the tunnel address (`tun0` inside gluetun) and the forwarded port.
2. Requires a healthy VPN, a tunnel address and a port between 1024 and 65535. Otherwise it
   follows the [missing-port rules](#when-proton-gives-no-port). Once ready, it reattaches stopped
   or detached downloaders, even after spontaneous VPN recovery, without restarting other
   services. It refuses to change preferences if qBittorrent's API response is invalid.
3. Binds qBittorrent to `tun0` and the current tunnel address, if it isn't already.
4. Sets `listen_port` to the forwarded port, if it differs.
5. Sets the login-free networks to exactly the tailnet and the Docker network.
6. Turns the web page's CSRF and Host checks on with the current host names.
7. Checks, inside gluetun, that something listens on the tunnel address and port; it exits 1 with
   a warning if not.

A run with nothing to change prints "already in sync". Every step only writes when the value
differs, so running it again is harmless.

## A reconnect

Proton hands out a new forwarded port when the tunnel reconnects, and the tunnel address can change
too. gluetun's up command fixes the port at once; the next `vpn-port-sync` run fixes the rest:

```mermaid
sequenceDiagram
  participant P as Proton
  participant G as gluetun
  participant Q as qBittorrent
  participant T as arr-port-sync.timer
  participant S as vpn-port-sync
  P->>G: Tunnel reconnects with a new forwarded port
  G->>G: Write the port file
  G->>Q: Up command sets listen_port
  Note over Q: Binding may still name the old tunnel address
  T->>S: Next run, 15 minutes at most
  S->>G: Read the tunnel address and the port
  S->>Q: Read the preferences
  S->>Q: Rebind to the tunnel address, fix the port if needed
  S->>Q: Reapply login-free networks and WebUI checks
  S->>G: Confirm the tunnel address and port are listening
```

After a boot, qBittorrent starts on its saved port, which is stale by then. `stack-up` runs
`vpn-port-sync` as soon as gluetun is healthy, and the timer runs 90 seconds after boot, so a
`stack-health` in the first minute may catch "forwarded port is in sync" failing mid-flight.

## When Proton gives no port

Proton sometimes stops answering NAT-PMP after a reconnect while the tunnel stays up. gluetun gives
up after nine tries. Torrents stay inside the VPN but no peers can connect in, so they slow down;
Usenet is unaffected. `vpn-port-sync` heals this by itself:

```mermaid
stateDiagram-v2
  state "Port in sync" as Synced
  state "Port missing" as Missing
  state "Restarting gluetun" as Restarting
  state "Recreating qBittorrent and slskd" as Reattach
  [*] --> Synced
  Synced --> Missing: no valid port, time noted
  Missing --> Missing: under 15 min, or last restart under 2 h ago
  Missing --> Reattach: VPN and port recover by themselves
  Missing --> Restarting: missing 15 min or more
  Restarting --> Reattach: healthy with a port
  Restarting --> Missing: still unavailable after 3 min
  Reattach --> Synced: clients answer and port is verified
  Reattach --> Missing: recovery incomplete, retry next run
```

- The 15 minutes (`MISSING_LIMIT`) are measured by the clock from when a run first saw the port
  missing, not by counting failed runs: at boot two runs come a minute apart. A time noted before
  the last boot is ignored, so the count starts again with each boot.
- At most one restart every two hours (`HEAL_EVERY`), so a long Proton outage doesn't mean a
  restart and a push every half hour.
- The restart is `docker compose restart --no-deps gluetun`; it waits up to 3 minutes for a tunnel address,
  a valid port and a healthy gluetun. Only then may it recreate qBittorrent and slskd in the new
  namespace (see [below](#re-attaching-qbittorrent-and-slskd)). A failed wait leaves them untouched.
- Every later run can reattach missing downloaders after the tunnel recovers, without another
  VPN restart. This uses the existing timer, not an additional watcher.
- It pushes **"VPN forwarded port restored"** only after clients answer and their port is verified,
  or **"VPN still unavailable"** if the restart did not restore readiness.
- The state lives in `$STATE_ROOT/port-forward-missing-since` and
  `$STATE_ROOT/port-forward-last-heal`.

To do it by hand (it pauses torrents and Soulseek for about a minute):

```bash
docker compose restart gluetun                    # wait until it's healthy
docker compose up -d --force-recreate qbittorrent slskd
./scripts/vpn-port-sync && ./scripts/vpn-leak-test
```

## Re-attaching qBittorrent and slskd

qBittorrent and slskd share gluetun's network namespace. When gluetun is restarted or recreated
under them, they keep "running" with a dead network, and the apps get "connection refused" until
they are recreated. [`stack-env.sh`](../reference/scripts.md#stack-envsh) holds the two helpers
every script uses:

- `vpn_apps_attached` asks qBittorrent's web page (`127.0.0.1:QBIT_PORT`) and, when the music module
  is on, slskd's `/health` on port 5030.
- `reattach_vpn_apps` runs `docker compose up -d --force-recreate qbittorrent` (plus `slskd` when
  the music module is on; naming a service would start it even with its profile off).

`stack-up` re-attaches them at boot when they don't answer, `vpn-port-sync` after its gluetun restart,
and `stack-update` after updating gluetun (see [Updates](updates.md)).

## Leak test

[`vpn-leak-test`](../reference/scripts.md#vpn-leak-test) proves the torrent traffic leaves through Proton:

1. It asks `https://api.ipify.org` (plain text for every client; some services send HTML to `wget`,
   which silently breaks the comparison) for the public IPv4 address three times: from the server,
   from gluetun and from qBittorrent.
2. **LEAK** (exit 1) if gluetun's address equals the server's, or qBittorrent's differs from
   gluetun's. **INCONCLUSIVE** (exit 2) if any of the three couldn't reach the service. **PASS**
   otherwise.
3. It then compares gluetun's forwarded port with qBittorrent's `listen_port` and suggests
   `vpn-port-sync` on a mismatch. It reads gluetun's port file, because gluetun's control-server API
   requires authentication.

Right after qBittorrent restarts, expect an inconclusive result for about a minute: many torrents
re-announcing at once briefly swamp the VPN's DNS.

## The forwarded-port monitor

gluetun's control server (port 8000, not published) requires authentication on every route.
[`apps/gluetun/auth.toml`](https://github.com/bugrauluyurt/homelab-media-stack/blob/main/apps/gluetun/auth.toml)
opens exactly one route without credentials, read-only: `GET /v1/portforward`. Only containers on
the `arr` network can reach it.
[`configure-uptime-kuma.py`](../reference/scripts.md#configure-uptime-kumapy) adds a
**"vpn forwarded port"** JSON monitor on `http://gluetun:8000/v1/portforward` that expects `port`
above 0, next to gluetun's Docker health and the qBittorrent and slskd ports. When Proton stops
handing out a port, Kuma sends DOWN, then UP once a new one is in place. See
[Monitoring](monitoring.md).

`stack-health` covers the rest: gluetun running, the exit country, qBittorrent answering and
reachable from Radarr, bound to the tunnel, the forwarded port in sync, the home network required to
log in, and cross-site requests refused.

## Scripts and units involved

| Name | Role | Reference |
|---|---|---|
| `vpn-port-sync` | Binds qBittorrent to the tunnel, syncs the port and WebUI settings, heals a missing port | [scripts](../reference/scripts.md#vpn-port-sync) |
| `arr-port-sync.timer` | Runs `vpn-port-sync` 90 seconds after boot, then every 15 minutes | [systemd](../reference/systemd.md#arr-port-synctimer) |
| `arr-port-sync.service` | The `vpn-port-sync` job, after `arr-stack.service` | [systemd](../reference/systemd.md#arr-port-syncservice) |
| `stack-up` | Re-attaches the VPN apps and syncs the port at boot | [scripts](../reference/scripts.md#stack-up) |
| `stack-env.sh` | Tunnel, port and re-attach helpers | [scripts](../reference/scripts.md#stack-envsh) |
| `vpn-leak-test` | Proves qBittorrent exits through Proton | [scripts](../reference/scripts.md#vpn-leak-test) |
| `configure-uptime-kuma.py` | The forwarded-port monitor | [scripts](../reference/scripts.md#configure-uptime-kumapy) |
| `stack-health` | The VPN checks | [scripts](../reference/scripts.md#stack-health) |
| `apps/gluetun/auth.toml` | The one open control-server route | [file](https://github.com/bugrauluyurt/homelab-media-stack/blob/main/apps/gluetun/auth.toml) |

## When it goes wrong

- **Apps say "Failed to connect to qBittorrent":**
  [qBittorrent stops answering after gluetun restarts](https://github.com/bugrauluyurt/homelab-media-stack/blob/main/ai/homelab-plugin/skills/stack-logs/references/known-issues.md#qbittorrent-stops-answering-after-gluetun-restarts).
- **Port out of sync:**
  [forwarded port out of sync](https://github.com/bugrauluyurt/homelab-media-stack/blob/main/ai/homelab-plugin/skills/stack-logs/references/known-issues.md#forwarded-port-out-of-sync).
- **"vpn forwarded port" DOWN in Kuma:**
  [no forwarded port at all](https://github.com/bugrauluyurt/homelab-media-stack/blob/main/ai/homelab-plugin/skills/stack-logs/references/known-issues.md#no-forwarded-port-at-all-vpn-forwarded-port-down-in-kuma).
  Act only if ntfy said "VPN still has no forwarded port".
- **Torrents at 0 peers, "Operation not permitted":**
  [trackers say "Operation not permitted"](https://github.com/bugrauluyurt/homelab-media-stack/blob/main/ai/homelab-plugin/skills/stack-logs/references/known-issues.md#torrents-stuck-at-0-peers-trackers-say-operation-not-permitted).
- **Trackers say "Host not found":**
  [BLOCK_MALICIOUS or a dead tracker](https://github.com/bugrauluyurt/homelab-media-stack/blob/main/ai/homelab-plugin/skills/stack-logs/references/known-issues.md#trackers-say-host-not-found).
- **Lidarr can't reach slskd:**
  ["Connection refused (gluetun:5030)"](https://github.com/bugrauluyurt/homelab-media-stack/blob/main/ai/homelab-plugin/skills/stack-logs/references/known-issues.md#lidarr-connection-refused-gluetun5030-from-slskddownloadmanager).
- **Never** move the exit to the US or take qBittorrent or slskd out of gluetun's network:
  [things never to do](https://github.com/bugrauluyurt/homelab-media-stack/blob/main/ai/homelab-plugin/skills/stack-logs/references/known-issues.md#things-never-to-do).

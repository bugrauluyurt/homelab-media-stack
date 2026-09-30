# Known issues and their fixes

Each entry says what you see, why it happens, and what to do.

## qBittorrent stops answering after gluetun restarts
- **Symptom:** Radarr, Sonarr, Lidarr or Questarr say "connection refused" to
  `gluetun:8080` or "Failed to connect to qBittorrent", or `stack-health` fails
  "qbittorrent bound to the tunnel". qBittorrent itself still shows as running.
- **Cause:** qBittorrent and slskd live in gluetun's network namespace. When
  gluetun is recreated they keep running, but their network is gone.
- **Fix:** `scripts/vpn-port-sync` reattaches them once gluetun is healthy and has a valid forwarded
  port. The existing timer also restores clients left stopped during an outage. It does not
  recreate clients while the VPN is unhealthy, or restart unrelated services.

## VPN fails shortly after torrents start, then recovers about an hour later
- **Observed:** two Netherlands endpoints connected initially, then lost NAT-PMP and WireGuard
  connectivity after qBittorrent started. Lower connection limits and queueing did not prevent it.
  With DHT disabled, the original endpoint stayed connected during validation at the usual upload
  cap, with queueing off and the original peer limits restored. A later 10-minute test that
  re-enabled DHT on the established session also stayed healthy, with downloads and uploads.
  This did not reproduce the failure and does not prove DHT alone caused it. The longer DHT-on
  trial ran without VPN errors for about 3 hours 43 minutes, then failed shortly after reboot:
  VPN connected at 23:17 UTC, downloaders started, resets began at 23:18:51 and NAT-PMP failed
  at 23:20. The same credentials recovered around 00:20. Subsequent DHT-off cold starts and a
  VPN restart with downloader reattachment stayed connected under upload traffic.
- **Suspected cause:** an upstream traffic-triggered restriction, consistent with reports about
  Proton's anti-abuse system. DHT, startup bursts and transient provider issues remain hypotheses;
  the provider-side reason is not confirmed. Do not assume every timeout is this issue.
- **Current policy:** DHT stays enabled at the owner's request. Passing DHT-off cold starts is
  not proof that DHT caused earlier failures; startup torrent volume is another hypothesis.
  Recovery scripts do not override DHT, peer limits, queueing or bandwidth. No extra watcher or
  scheduler was added. Preserve failure evidence before further changes; do not replace
  credentials or lower traffic limits without evidence and approval. A temporary upstream block
  remains a hypothesis, not a confirmed provider diagnosis.
- **Check:** read WireGuard handshake age, tunnel traffic, forwarded port and the live `dht`
  preference. Validate beyond the previous failure window with the downloaders running, not just
  an initial Docker healthy status. Never bypass the VPN to restore connectivity.

## Forwarded port out of sync
- **Cause:** Proton assigns a new port on every reconnect.
- **Fix:** `scripts/vpn-port-sync`. A 15-minute timer also does it. An "up command
  exit status 4" line in gluetun's log just means qBittorrent wasn't up yet; it's harmless.
- **Right after a reboot** `stack-health` may fail "forwarded port is in sync": qBittorrent
  comes back on its saved, now stale port. `scripts/stack-up` re-syncs it once the tunnel
  reports healthy, and `arr-port-sync.timer` runs 90 seconds after boot, so a check in the
  first minute can catch it mid-flight. Run `scripts/vpn-port-sync` to fix it at once.

## Torrents stuck at 0 peers, trackers say "Operation not permitted"
- **Cause 1:** qBittorrent bound to the Docker bridge instead of the VPN tunnel. gluetun
  routes traffic from the bridge address back out `eth0` so the published WebUI can reply,
  so tracker packets leave outside the tunnel and gluetun's firewall drops them.
- **Fix:** `scripts/vpn-port-sync` binds qBittorrent to the tunnel's current address. That
  address changes on every Proton reconnect, which is why a timer runs it every 15 minutes.
- **Cause 2:** DNS answered with IPv6 (AAAA) addresses the tunnel has no route for.
  `DOT_IPV6: "off"` on gluetun in `docker-compose.yml` prevents it; keep it off.

## Downloads from one private tracker stall at 0 seeds ("ratio insuffisant")
- **Symptom:** downloads from one private or semi-private tracker sit at 0% with 0 seeds and
  0 peers, although the search showed seeders. qBittorrent → the torrent → **Trackers** shows the
  tracker refusing the announce, e.g. TR4KER's "ratio insuffisant; uploadez avant de télécharger".
- **Cause:** the account's ratio is below the tracker's minimum, so it hands out no peers. Private
  torrents have DHT and PeX off, so the tracker is their only source. Well-seeded French TV has
  hardly any leechers, so seeding it barely raises the ratio. `configure-indexers.py` keeps the account
  trackers on Prowlarr's `RSS only` app profile so backlog searches can't drain the ratio again.
- **What happens already:** Cleanuparr's stall rule removes such a download after about an hour
  (from qBittorrent too) and blocklists it, and the app searches again.
- **Fix:** raise the ratio on the tracker's site (bonus points, freeleech). If the apps keep
  picking that tracker, switch it off in Prowlarr until then and re-run
  `scripts/configure-questarr.py`. Lowering its priority won't steer around it: the apps rank
  quality and custom format score before indexer priority.

## Trackers say "Host not found"
- **Cause:** gluetun's `BLOCK_MALICIOUS` DNS filter also blocks public tracker domains, which
  then fail with NXDOMAIN. It is `"off"` in `docker-compose.yml`; keep it off.
- Some tracker domains are simply dead (`opentracker.i2p.rocks`, for one). Check the name with
  `getent hosts <domain>` before blaming the VPN.

## No forwarded port at all ("vpn forwarded port" DOWN in Kuma)
- **Symptom:** Kuma alerts "vpn forwarded port"; `vpn-port-sync` says "no valid forwarded
  port"; gluetun's log shows `port forwarding ... i/o timeout (tries 1 ... 9)` and then
  gives up. The tunnel is still up and torrents stay inside it, but get no incoming peers.
- **Cause:** the Proton server stopped answering NAT-PMP after a reconnect.
- **Usually fixes itself:** `vpn-port-sync` restarts gluetun once the port has been missing 15 min
  (at most once every 2 h; state in `$STATE_ROOT/port-forward-*`, reset at boot) and reports on ntfy.
  Act only if the user got "VPN still has no forwarded port".
- **Manual fix (ask first, it pauses torrents and Soulseek for about a minute):**
  `docker compose restart gluetun`, wait until it's healthy and
  `/tmp/gluetun/forwarded_port` has a number, then
  `docker compose up -d --force-recreate qbittorrent slskd` and `scripts/vpn-port-sync`.
  Confirm with `scripts/vpn-leak-test`.

## Questarr says "added to qBittorrent" but nothing downloads
- **Cause:** Prowlarr writes the host it was called on into its download links,
  and Questarr rejects links whose host differs from the indexer URL.
- **Fix:** Prowlarr has a fixed IP (`PROWLARR_IP`, 172.18.0.200), and Questarr's
  indexers must use it. Re-run `scripts/configure-questarr.py`, which also prunes
  stale entries.
- Questarr never picks a release itself; the user chooses one. Finished downloads may stay
  untracked; use Claim on its Downloads page.

## Jellyfin home screen shows "Nothing here"
- **Cause:** Home Screen Sections 3.0.2 returns nothing when the row `OrderIndex`
  values have gaps after 0.
- **Fix:** keep `HOME_ROWS` in `scripts/configure-jellyfin-plugins.py` numbered
  0, 1, 2…, then restart Jellyfin, because the plugin caches empty pages in memory.

## Subtitles stuck on "Fetching additional data" in a browser
- **Cause:** the file has embedded subtitles only, and Jellyfin has to read the whole
  file to extract them.
- **Fix:** Bazarr is set to ignore embedded subtitles (`use_embedded_subs: false`),
  so external `.srt` files normally arrive. Check Bazarr's Wanted list.

## Bazarr "throttling" messages
- **This is normal backoff:** a flaky site gets 10 minutes off. OpenSubtitles'
  free tier stops at about 20 downloads a day and resumes on its own. It's only a problem
  if every provider stays throttled for hours.

## Bazarr uses a full CPU core for minutes at a time
- **Cause:** the missing-subtitle search runs every 6 hours over every wanted
  episode on every provider. Adaptive searching drops an episode to weekly only
  after 3 weeks without a match, so a freshly added library searches hardest.
- **Normal:** bursts after a search; idle in between (`docker stats bazarr`).
- **Shows with built-in English subtitles** stay wanted forever, because
  `use_embedded_subs` is off. Give such a show (for example one whose every file
  carries two English SRT tracks) no language profile in Bazarr, rather than
  turning embedded subs on globally.
- **Dead providers** make every search wait on timeouts. tvsubtitles (domain gone)
  and subf2m (HTTP 500 on every search) were removed in 2026-09; drop any other
  provider that stays in `ConnectionError`/`HTTPError` for days from
  `scripts/configure-bazarr.py`.

## Byparr healthcheck fails
- **Cause:** it solves Cloudflare challenges for EZTV, and each one takes 60 to 100 s,
  so the probe times out while it's busy.
- **What to do:** usually nothing; it recovers by itself. Restart it only if it stays unhealthy
  for more than 15 minutes.
- Searches through Byparr take about 15 to 20 s while the challenge clears. That is normal.

## Searches find nothing, or an indexer keeps failing
- **See which work:** `scripts/indexers-check` tests every indexer and prints Prowlarr's own
  query and failure counts. Prowlarr already does this continuously: it disables a failing
  indexer with exponential backoff and re-enables it when it recovers (Prowlarr → System → Health).
- **Cloudflare errors:** the indexer needs Byparr. Give it the `byparr` tag in Prowlarr and
  check Byparr is healthy (`docker inspect -f '{{.State.Health.Status}}' byparr`).
- **Nothing found for an old or obscure title:** public trackers are patchy; no setting fixes
  that. A tracker with an account, added to Prowlarr, is the real fix.
- **Every game search in Questarr takes 30 s:** Questarr waits for all indexers, up to 30 s. One
  that answers slowly instead of failing (Knaben, September 2026) holds every search to that limit,
  and Prowlarr's backoff doesn't catch it. Questarr's log names it ("error searching indexer" after
  a timeout). Downtime happens and usually passes within hours, so don't switch an indexer off
  at the first slow answer. If it stays slow for a day, switch it off in Prowlarr (edit the
  indexer, untick **Enable**), then re-run `scripts/configure-questarr.py`, which copies the
  on/off state into Questarr. Turn it back on once Prowlarr's **Test** answers in a few seconds.

## Releases shown as rejected
- **Cause:** usually TRaSH's quality rules: a low-quality or unknown release group, or a file
  below the minimum size for its runtime ("smaller than minimum allowed").
- **What to do:** loosen the size limit in Radarr or Sonarr → Settings → Quality if you want
  smaller encodes, or grab a rejected release on purpose from Interactive Search.

## Dozzle lists containers but can't open their logs
- **Cause:** the linuxserver socket proxy gates log reads with its own `ALLOW_LOGS`
  flag, separate from `CONTAINERS`. Dozzle's log shows "403 Forbidden ...
  administrative rules".
- **Fix:** `ALLOW_LOGS: 1` on `socket-proxy` in compose (a read-only GET; `POST` stays
  0). `stack-health` checks both that logs are readable and that writes are refused.

## Dozzle shows no CPU or memory (avg CPU/memory empty)
- **Cause:** Dozzle lists containers once at start and never retries. When the whole
  stack starts at once, Docker can be too slow to answer, and Dozzle's log shows
  "failed to list containers: context deadline exceeded". Containers created later
  still get stats, so only some show numbers.
- **Fix:** `docker compose restart dozzle`. `stack-up` does this by itself when it finds
  that line in the current Dozzle log.

## A show is in Jellyfin but has no poster or description
- **Cause:** Jellyfin identifies a show by its folder name. Sonarr uses the English title,
  and a foreign show Jellyfin knows only under its own title (a French show Sonarr lists
  under an English TVDB name with "(FR)" added, for one) matches nothing.
- **Fix:** new series folders carry the TVDB id (`{Series Title} [tvdbid-{TvdbId}]`, set by
  `configure-arr.py`), which Jellyfin matches on. For an older folder, identify it in Jellyfin
  by its TMDB id (Seerr has it): `/Items/RemoteSearch/Series`, then
  `/Items/RemoteSearch/Apply/<id>?ReplaceAllImages=true`.

## Slow playback or disk while downloading
- **Cause:** a big batch downloading at full speed (~90 MB/s). Decrypting the VPN tunnel then
  takes most of the CPU (load 15+, mostly `napi/tun` and `ksoftirqd`), rather than the disk.
  Many simultaneous torrents (60+) can also saturate the USB drive. Queueing is off by choice.
- **What happens already:** `downloads-throttle` (every minute) switches on qBittorrent's
  alternative limit, 20 MB/s, while anyone plays in Jellyfin or Plex or the 5-minute load reaches
  twice the core count (8 on a Pi 5), and off once nobody watches and the load is under the core
  count. Check `journalctl -u arr-throttle`.
- **What to do:** explain the cause; don't add other limits without asking.

## A value in .env contains `$`
- **Symptom:** Compose warns "The \"xyz\" variable is not set"; the password
  silently loses everything after the `$` in Compose and bash.
- **Fix:** wrap that value in single quotes in `.env` (`USENET_PASS='a$b'`).
  `scripts/stack_env.py` strips the quotes, so Python reads the same value.

## Lidarr ignores Soulseek
- **Cause 1:** Lidarr's delay profile had the Soulseek protocol "not allowed", so every
  Soulseek result was silently dropped.
- **Fix:** `configure-arr.py` sets the Lidarr delay profile to Soulseek, then Usenet,
  then torrents.
- **Cause 2:** the Soulseek (Tubifarry) indexer had automatic and interactive search off.
  Lidarr's template leaves them off for indexers without RSS, so Lidarr never asked
  Soulseek: its log says "Searching indexers … 5 active indexers" instead of 6, and slskd's
  log shows no searches from Lidarr. `configure-lidarr.py` turns them on, waits 20 s for
  answers and tries names without accents.

## Lidarr finds copies but takes none ("X is not wanted in profile")
- **See why:** Lidarr → the album → Interactive Search, or
  `GET /api/v1/release?albumId=<id>` lists each copy with its rejections.
- **"FLAC is not wanted in profile":** new artists get the root folder's *Standard*
  profile, which is lossy only, so a FLAC-only copy is rejected. Switch that artist to
  *Any* or *Lossless* in Lidarr (ask the owner; it's their space/quality choice).
- **"No results found" for rare music:** Soulseek may have it under another spelling;
  a manual slskd search (`/api/v0/searches`) with and without accents shows what's there.

## "Album match is not close enough: 49.1% vs 80%" in Needle's Downloading now
- **Cause:** Lidarr downloaded a copy that doesn't match the album (another edition, a
  bootleg, missing tracks) and won't import it.
- **Fix:** Needle → Requests → **Find another copy** (removes it from the download client,
  blocklists that release, searches again) or × (removes and blocklists without a new
  search). The same is Lidarr → Activity → Queue → remove with "Blocklist release".

## An album has no cover in Navidrome or Needle
- **Cause:** Lidarr imports without writing tags, so covers come only from `folder.jpg`,
  which Lidarr's Kodi/Emby metadata writer saves (`configure-lidarr.py` turns it on).
- **Fix:** run `configure-lidarr.py`; for albums already there, Lidarr → the artist →
  Refresh & Scan (or `RescanFolders` for the artist's folder). Multi-disc albums get
  `folder.jpg` in one disc folder; Navidrome finds it.

## Needle hides Spotify, or says Spotify refused (429)
- **Cause:** Spotify's development-mode quota is per app and shared by everyone who
  connected; after too many calls it refuses (`429 QUOTA_EXCEEDED`) for up to hours.
- **What Needle does:** stops calling Spotify for as long as it asks (an hour when the
  browser can't read the wait) and hides Spotify meanwhile; it comes back by itself.
  Nothing to fix; fewer people browsing Spotify at once helps.

## SABnzbd "Refused connection from ::ffff:100.x"
- **Cause:** SABnzbd only trusts private LAN ranges by default; Tailscale's 100.64.0.0/10
  isn't one, so phones on the tailnet were refused.
- **Fix:** `configure-sabnzbd.py` writes `local_ranges` (LAN, tailnet, Docker, localhost)
  into `sabnzbd.ini` with the container stopped. SABnzbd silently ignores API changes to
  that setting. `stack-health` verifies the tailnet is listed.

## "Pool overlaps with other one on this address space" when the stack starts
- **Cause:** another Docker network on the machine already uses the `arr` network's subnet.
  Docker gives `172.18.0.0/16`, the default `ARR_SUBNET`, to the first other compose project.
- **Fix:** `scripts/host-install` names the clashing network. Set a free `/16` as `ARR_SUBNET` in
  `.env` (for example `172.28.0.0/16`) and move `PROWLARR_IP` into it (`172.28.0.200`), then
  start the stack and re-run `configure-questarr.py`, which stores Prowlarr's address.

## An app won't open from home Wi-Fi, only Jellyfin, Seerr and the games page do
- **This is by design:** the host firewall (`scripts/host-firewall`) lets the home network
  reach only Jellyfin (8096), Seerr (5055) and the games page (8090); SSH and SFTP (2022)
  are Tailscale only. Use the Tailscale address, at home too.
- Seerr is open because TV apps such as JellySee (home network, no Tailscale) load
  "Upcoming", trending and requests from it. If those sections fail but playback works,
  check the `ctorigdstport 5055` rule in `ARR-FWD` (`sudo scripts/host-firewall status`).
- Macvlan containers have their own home-network addresses and bypass the host's
  firewall entirely; leave them to their own project.

## A viewer (family, friend) can't connect
- **Check, in order:** their device is signed in to Tailscale with an email listed in
  `group:viewers`; the device is **not** tagged (a tagged device stops being theirs);
  the server still carries `tag:media` (`tailscale status --json`, `Self.Tags`); on a TV,
  the Tailscale app is connected (it pauses while the TV sleeps).
- They reach only 8096, 5055, 5000, 8090, 2022 (SFTP) and 4535 (Needle) by design (see `host/tailscale-policy.hujson`).
- Their Jellyfin, Seerr, game downloads (SFTPGo) and Navidrome (Needle) logins come from
  `scripts/viewer-add.py`; the Navidrome username is their name up to any "@". Needle is
  on 4535 for viewers too (the policy's viewer grant must include `tcp:4535`). What they
  may do in Needle (request music, Spotify) is in Needle → Settings → People; they appear
  there after their first sign-in.
  "Account disabled" after wrong passwords: Jellyfin locks non-admins after 3; re-enable in
  Jellyfin → Users. Seerr requests wait for the owner's approval unless the viewer was
  added with `--auto-approve` (or given Auto-Approve in Seerr → Users).

## Games page (SFTPGo): a big download started over
- A **single file** resumes (HTTP ranges); a **zip of several items** is built on the fly
  and can't. For big games over the internet, download files one by one.
- Its admin can't log in from the tailnet by design (allow-list `127.0.0.0/8`,
  `172.16.0.0/12`); `configure-sftpgo.py` and `viewer-add.py` run on the server.

## Lidarr: "Connection refused (gluetun:5030)" from SlskdDownloadManager
- **Cause:** slskd lives in gluetun's network namespace, so while gluetun restarts
  (an update, or `vpn-port-sync`'s automatic VPN restart) Lidarr can't reach it for a few
  seconds. Lidarr keeps its cached items and retries on its own.
- **Harmless if it's one error per VPN restart.** If it repeats, slskd lost gluetun's
  network: `docker compose up -d --force-recreate slskd`.

## SSH refused ("Permission denied (publickey)") from a device of yours
- SSH is Tailscale only, and each key has a `from=` list: the owner's keys accept the
  tailnet ranges, and other keys only the devices they belong to. Connect over Tailscale, or add that
  device's source to the key's `from=` (keep it pinned; `stack-health` checks).

## Radarr downloaded a fake of a movie still in cinemas
- **Cause:** a search started through Radarr's API (`MissingMoviesSearch`, `MoviesSearch`)
  counts as a user-invoked search, and those skip the minimum-availability check. Radarr
  then searches movies that aren't released for home viewing yet, and public trackers
  offer fakes labelled "WEB-DL". This happened once with a weekly catch-up search, which
  was removed at the user's request.
- **Fix:** Activity → History → mark the grab as failed (blocklists it), delete the file
  and its torrent. Automatic searches respect availability, so nothing is re-grabbed.

## Uptime Kuma says a service is down, but it's running
Kuma keeps checking a container's old address after the container was recreated
(`connect EHOSTUNREACH 172.18.x.x` in `docker logs uptime-kuma`). That was Kuma's
DNS cache (nscd), which `scripts/configure-uptime-kuma.py` now turns off. If it
comes back, re-run that script; `docker exec uptime-kuma nscd -i hosts` clears the
cache at once.

## The media drive won't mount
- **Check:** the drive is powered on, then `systemctl status <unit>.mount`, where the unit is
  `systemd-escape --path --suffix=mount "$STORAGE_MOUNT"` (`mnt-storage.mount` for `/mnt/storage`).
- **After reformatting:** the udev rule matches the filesystem UUID. Put the new UUID
  (`lsblk -f`) in `STORAGE_UUID` in `.env` and in `/etc/fstab`, then re-run `scripts/host-install`.
- The stack refuses to start without the mount (`arr-stack.service` checks `mountpoint`), so
  media never lands on the system disk.

## Glance's video rows are empty or stale
- **Cause:** Glance reads `/assets/youtube/<tab>.json`, which `arr-youtube.timer` rewrites hourly.
  Check `systemctl status arr-youtube.service` and run `scripts/youtube-sync.py`: `!` lines name
  channels that failed and kept their last videos.
- Not signed in (`YOUTUBE_REFRESH_TOKEN` empty), the videos come from YouTube's RSS feed, which
  answers 404 for hours at a time; sign in with `youtube-sync.py --login` to use the Data API.
- `quotaExceeded` from the API resets at midnight Pacific time; the rows keep their last videos.

## Things never to do
- `docker compose down`, or recreating the `arr` network, while the user is
  watching or downloading. Both restart everything.
- Moving the VPN exit to the US (`VPN_COUNTRIES`), or taking qBittorrent or slskd out
  of gluetun's network. Torrents must always go through the VPN; only SABnzbd
  (Usenet) runs outside it.
- Printing or committing secrets from `.env`.
- Triggering Radarr searches through the API for movies that aren't `isAvailable`: it
  bypasses "wait until released" and grabs fakes.
- Opening more ports to the home network, or leaving `scripts/host-firewall off` in place.
  Guests share that network; new access goes through Tailscale and its access rules.

# Dashboards

This page is a tour of the web dashboards that show what the server is doing: which one answers
which question, its port, and the module (`COMPOSE_PROFILES`) that runs it. It also walks through
the pages of Glance, the start page. How the metrics and alerts behind them are collected is in
[Monitoring](../flows/monitoring.md).

Every dashboard is reachable over Tailscale only, at `http://<tailscale-ip>:<port>`; the home
network can't open them.

## Which dashboard answers what

| Dashboard | Port | Answers | Login | Module |
|---|---|---|---|---|
| **Homepage** | 3000 | Is everything up, and what is downloading right now? | None | `dashboards` |
| **Glance** | 3005 | What's new today, what's airing next, how is the server? | None | `dashboards` |
| **ChangeDetection.io** | 3007 | Did that web page change? | None | `dashboards` |
| **Grafana** | 3001 | How has it behaved over time? | `GRAFANA_USER` / `GRAFANA_PASSWORD` | `monitoring` |
| **Uptime Kuma** | 3003 | Is anything down, and since when? Status page at `/status/stack` | `UPTIME_KUMA_USER` / `UPTIME_KUMA_PASSWORD` | `monitoring` |
| **Dozzle** | 8888 | What is this container saying? | `DOZZLE_USER` / `DOZZLE_PASSWORD` | `monitoring` |
| **Scrutiny** | 3006 | Is the media drive healthy? | None | `monitoring` |
| **Prometheus** | 9090 | Raw metrics; `/targets` shows every scrape | None | `monitoring` |
| **Jellystat** | 3002 | What have we been watching? | Its own, created on first visit | `stats` |
| **JellyDash** | 3004 | What's playing now, and the watch history | `JELLYDASH_USER` / `JELLYDASH_PASSWORD` | `stats` |

Start with Homepage for the stack and Glance for the day. Homepage, Glance and Dozzle read Docker
only through a read-only socket proxy, never the Docker socket itself (see
[Security](../security.md)).

## Homepage

`http://<tailscale-ip>:3000` is the operations dashboard: one page linking to every app, in three
groups (Watch, Manage, Infrastructure), with live data from each rather than just green dots.

| Tile | Shows |
|---|---|
| Seerr | Pending requests |
| Radarr, Sonarr | Queue, wanted, missing |
| Prowlarr | Indexer health |
| Bazarr | Subtitles wanted |
| qBittorrent | Live download and upload speed, active torrents |
| Lidarr, SABnzbd | Live status from each app |
| Uptime Kuma | The status page's summary |
| Top strip | CPU, RAM, temperature, uptime, and free space on the system disk and the media drive |

Each tile's dot shows whether its container is running.

- **Why no Jellyfin widget:** Jellyfin 12 accepts only the `Authorization: MediaBrowser Token=...`
  header and rejects the older header Homepage's Jellyfin widget sends, so the widget always gets
  401. The tile still links to Jellyfin and shows its container status; Jellystat covers the
  statistics.
- **Why Homepage and not Dashy:** Dashy has no live widgets for these apps, only up and down
  dots, so it can't show download status.
- **Every tile shows "API Error Information":** the status dots go through the socket proxy; look
  at `docker logs homepage | grep -i sock`.
- **Homepage refuses an address you typed:** it answers only the host names and ports listed in
  `HOMEPAGE_ALLOWED_HOSTS` in `.env`. Add the one you use.

Its configuration is YAML in `homepage/` in the repository; edit it and Homepage reloads itself.

## Glance

`http://<tailscale-ip>:3005` is the start page, meant as your browser's home page. It has five
pages, in this order:

| Page | What is on it |
|---|---|
| **Lab** (the first, so `/` opens it) | Server CPU, RAM, temperature and both disks; the media drive's free space, growth per day, projected full date and SMART status from Scrutiny; library counts and sizes; response times of the apps people use; every container's state; Uptime Kuma's up and down counts with 24-hour uptime; pending image updates and the last backup; indexers backing off, subtitles wanted and throttled subtitle providers; new releases of the stack's apps |
| **Home** | Calendar, blogs, Twitch channels and ChangeDetection's watched pages; a search box with `!yt`, `!gh` and `!r` shortcuts, Hacker News and Lobsters, your tech YouTube subscriptions, Reddit and Ars Technica; the weather, your stocks, Formula 1 (next race, standings and last result, from [f1api.dev](https://f1api.dev)) and bookmarks |
| **Media** | Poster rows: movies and episodes recently added to Jellyfin, the next two weeks of TV, the next 90 days of movies and 60 days of albums from your Lidarr artists, recent Seerr requests with their status, and the month's most watched. Beside them: the VPN (exit city, address and forwarded port; red when it is down or exits in the US), live torrent and Usenet speeds, Jellyfin's now playing, request counts, 30-day watch statistics, the download queue and every downloading torrent |
| **Gaming** | Top Twitch games, gaming news, your gaming YouTube subscriptions, free Epic games, Steam deals and a Pokémon of the hour |
| **Markets** | Indices and your stocks, your markets YouTube subscriptions, and market headlines |

The three dots at the top right pick a colour theme (dark, light and 19 presets), remembered per
browser.

How it works, and what to know when you change it:

- **Configuration** is `glance/glance.yml` in the repository. Edit it and Glance reloads itself.
  API keys come from `.env` as `${VAR}`; a missing variable stops the reload, and
  `docker logs glance` says why. `configure-glance.py` puts Jellystat's and ChangeDetection's keys
  there.
- **Weather** uses `WEATHER_LOCATION` in `.env`, in single quotes when it has spaces:
  `'Amsterdam, Netherlands'`.
- **Posters** come straight from Jellyfin (its image addresses need no key) and from the public
  TVDB and TMDB links Sonarr, Radarr and Seerr return, so no API key reaches the browser. Their
  styling is `glance/assets/media.css`.
- **Reddit** refuses its JSON API from the server's address and rate-limits RSS to about one
  request at a time, so every subreddit shares one combined feed (`r/a+b+c/.rss`), refreshed
  every two hours. Add a subreddit by extending the `+` list, never with a second Reddit feed.
- **Samples to edit:** the subreddits, the stock list (`&stocks` in `glance/glance.yml`) and the
  pinned YouTube channels ship as generic examples; replace them with your own.
- **Pending updates and the last backup** reach Glance through Prometheus: `check-updates`,
  `update` and `backup-config` write them as metrics, which node-exporter exports, so Grafana has
  their history too.
- **Container states** come through the read-only socket proxy. Glance has no login, so it stays
  tailnet-only like everything here.

To open Glance's Lab page in every new Chrome tab, with the cursor in its search box, see the
[Chrome new-tab extension](../operations/host.md#chrome-new-tab-extension).

### YouTube rows follow your subscriptions

The Tech, Gaming and Markets video rows are lists of channels that `sync-youtube.py` writes to
`$CONFIG_ROOT/glance/youtube-*.yml` every Sunday (`arr-youtube.timer`); `glance.yml` includes
them. The sync reads your subscriptions, most relevant first, keeps the **pinned** channels in
`glance/youtube-channels.json` that you still follow, and fills the remaining slots (the limits are
in the same file) with channels whose YouTube topic tags say gaming, technology or business.
Unsubscribe and a channel disappears; subscribe and it shows up if it fits a row. Put a channel
under `skip` to keep it out, or pin it to force its row. Until you sign in, the pinned lists are
used as they are.

One-time setup:

1. In the [Google Cloud console](https://console.cloud.google.com), create a project, then
   **APIs & Services → Library → YouTube Data API v3 → Enable**.
2. In **Google Auth Platform**, set the audience to **External**, add yourself as a test user,
   then **Publish app** (while in testing, the sign-in expires after 7 days). It stays unverified,
   which is fine for your own account.
3. **Clients → Create client → TVs and Limited Input devices.** Put its ID and secret in `.env` as
   `YOUTUBE_CLIENT_ID` / `YOUTUBE_CLIENT_SECRET`.
4. Run `scripts/sync-youtube.py --login`, open the address it prints on any device and enter the
   code. Google warns that the app is unverified: **Advanced → continue**. Access is read-only,
   and the script stores the refresh token in `.env` itself.
5. Run `scripts/sync-youtube.py` to sync at once; the timer does it weekly after that.

Once you are signed in, `health-check` fails if the lists haven't synced in 14 days.

## Grafana

`http://<tailscale-ip>:3001`. The dashboards are under **Dashboards → Media Stack**:

| Dashboard | Shows |
|---|---|
| **Media Server: Overview** (`/d/media-server-overview`) | Host CPU, temperature, RAM, storage, disk I/O, network and metrics-collection history; 24 hours by default |
| **Media Server: Watching** (`/d/media-watching-overview`) | Jellystat's recorded sessions, watch time, active viewers, totals per user and title, playback methods and recent history; 7 days by default |
| **Node Exporter Full** | The server in depth: CPU, RAM, temperature, disk I/O, network |
| **Sonarr v3**, **Radarr v3** | Library, queue, missing, disk |
| **Scraping** | Everything Scraparr collects from the arr apps |

The two overview dashboards link to each other and to Node Exporter Full; use the time picker for
other ranges. They are provisioned from `grafana/dashboards/` and picked up within about a minute.
Edits made in the UI survive, but for anything permanent, export the JSON into that folder. The
Watching dashboard reads Jellystat's history through a read-only database user; how it is set up
is in [Monitoring](../flows/monitoring.md).

## Uptime Kuma

The status page, `http://<tailscale-ip>:3003/status/stack`, shows every service's recent checks;
it is also the Uptime Kuma tile on Homepage. Kuma checks every service once a minute and pushes
**DOWN** and **UP** alerts to your phone through ntfy. It is the always-on watcher that tells you
*when* something broke; `health-check` is the deep check you run on demand. What it watches and
how the alerts flow: [Monitoring](../flows/monitoring.md).

## Dozzle

`http://<tailscale-ip>:8888` shows every container's log in the browser, streaming live, with
search. It reads Docker only through the read-only socket proxy, so it can't stop, restart or
change anything: its action buttons and shell are pinned off in `docker-compose.yml`, and the
proxy refuses writes anyway. `configure-dozzle.py` applies the login from `.env`. In a terminal,
`dock` (lazydocker) shows the same logs ([Terminal](../operations/terminal.md)).

## Scrutiny

`http://<tailscale-ip>:3006` keeps the media drive's SMART attributes, temperature and health over
time, collected every six hours. `STORAGE_DEVICE` in `.env` names the drive (default `/dev/sda`);
behind a USB enclosure it reads through the bridge with the `sat` device type
(`scrutiny/collector.yaml`). Alerts still come from `health-check`, which checks SMART every 6
hours; Scrutiny is for the history. Its metrics database is left out of backups.

## ChangeDetection.io

`http://<tailscale-ip>:3007`: paste an address (a store page, a product listing, release notes)
and it checks it on a schedule and shows what changed. Recent changes also appear on Glance's
Home page. It fetches pages with plain HTTP and has no browser, so pages that need JavaScript to
render won't work.

## Jellystat

`http://<tailscale-ip>:3002` records Jellyfin watch statistics. On the first visit it asks you to
create a Jellystat login (its own, separate from Jellyfin), then to connect Jellyfin:

| Field | Value |
|---|---|
| URL | `http://jellyfin:8096` |
| API key | `JELLYSTAT_JELLYFIN_API_KEY` from `.env` |

`jellyfin` is Jellyfin's name inside Docker. It won't open in your browser and doesn't need to;
Jellystat uses it from its own container, and it never changes. The key is a dedicated one named
Jellystat in Jellyfin (Dashboard → API Keys), so it can be revoked on its own.

Afterwards, in Jellystat's **Settings**, set **External URL** to an address your devices reach,
such as `http://<tailscale-ip>:8096`; it is used for links you click. Keep Jellystat in its default
**Jellyfin** mode: its Emby mode sends a login header Jellyfin 12 rejects.

Jellystat records only what is watched after it is set up. It keeps its data in its own
PostgreSQL container, `jellystat-db`, which publishes no port.

## JellyDash

`http://<tailscale-ip>:3004` is a companion to Jellyfin: live "now playing" cards, a searchable
watch history with CSV export, statistics and monthly recaps, and the Seerr requests. On an
iPhone, **Add to Home Screen** installs it like an app. It overlaps with Jellystat; run both for a
while and keep the one you prefer.

- Its **Downloads** page shows qBittorrent and SABnzbd live (speed, progress, time left, recent
  completions and failures). It only reads the queues, never changes them.
- It pushes "*someone* started watching..." and new Seerr requests to the stack's ntfy topic,
  for every user. Plays that started more than 10 minutes before it noticed are skipped.
- `configure-jellydash.py` creates its own Jellyfin API key (stored in `.env`), sets the admin
  login and adds both download clients. JellyDash normally insists on 8-character passwords; the
  script writes the `.env` password as a hash, so a shorter one works.
- The project is young and releases often. If an update misbehaves, `update --rollback jellydash`
  ([Updates](../flows/updates.md)).

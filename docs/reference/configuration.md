# Configuration reference

Every setting in `.env` and every compose profile (module): what it does, whether you must set it, its default, and what reads it. It is for anyone filling in `.env` or switching modules on and off; [Getting started](../getting-started.md) walks through a first setup.

## How .env is read

`.env` lives in the repository root, holds every secret and every value specific to your server, and is gitignored. Start from [`.env.example`](https://github.com/bugrauluyurt/homelab-media-stack/blob/main/.env.example), which lists every key with a one-line hint, and keep it private (`chmod 600 .env`).

- **Docker Compose** substitutes `${KEY}` in `docker-compose.yml` from it, and also reads `COMPOSE_PROFILES` and `COMPOSE_FILE` from it, so plain `docker compose` commands in the repository follow them.
- **Bash scripts** source it through [`stack-env.sh`](scripts.md#stack-envsh), which exports every key. **Python scripts** parse it through [`stack_env.py`](scripts.md#stack_envpy).
- **Quoting:** wrap a value that contains `$` in single quotes (Compose and bash would expand it), and a value with spaces too, for example `WEATHER_LOCATION='<city>, <country>'`. The Python scripts strip the quotes, so every tool reads the same value.
- **Keys the scripts write:** `SABNZBD_API_KEY` ([`configure-sabnzbd.py`](scripts.md#configure-sabnzbdpy)), `JELLYSTAT_API_KEY` and `CHANGEDETECTION_API_KEY` ([`configure-glance.py`](scripts.md#configure-glancepy)), `JELLYDASH_JELLYFIN_API_KEY` ([`configure-jellydash.py`](scripts.md#configure-jellydashpy)) and `YOUTUBE_REFRESH_TOKEN` ([`youtube-sync.py --login`](scripts.md#youtube-syncpy)). Leave them empty and run the script.
- Changing a value that a container reads takes effect when the container is recreated (`docker compose up -d <service>`); a value a configure script applies takes effect when you re-run that script.

In the tables below, **Required** is *yes* when the core stack or a core script fails without the key, the module's name when only that [module](#compose-profiles) needs it, *no* for an optional feature, and *filled by a script* for the keys above. **Default** is what is used when the key is empty or missing; *none* means there is no fallback (the example file's value, where it has one, is given in brackets). **Read by** names containers (compose services) and scripts. Each key's anchor is its name in lower case, for example `#storage_mount`.

## Keys

### This machine

| Key | Required | Default | What it does | Read by |
|---|---|---|---|---|
| <a id="stack_user"></a>`STACK_USER` | yes | none | Linux user that owns the repository and runs the stack's services and timers. | [`host-install`](scripts.md#host-install) (systemd templates), [`stack-backup`](scripts.md#stack-backup), [`stack-health`](scripts.md#stack-health) |
| <a id="host_name"></a>`HOST_NAME` | yes | none | The server's host name, also its Tailscale MagicDNS name (`hostname`). Used for links on the dashboards and as an allowed host. | homepage, glance, changedetection, grafana; [`vpn-port-sync`](scripts.md#vpn-port-sync) (qBittorrent's allowed hosts), `stack-backup` (restic host), `stack-health` (`<host>.local` resolves to a LAN address) |
| <a id="tailscale_ip"></a>`TAILSCALE_IP` | yes | none | The server's Tailscale IPv4 address (`tailscale ip -4`). | [`configure-jellyfin-plugins.py`](scripts.md#configure-jellyfin-pluginspy) (external links), `stack-health` (SFTPGo's admin refused on it) |
| <a id="storage_mount"></a>`STORAGE_MOUNT` | no | `/mnt/storage` | Where the media disk is mounted. See [below](#storage_mount-and-storage_device). | `host-install`, [`stack-up`](scripts.md#stack-up), [`drive-off`](scripts.md#drive-off), `stack-health`, [`stack-update`](scripts.md#stack-update), `stack-backup`, [`configure-uptime-kuma.py`](scripts.md#configure-uptime-kumapy), glance, the skills |
| <a id="storage_uuid"></a>`STORAGE_UUID` | no | empty | Filesystem UUID (`lsblk -f`) of a media drive you switch on by hand, so it mounts on power-on. Leave empty when the disk is always mounted through fstab. | `host-install` ([`99-arr-storage.rules`](systemd.md#99-arr-storagerules)) |
| <a id="storage_device"></a>`STORAGE_DEVICE` | no | `/dev/sda` | The media drive's whole-disk device, for Scrutiny's SMART history. See [below](#storage_mount-and-storage_device). | scrutiny |
| <a id="questarr_allowed_origins"></a>`QUESTARR_ALLOWED_ORIGINS` | games | none | Every URL Questarr is opened on (host name, `<host>.local`, LAN IP, Tailscale IP, `localhost`), each with port 5000, comma-separated. | questarr |

### Identity and permissions

| Key | Required | Default | What it does | Read by |
|---|---|---|---|---|
| <a id="puid"></a>`PUID` | yes | none (`1000`) | User ID the containers run as; must own `DATA_ROOT` (`id`). | the linuxserver images and every service with `user:`; [`configure-navidrome.py`](scripts.md#configure-navidromepy) |
| <a id="pgid"></a>`PGID` | yes | none (`1000`) | Group ID the containers run as. | same as `PUID` |
| <a id="umask"></a>`UMASK` | yes | none (`002`) | `002` makes new files group-writable, so every container can import the others' files. | the linuxserver images, slskd |
| <a id="tz"></a>`TZ` | yes | none (`Etc/UTC`) | Your time zone (`timedatectl list-timezones`). | every container that takes `TZ`; glance |
| <a id="weather_location"></a>`WEATHER_LOCATION` | dashboards | empty | Location of Glance's weather widget; single-quote it when it has spaces. | glance |

### Paths

| Key | Required | Default | What it does | Read by |
|---|---|---|---|---|
| <a id="data_root"></a>`DATA_ROOT` | yes | none | One folder on the media mount holding both downloads and media, so hardlinks work. Don't split it; `stack-health` fails when it is not on `STORAGE_MOUNT`. | every container that mounts `/data` or the media; `configure-navidrome.py`, [`configure-sftpgo.py`](scripts.md#configure-sftpgopy), `stack-health` |
| <a id="config_root"></a>`CONFIG_ROOT` | yes | none | App databases, settings and API keys, deliberately outside the repository. The scripts keep their state in the `state` folder beside it. | every container's config volume; every script through `stack-env.sh` and `stack_env.py` |

### Network and modules

| Key | Required | Default | What it does | Read by |
|---|---|---|---|---|
| <a id="lan_cidr"></a>`LAN_CIDR` | yes | none | Your home network's range. | gluetun (reachable outside the tunnel), [`host-firewall`](scripts.md#host-firewall), `stack-health`, [`configure-sabnzbd.py`](scripts.md#configure-sabnzbdpy), [`configure-plex.py`](scripts.md#configure-plexpy) |
| <a id="arr_subnet"></a>`ARR_SUBNET` | no | `172.18.0.0/16` | The subnet of the `arr` Docker network. Docker gives `172.18.0.0/16` to the first other compose project on a machine, so `host-install` checks for an overlap and names a free range; move `PROWLARR_IP` into the new subnet with it. | docker-compose.yml, [`host-install`](scripts.md#host-install) |
| <a id="prowlarr_ip"></a>`PROWLARR_IP` | yes | none (`172.18.0.200`) | Prowlarr's fixed address on the `arr` Docker network (inside `ARR_SUBNET`). Questarr trusts Prowlarr's download links only when their host matches the address it syncs from. | prowlarr, [`configure-questarr.py`](scripts.md#configure-questarrpy) |
| <a id="qbit_port"></a>`QBIT_PORT` | yes | none (`8080`) | qBittorrent's web UI port, published by gluetun; every app and script reaches qBittorrent on it. | gluetun, qbittorrent, homepage, glance; `stack-env.sh`, `vpn-port-sync`, `stack-health`, [`downloads-throttle`](scripts.md#downloads-throttle), [`configure-arr.py`](scripts.md#configure-arrpy) |
| <a id="compose_profiles"></a>`COMPOSE_PROFILES` | no | `*` for the scripts | Which optional modules run: `*` for all, or a list such as `music,monitoring`. See [compose profiles](#compose-profiles). | Docker Compose; `stack-env.sh`, `stack_env.py` and every script that skips a module |
| <a id="media_cpus"></a>`MEDIA_CPUS` | no | `3` | CPU cores Jellyfin, Plex and Byparr may each use. See [below](#cpu-limit). | jellyfin, plex, byparr |
| <a id="compose_file"></a>`COMPOSE_FILE` | no | `docker-compose.yml` | Commented out in the example. Add `compose.gpu.yml` for hardware transcoding or `compose.vpn-failover.yml` for a verified Proton server pool, separated by colons. Both overrides can be combined. See [below](#composegpuyml-and-compose_file) and [VPN failover](../flows/vpn-and-ports.md#verified-proton-server-pool). | Docker Compose |
| <a id="hwaccel"></a>`HWACCEL` | no | empty | Hardware transcoding type: `vaapi` (Intel or AMD) or `qsv` (Intel). Commented out in the example. | `configure-jellyfin-plugins.py` |

### Proton VPN

| Key | Required | Default | What it does | Read by |
|---|---|---|---|---|
| <a id="wireguard_private_key"></a>`WIREGUARD_PRIVATE_KEY` | yes | none | The `PrivateKey` of a dedicated Proton WireGuard configuration (a P2P server, NAT-PMP on, Moderate NAT off). Its endpoint configuration is installed separately; see [VPN and ports](../flows/vpn-and-ports.md). The pre-commit hook blocks committing it. | gluetun |
| <a id="vpn_countries"></a>`VPN_COUNTRIES` | yes | none | Comma-separated countries the VPN may exit in, spelled as gluetun logs them. `stack-health` fails when the exit country isn't listed or is the United States. Custom mode uses the endpoint in your WireGuard configuration. The failover preset also passes this as gluetun's `SERVER_COUNTRIES` filter and refuses an empty value. | gluetun in failover mode, `stack-health`, the vpn-check skill |
| <a id="vpn_server_names"></a>`VPN_SERVER_NAMES` | with failover preset | empty | Comma-separated server names printed by `vpn-import-servers`. Limits failover to those imported servers; the preset refuses an empty value. Ignored in custom mode. | gluetun in failover mode |

### Plex

| Key | Required | Default | What it does | Read by |
|---|---|---|---|---|
| <a id="plex_claim"></a>`PLEX_CLAIM` | plex, first run only | empty | A claim token from `plex.tv/claim` (it expires in about 4 minutes). Can be blank afterwards. | plex |

### Recyclarr

| Key | Required | Default | What it does | Read by |
|---|---|---|---|---|
| <a id="radarr_api_key"></a>`RADARR_API_KEY` | yes | none | Radarr's API key (Radarr, Settings, General). Most scripts fall back to Radarr's `config.xml` when it is empty; the containers and `configure-jellyfin-plugins.py` can't. | recyclarr, homepage, glance, scraparr (through [`configure-scraparr`](scripts.md#configure-scraparr)); `stack-health` and every script that talks to Radarr |
| <a id="sonarr_api_key"></a>`SONARR_API_KEY` | yes | none | Sonarr's API key, the same way. | recyclarr, homepage, glance, scraparr; `stack-health` and every script that talks to Sonarr |

### Jellyfin admin

| Key | Required | Default | What it does | Read by |
|---|---|---|---|---|
| <a id="jellyfin_user"></a>`JELLYFIN_USER` | no | `admin` | Jellyfin admin created by the startup wizard; Seerr signs in to Jellyfin with it. | [`configure-jellyfin.py`](scripts.md#configure-jellyfinpy), [`configure-seerr.py`](scripts.md#configure-seerrpy) |
| <a id="jellyfin_password"></a>`JELLYFIN_PASSWORD` | yes | none | Its password. | same |
| <a id="jellyfin_server_name"></a>`JELLYFIN_SERVER_NAME` | no | `Home Media` | The server name apps show. | `configure-jellyfin-plugins.py` |

### Dashboard and monitoring

| Key | Required | Default | What it does | Read by |
|---|---|---|---|---|
| <a id="homepage_allowed_hosts"></a>`HOMEPAGE_ALLOWED_HOSTS` | yes | none | Every `host:port` Homepage is opened on; Homepage refuses other `Host` headers. The scripts reuse the host names for SABnzbd's allowed host names and Jellyfin Enhanced's Seerr links. | homepage, `configure-sabnzbd.py`, `configure-jellyfin-plugins.py` |
| <a id="prowlarr_api_key"></a>`PROWLARR_API_KEY` | yes | none | Prowlarr's API key (Settings, General). The scripts fall back to Prowlarr's `config.xml`. | homepage, glance, scraparr; `stack-health` and every script that talks to Prowlarr |
| <a id="bazarr_api_key"></a>`BAZARR_API_KEY` | dashboards, monitoring | none | Bazarr's API key. [`configure-bazarr.py`](scripts.md#configure-bazarrpy) reads Bazarr's own config file instead. | homepage, glance, scraparr |
| <a id="seerr_api_key"></a>`SEERR_API_KEY` | yes | none | Seerr's API key. | homepage, glance, jellydash; [`viewer-add.py`](scripts.md#viewer-addpy), [`activity-watch`](scripts.md#activity-watch), `configure-jellyfin-plugins.py` |
| <a id="jellyfin_api_key"></a>`JELLYFIN_API_KEY` | yes | none | An API key you create in Jellyfin (Dashboard, API Keys) after its startup wizard. | homepage, glance; `configure-arr.py`, `configure-jellyfin-plugins.py`, `configure-jellydash.py`, `viewer-add.py`, `activity-watch`, `downloads-throttle`, `stack-health` |
| <a id="grafana_user"></a>`GRAFANA_USER` | monitoring | none (`admin`) | Grafana's admin. | grafana, [`configure-grafana-watch.py`](scripts.md#configure-grafana-watchpy) |
| <a id="grafana_password"></a>`GRAFANA_PASSWORD` | monitoring | none | Its password. | same |
| <a id="jellystat_db_user"></a>`JELLYSTAT_DB_USER` | stats | none (`jellystat`) | Postgres user of Jellystat's database. | jellystat-db, jellystat, `stack-backup` (`pg_dump`) |
| <a id="jellystat_db_password"></a>`JELLYSTAT_DB_PASSWORD` | stats | none | Its password. | jellystat-db, jellystat |
| <a id="jellystat_jwt_secret"></a>`JELLYSTAT_JWT_SECRET` | stats | none | Jellystat's JWT secret; any random string. | jellystat |
| <a id="jellystat_jellyfin_api_key"></a>`JELLYSTAT_JELLYFIN_API_KEY` | no | empty | A Jellyfin API key dedicated to Jellystat, which you paste into Jellystat's own setup page. Nothing in the stack reads it; `.env` just keeps it. | nothing |

### Glance

| Key | Required | Default | What it does | Read by |
|---|---|---|---|---|
| <a id="jellystat_api_key"></a>`JELLYSTAT_API_KEY` | filled by a script | empty | A Jellystat key named `glance`, created by [`configure-glance.py`](scripts.md#configure-glancepy). | glance |
| <a id="changedetection_api_key"></a>`CHANGEDETECTION_API_KEY` | filled by a script | empty | The key ChangeDetection.io generates on first start, copied by `configure-glance.py`. | glance |

### YouTube (Glance)

| Key | Required | Default | What it does | Read by |
|---|---|---|---|---|
| <a id="youtube_client_id"></a>`YOUTUBE_CLIENT_ID` | no | empty | A Google OAuth client of type "TVs and Limited Input devices" with the YouTube Data API enabled, for Glance's video rows. | [`youtube-sync.py`](scripts.md#youtube-syncpy) |
| <a id="youtube_client_secret"></a>`YOUTUBE_CLIENT_SECRET` | no | empty | Its secret. | `youtube-sync.py` |
| <a id="youtube_refresh_token"></a>`YOUTUBE_REFRESH_TOKEN` | filled by a script | empty | Stored by `youtube-sync.py --login`. Without it the pinned channel lists stay and videos come from YouTube's unreliable RSS feed. | `youtube-sync.py`, `stack-health` |

### Needle and Spotify

| Key | Required | Default | What it does | Read by |
|---|---|---|---|---|
| <a id="spotify_client_id"></a>`SPOTIFY_CLIENT_ID` | no | empty | A Spotify app (developer.spotify.com, needs Premium) for Spotify in Needle. Its redirect URI is `<NEEDLE_PUBLIC_URL>/api/spotify/callback`. | needle |
| <a id="spotify_client_secret"></a>`SPOTIFY_CLIENT_SECRET` | no | empty | Its secret. | needle |
| <a id="needle_public_url"></a>`NEEDLE_PUBLIC_URL` | music | empty | Needle's Tailscale Serve address, `https://<host>.<tailnet>.ts.net:4535`. | needle, homepage, glance |
| <a id="needle_image"></a>`NEEDLE_IMAGE` | no | `ghcr.io/bugrauluyurt/needle:1` | Needle's image. See [below](#needle-image). | needle |

### Backups

| Key | Required | Default | What it does | Read by |
|---|---|---|---|---|
| <a id="restic_password"></a>`RESTIC_PASSWORD` | yes | none | Encrypts the restic backups. `stack-backup` also keeps a copy beside the repository on the media drive. | `stack-backup`; `stack-update` and `stack-health` use the copy on the drive |
| <a id="restic_offsite_repo"></a>`RESTIC_OFFSITE_REPO` | no | empty | An offsite restic repository (an `s3:` or `b2:` URL, for example) that receives a copy of every daily backup. Its credentials go into `.env` too, as the backend's own variables (`AWS_*`, `B2_*`, `AZURE_*`, `GOOGLE_*` or `RCLONE_*`), which `stack-backup` passes to restic. | `stack-backup` |

### Cleanuparr

| Key | Required | Default | What it does | Read by |
|---|---|---|---|---|
| <a id="cleanuparr_password"></a>`CLEANUPARR_PASSWORD` | yes | none | Cleanuparr's web login (user `admin`). | [`configure-cleanuparr.py`](scripts.md#configure-cleanuparrpy), [`cleanuparr-state`](scripts.md#cleanuparr-state) (so `stack-health`) |

### Questarr

| Key | Required | Default | What it does | Read by |
|---|---|---|---|---|
| <a id="questarr_password"></a>`QUESTARR_PASSWORD` | games | none | Questarr's web login (user `admin`); any password, it is written as a hash. | `configure-questarr.py` |
| <a id="igdb_client_id"></a>`IGDB_CLIENT_ID` | no | empty | Game search and covers in Questarr, from your own Twitch developer app (dev.twitch.tv/console). | `configure-questarr.py` |
| <a id="igdb_client_secret"></a>`IGDB_CLIENT_SECRET` | no | empty | Its secret. | `configure-questarr.py` |

### Music

| Key | Required | Default | What it does | Read by |
|---|---|---|---|---|
| <a id="soulseek_user"></a>`SOULSEEK_USER` | music | none | Soulseek account name. slskd registers it on first login, so pick any unique name. | slskd |
| <a id="soulseek_pass"></a>`SOULSEEK_PASS` | music | none | Its password; a random string. | slskd |
| <a id="slskd_password"></a>`SLSKD_PASSWORD` | music | none | slskd's web login (user `admin`). | slskd |
| <a id="slskd_api_key"></a>`SLSKD_API_KEY` | music | none | The API key Lidarr and Needle use for slskd; a random string. | slskd, needle; [`configure-lidarr.py`](scripts.md#configure-lidarrpy), `stack-health` |
| <a id="navidrome_user"></a>`NAVIDROME_USER` | music | none (`admin`) | Navidrome's admin, created by `configure-lidarr.py`. | `configure-lidarr.py`, `configure-navidrome.py`, `viewer-add.py` |
| <a id="navidrome_pass"></a>`NAVIDROME_PASS` | music | none | Its password. | same |
| <a id="lidarr_api_key"></a>`LIDARR_API_KEY` | music | none | Lidarr's API key (Settings, General). The scripts fall back to Lidarr's `config.xml`. | homepage, glance, needle; `stack-health` and every script that talks to Lidarr |

### Notifications

| Key | Required | Default | What it does | Read by |
|---|---|---|---|---|
| <a id="ntfy_server"></a>`NTFY_SERVER` | no | `https://ntfy.sh` | The ntfy server for push notifications. | jellydash; every script's `notify`, `configure-arr.py`, `configure-seerr.py`, `configure-questarr.py`, `configure-uptime-kuma.py` |
| <a id="ntfy_topic"></a>`NTFY_TOPIC` | no | empty | The ntfy topic. Anyone who knows the name can read it, so make it long and random. Empty means no pushes, and `configure-arr.py`, `configure-seerr.py`, `configure-questarr.py` and `configure-uptime-kuma.py` skip their ntfy steps. | same |

### Uptime Kuma

| Key | Required | Default | What it does | Read by |
|---|---|---|---|---|
| <a id="uptime_kuma_user"></a>`UPTIME_KUMA_USER` | monitoring | none (`admin`) | Uptime Kuma's admin. | `configure-uptime-kuma.py` |
| <a id="uptime_kuma_password"></a>`UPTIME_KUMA_PASSWORD` | monitoring | none | Its password; any password works, it is written as a hash. | `configure-uptime-kuma.py` |

### Dozzle and JellyDash

| Key | Required | Default | What it does | Read by |
|---|---|---|---|---|
| <a id="dozzle_user"></a>`DOZZLE_USER` | monitoring | none (`admin`) | Dozzle's login. | [`configure-dozzle.py`](scripts.md#configure-dozzlepy) |
| <a id="dozzle_password"></a>`DOZZLE_PASSWORD` | monitoring | none | Its password. | `configure-dozzle.py` |
| <a id="jellydash_user"></a>`JELLYDASH_USER` | stats | none (`admin`) | JellyDash's admin. | jellydash, `configure-jellydash.py` |
| <a id="jellydash_password"></a>`JELLYDASH_PASSWORD` | stats | none | Its password; JellyDash's 8-character minimum doesn't apply, it is written as a hash. | `configure-jellydash.py` |
| <a id="jellydash_jellyfin_api_key"></a>`JELLYDASH_JELLYFIN_API_KEY` | filled by a script | empty | JellyDash's own Jellyfin API key, created by `configure-jellydash.py`. | jellydash |

### Games download page (SFTPGo)

| Key | Required | Default | What it does | Read by |
|---|---|---|---|---|
| <a id="games_user"></a>`GAMES_USER` | games | none (`admin`) | Your login to the games download page. Every account is read-only, so yours grants nothing a viewer's doesn't. | `configure-sftpgo.py` |
| <a id="games_password"></a>`GAMES_PASSWORD` | games | none | Its password. | `configure-sftpgo.py` |
| <a id="sftpgo_admin_user"></a>`SFTPGO_ADMIN_USER` | games | none (`gamesadmin`) | SFTPGo's admin, created on first start and used only by the scripts through the REST API; it may log in only from the server and Docker. | sftpgo, [`games_accounts.py`](scripts.md#games_accountspy), `stack-health` |
| <a id="sftpgo_admin_password"></a>`SFTPGO_ADMIN_PASSWORD` | games | none | Its password; use a long random value (`openssl rand -base64 24`). | same |

### Usenet

| Key | Required | Default | What it does | Read by |
|---|---|---|---|---|
| <a id="usenet_host"></a>`USENET_HOST` | no | empty | Your Usenet provider's server. When set, `configure-arr.py` adds SABnzbd to the arr apps. | `configure-sabnzbd.py`, `configure-arr.py` |
| <a id="usenet_port"></a>`USENET_PORT` | no | `563` | Its SSL port. | `configure-sabnzbd.py` |
| <a id="usenet_user"></a>`USENET_USER` | with `USENET_HOST` | none | Provider login. | `configure-sabnzbd.py` |
| <a id="usenet_pass"></a>`USENET_PASS` | with `USENET_HOST` | none | Provider password; single-quote it when it contains `$`. | `configure-sabnzbd.py` |
| <a id="usenet_connections"></a>`USENET_CONNECTIONS` | no | `20` | Connections SABnzbd opens. | `configure-sabnzbd.py` |
| <a id="nzbgeek_api_key"></a>`NZBGEEK_API_KEY` | no | empty | Adds the NZBgeek indexer to Prowlarr. | `configure-arr.py` |
| <a id="nzbfinder_api_key"></a>`NZBFINDER_API_KEY` | no | empty | Adds the NZBFinder indexer to Prowlarr; it is strong on French releases. | `configure-arr.py` |
| <a id="draupnirr_api_key"></a>`DRAUPNIRR_API_KEY` | no | empty | Adds the semi-private draupnirr tracker (French TV) to Prowlarr. | [`configure-indexers.py`](scripts.md#configure-indexerspy) |
| <a id="tr4ker_api_key"></a>`TR4KER_API_KEY` | no | empty | Adds the semi-private tr4ker tracker (French TV) to Prowlarr. | `configure-indexers.py` |
| <a id="sabnzbd_user"></a>`SABNZBD_USER` | no | empty (`admin`) | SABnzbd's web login; the apps use its API key instead. | `configure-sabnzbd.py` |
| <a id="sabnzbd_password"></a>`SABNZBD_PASSWORD` | no | empty | Its password. | `configure-sabnzbd.py` |
| <a id="sabnzbd_api_key"></a>`SABNZBD_API_KEY` | filled by a script | empty | SABnzbd's API key, copied by `configure-sabnzbd.py`. | homepage, glance; `configure-questarr.py`, `configure-jellydash.py` |

### Subtitle providers (Bazarr)

Each provider is enabled only when its keys are filled; re-run `configure-bazarr.py` after changing them.

| Key | Required | Default | What it does | Read by |
|---|---|---|---|---|
| <a id="opensubtitles_user"></a>`OPENSUBTITLES_USER` | no | empty | opensubtitles.com account (the free tier is enough), the biggest subtitle source. | `configure-bazarr.py` |
| <a id="opensubtitles_pass"></a>`OPENSUBTITLES_PASS` | no | empty | Its password. | `configure-bazarr.py` |
| <a id="subsource_api_key"></a>`SUBSOURCE_API_KEY` | no | empty | SubSource API key (subsource.net, profile). | `configure-bazarr.py` |

### Jellyfin Enhanced extras

Re-run `configure-jellyfin-plugins.py` after changing these.

| Key | Required | Default | What it does | Read by |
|---|---|---|---|---|
| <a id="tmdb_api_key"></a>`TMDB_API_KEY` | no | empty | themoviedb.org v3 API key: reviews and "where to stream". | `configure-jellyfin-plugins.py` |
| <a id="mdblist_api_key"></a>`MDBLIST_API_KEY` | no | empty | mdblist.com API key: IMDb, Rotten Tomatoes and Metacritic ratings on posters. | `configure-jellyfin-plugins.py` |

## Compose profiles

The stack is a core plus optional modules, each a Docker Compose profile. `COMPOSE_PROFILES` in `.env` picks the modules.

| Module | Services | Skipped when the module is off |
|---|---|---|
| core (always on) | gluetun, qbittorrent, sabnzbd, prowlarr, radarr, sonarr, bazarr, seerr, recyclarr, byparr, jellyfin, cleanuparr, socket-proxy | nothing |
| `music` | slskd, lidarr, navidrome, needle | `configure-lidarr.py`, `configure-navidrome.py`, the Lidarr steps of `configure-arr.py`, the Navidrome and Needle steps of `viewer-add.py` |
| `games` | questarr, sftpgo | `configure-questarr.py`, `configure-sftpgo.py`, the games login in `viewer-add.py` |
| `dashboards` | homepage, glance, changedetection | `configure-glance.py`, `youtube-sync.py` (so `arr-youtube.timer` does nothing) |
| `monitoring` | prometheus, node-exporter, scraparr, grafana, dozzle, uptime-kuma, scrutiny | `configure-dozzle.py`, `configure-uptime-kuma.py`, `configure-grafana-watch.py`, `configure-scraparr` |
| `stats` | jellystat, jellystat-db, jellydash | `configure-jellydash.py`, `configure-grafana-watch.py`, the Jellystat key in `configure-glance.py`, the Jellystat dump in `stack-backup` |
| `plex` | plex | `configure-plex.py` |

`stack-health` skips the checks of services that are off, `stack-up` requires only the library services of the modules that are on, and `configure-uptime-kuma.py` monitors only enabled services.

### `*` or a list

- `COMPOSE_PROFILES=*` turns every module on. This is the example file's value.
- A comma-separated list, such as `COMPOSE_PROFILES=music,monitoring`, turns on only those modules; the core always runs.
- Empty or missing, the scripts treat it as `*` (they export that default to every `docker compose` call they make), but a `docker compose` command you type yourself sees no profile and handles only the core. Set it explicitly.

### Switching a module off

1. Remove the module from `COMPOSE_PROFILES` in `.env`.
2. Stop and remove its containers yourself: `stack-up`'s `docker compose up -d --remove-orphans` leaves them running, because their services are still defined in `docker-compose.yml`. For example, for the games module: `docker compose rm -sf questarr sftpgo`.
3. Re-run [`configure-uptime-kuma.py`](scripts.md#configure-uptime-kumapy) if monitoring is on, so it deletes the module's monitors.

From then on the scripts skip the module (they print `~ <service> is off (COMPOSE_PROFILES in .env); skipped`). The dashboards don't follow `COMPOSE_PROFILES`: Homepage's `apps/homepage/services.yaml` and Glance's `apps/glance/glance.yml` keep every card, and a switched-off module's cards show an error or no data. Remove them from those files if they bother you.

| Module | Homepage cards | Glance widgets |
|---|---|---|
| `music` | Needle, Lidarr | Lab page: the Music entry of Apps. Media page: Coming up in music |
| `games` | Questarr, Game downloads | Lab page: the Questarr and Games page entries of Apps |
| `monitoring` | Uptime Kuma, Dozzle, Scrutiny, Grafana | Lab page: Media drive (Scrutiny and Prometheus), Uptime, Maintenance (Prometheus), and the movie and TV sizes in Library (Prometheus) |
| `stats` | JellyDash, Jellystat | Media page: Most watched this month, Watching last 30 days |
| `plex` | Plex | none |
| `dashboards` | the whole of Homepage | the whole of Glance, including Watched pages (ChangeDetection.io) |

## Hardware and resources

### compose.gpu.yml and COMPOSE_FILE

[`compose.gpu.yml`](https://github.com/bugrauluyurt/homelab-media-stack/blob/main/compose.gpu.yml) is an override that gives Jellyfin and Plex the host's `/dev/dri`, for hardware transcoding on Intel or AMD graphics on an x86-64 machine. A Raspberry Pi 5 has no video encoder, so leave it off there. The linuxserver images join `/dev/dri`'s group themselves.

1. In `.env`, set `COMPOSE_FILE=docker-compose.yml:compose.gpu.yml` and `HWACCEL=vaapi` (Intel or AMD) or `HWACCEL=qsv` (Intel).
2. Recreate Jellyfin so it gets the device: `docker compose up -d jellyfin` (and `plex` when that module is on).
3. Run [`configure-jellyfin-plugins.py`](scripts.md#configure-jellyfin-pluginspy). With `HWACCEL` set, it sets Jellyfin's hardware acceleration to that type with the device `/dev/dri/renderD128`, turns on hardware encoding and 10-bit HEVC decoding, and decodes H.264, HEVC and VP9 in hardware.

Docker Compose reads `COMPOSE_FILE` from `.env`, so every `docker compose` command in the repository, the scripts' included, uses both files. No script changes Plex's transcoder settings. [`activity-watch`](scripts.md#activity-watch) alerts only on software transcodes, so hardware ones stay quiet.

When using the VPN failover preset too, preserve it with
`COMPOSE_FILE=docker-compose.yml:compose.gpu.yml:compose.vpn-failover.yml`.

### CPU limit

The `cpus:` limit of jellyfin, plex and byparr, each on its own; default `3`. Keep it below the machine's core count so a transcode or Byparr's headless browser can't take every core.

### STORAGE_MOUNT and STORAGE_DEVICE

`STORAGE_MOUNT` (default `/mnt/storage`) must be a real mount point: `arr-stack.service` and `stack-up` refuse to start without it, so media never lands on the system disk, and `stack-health` fails when `DATA_ROOT` is not on it. On a single-disk machine, bind-mount a folder there, for example with the fstab line `/srv/media /mnt/storage none bind 0 0`. The installed units embed the mount path and its mount unit name, so re-run [`host-install`](scripts.md#host-install) after changing it. [Storage and boot](../flows/storage-and-boot.md) covers the drive's power cycle.

`STORAGE_DEVICE` (default `/dev/sda`) is the whole-disk device Scrutiny reads SMART data from; it appears as `/dev/sda` inside the container. A `/dev/disk/by-id/...` path survives device reordering (`ls -l /dev/disk/by-id/`). `apps/scrutiny/collector.yaml` sets the device type `sat`, for a drive behind a USB-SATA bridge, and the container gets `SYS_RAWIO` so smartctl can reach it. `stack-health` doesn't use this key: it finds the disk from the mount and adds `-d sat` itself for a USB drive.

### Needle image

Needle's image; the default `ghcr.io/bugrauluyurt/needle:1` follows every 1.x release. To run your own build, build it from a Needle checkout with `docker build -t needle:local <needle checkout>`, set `NEEDLE_IMAGE=needle:local`, and recreate Needle (`docker compose up -d needle`).

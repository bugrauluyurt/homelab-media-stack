# Watching

This page is for everyone who watches from the server: which app to use on each device, the
settings that keep playback smooth, what the Jellyfin look and plugins add, subtitles, watching
away from home, and the optional Plex server.

## Which player where

Jellyfin is the media server. Every app below talks to it.

| Where you are | Use | Why |
|---|---|---|
| Apple TV | **Neptune** or **Swiftfin** | Native tvOS apps that play files directly; Neptune has the most polished TV interface |
| Android TV, Fire TV, Samsung or LG TV, Roku | The **Jellyfin** app from the TV's store | The official app for each platform |
| A TV at home without Tailscale | **JellySee**, or any Jellyfin app on `http://<lan-ip>:8096` | The home network reaches Jellyfin and Seerr, which JellySee needs |
| Phone, tablet or laptop | **Jellyfin in the browser** | Gets the full look described below, with Seerr requests and recommendations. On an iPhone, add it to the Home Screen |
| Phone, native app | **Streamyfin** (shows the same home rows) or **Swiftfin** | Offline downloads |
| Away from home | Any of the above, with **Tailscale** on | See [Watching away from home](#watching-away-from-home) |

The first time, an app asks for the **server address**, because Jellyfin has no cloud account:

| From | Server address |
|---|---|
| Anywhere, over Tailscale | `http://<tailscale-ip>:8096` |
| At home, on the home network | `http://<lan-ip>:8096` |

Sign in with your own account. The owner uses `JELLYFIN_USER` / `JELLYFIN_PASSWORD` from `.env`;
everyone else gets one from `add-viewer.py` ([Giving someone access](../flows/viewers.md)). The
app remembers the server after that.

## Settings that keep playback smooth

Everything is tuned so that the device you watch on plays the file as it is ("direct play"). A
Raspberry Pi 5 has no hardware video encoder, so converting video on the fly ("transcoding") is
slow and stutters. In every Jellyfin app:

1. **Settings → Playback → Video quality:** **Auto**, or the highest bitrate offered. Never a
   fixed low bitrate: any cap below the file's own bitrate forces a transcode.
2. Leave **Allow direct play** and **Allow direct stream** switched on.

To check, play something and open Jellyfin → **Dashboard → Activity**. The session should say
**Direct Play** or **Direct Stream**, not *Transcode*. The owner also gets a push notification
whenever a stream is transcoded in software.

On an x86 server with Intel or AMD graphics, hardware transcoding can be switched on
(`compose.gpu.yml` and `HWACCEL`, see [Getting started](../getting-started.md#optional-hardware-transcoding)). A hardware
transcode is cheap and raises no alert; direct play is still the goal.

**Chromecast:** use the Cast button inside the Jellyfin app, so the Chromecast pulls the stream
straight from the server. Don't mirror your phone's screen: the phone then re-encodes its own
display, which looks worse and drains the battery.

## The Jellyfin look and plugins

`configure-jellyfin-plugins.py` sets all of this up on the server, and is safe to re-run:

| Piece | What it adds |
|---|---|
| [**Abyss**](https://github.com/AumGupta/abyss-jellyfin) theme | A dark, streaming-service style theme with a mobile layout, set as Custom CSS in Dashboard → Branding |
| **Abyss Spotlight** | A full-width rotating banner with title logos, Play and info buttons |
| **Home Screen Sections** plugin | The home rows (listed below). Streamyfin shows them too |
| [**Jellyfin Enhanced**](https://github.com/n00bcodr/Jellyfin-Enhanced) plugin | Seerr results and requests in search; requestable Recommended and Similar rows on every detail page; quality and rating badges; Calendar, Downloads and Recommendations pages in the user menu; links to Sonarr, Radarr and Bazarr |
| **File Transformation**, **Plugin Pages** | Needed by the two plugins above |
| **Neptune Indexers**, **Neptune MDM** | The server side of the Neptune app. Neptune installs them itself; the script lists them so a rebuilt server gets them back |
| **TMDb Box Sets** | Automatic collections once you own two or more films of a series. The script runs its first scan once on a fresh install |
| **Fanart** | Clear logos and extra backdrops, used by the Spotlight banner and TV apps |
| **Trakt** | Watch-history sync with Trakt. Idle until you link an account: Dashboard → Plugins → Trakt |

The home rows, top to bottom: Continue Watching, Next Up, Top 10, Because You Watched (up to
three rows), Discover (with request buttons), Recently Added Movies, Recently Added Shows, Genre
(up to two rows), Discover Movies, Discover TV, Upcoming Shows and Upcoming Movies (from Sonarr
and Radarr), My List, My Requests and Watch Again.

Things worth knowing:

- **Some rows stay hidden at first.** Because You Watched, Genre and Top 10 are built from
  watched *movies*, so they appear once some have been played.
- **Row order must have no gaps.** Home Screen Sections 3.0.2 shows an empty home screen when the
  first row is 0 and the next one isn't 1; the script numbers them 0, 1, 2 and so on. If the home
  screen ever says "Nothing here", see the
  [known issue](https://github.com/bugrauluyurt/homelab-media-stack/blob/main/ai/homelab-plugin/skills/stack-logs/references/known-issues.md#jellyfin-home-screen-shows-nothing-here).
- **Spotlight isn't a plugin.** `apps/jellyfin/custom-cont-init.d/abyss-spotlight.sh` (vendored from
  Abyss, MIT) adds its loader to Jellyfin's `index.html` on every container start, so it survives
  image updates.
- **Links follow the address you used.** The plugins reach Seerr and the arr apps over the
  Docker network with the API keys from `.env`, and links shown to your browser are mapped to the
  address you opened Jellyfin on (Tailscale, home network, `.local` or localhost).
- **Requests need a Seerr account.** Each Jellyfin user needs a linked Seerr account with request
  permission; `add-viewer.py` creates it.
- **Optional extras.** `TMDB_API_KEY` adds reviews and "where to stream"; `MDBLIST_API_KEY` adds
  IMDb and Rotten Tomatoes ratings on posters. Fill them in `.env`, then re-run the script.
- **The server's name** in apps is `JELLYFIN_SERVER_NAME` (default "Home Media").
- **No Skip Intro button.** The Intro Skipper plugin was removed; see
  [Maintenance](../operations/maintenance.md#intro-skipper-removed).

Where it shows: everything works in the browser and the iPhone app. On TVs the home rows work,
but Jellyfin Enhanced's extras may be missing, since it supports Jellyfin Desktop only from its
unreleased version 3.0. The official Android TV app is native and ignores all of this.

## Subtitles

Bazarr fetches English subtitles automatically, a few minutes after a file is imported. It saves
them as separate `.srt` files next to the video, on purpose:

- A browser can only show subtitles embedded in the file after Jellyfin reads the whole file to
  extract them, which leaves playback stuck on "Fetching additional data".
- Image subtitles (PGS, VOBSUB) have to be burned into the picture, which is a full transcode.
  Text subtitles (SubRip, ASS) can be switched on without touching the video.

If a subtitle is missing, open Bazarr (`:6767`), find the title and search manually with the
magnifying glass. To see which subtitle formats a file carries:

```bash
docker exec jellyfin /usr/lib/jellyfin-ffmpeg/ffprobe -v error \
  -select_streams s -show_entries stream=index,codec_name \
  -of csv=p=0 "/data/media/movies/<title>/<file>.mkv"
```

If it reports `pgs` or `dvd_subtitle`, let Bazarr fetch an external `.srt` for that title and pick
that track instead.

A free **OpenSubtitles.com** account noticeably improves hit rates: it is the biggest source. Put
it in `.env` as `OPENSUBTITLES_USER` / `OPENSUBTITLES_PASS` (and optionally `SUBSOURCE_API_KEY`),
then re-run `configure-bazarr.py`. Series whose original language is French are tagged `french`
in Sonarr, which gives them Bazarr's French subtitle profile, since English subtitles for French
TV rarely exist.

## Watching away from home

1. Install **Tailscale** on the phone, tablet or laptop and sign in.
2. Open Jellyfin as usual, at `http://<tailscale-ip>:8096`.

Tailscale makes the server reachable as if you were at home, encrypted end to end, with no port
open on your router. Family and friends get their own account and a limited slice of your
tailnet: see [Giving someone access](../flows/viewers.md).

Everything you watch away from home has to fit through your home **upload**:

| File | Bitrate | Away from home |
|---|---|---|
| 1080p encode (most things) | 8 to 15 Mbps | Comfortable on most connections |
| 1080p remux (large files) | 15 to 25 Mbps | One stream |
| 4K | 80 to 100 Mbps | Beyond most home uploads |

This is one reason the library targets 1080p ([why](requesting.md#why-everything-is-1080p)). Torrent
seeding shares the same upload and is capped permanently at 10 Mbps to leave room for streams;
Usenet uploads nothing. Game downloads from the games page share it too.

If a stream stutters away from home, lower the app's quality *while away* and set it back to
maximum at home. That makes the server transcode; a Raspberry Pi 5 manages one 1080p transcode at
most, so don't ask for two at once.

## Plex (optional)

Plex runs when the `plex` module is in `COMPOSE_PROFILES`, already tuned for direct play but not
linked to a Plex account. Both servers read the same library side by side without conflict; Plex
mainly adds slightly more polished TV apps. To claim it:

1. Get a claim token from <https://plex.tv/claim>. It expires in about four minutes.
2. Put it in `.env` as `PLEX_CLAIM`.
3. `docker compose up -d --force-recreate plex`, then open `http://<tailscale-ip>:32400/web`.

Plex runs on the host network and is reachable over Tailscale only. `configure-plex.py` keeps its
preferences right (it stops Plex while it writes them, because Plex rewrites its preferences file
on exit):

| Setting | Why |
|---|---|
| The home network **and** Tailscale's `100.64.0.0/10` count as local | Otherwise Plex treats tailnet devices as remote, caps their bitrate and forces a transcode |
| Scheduled daily library scans, no file-system watching | The media drive is a spinning disk; watching for changes would keep waking it |
| No video preview thumbnails, chapter thumbnails or loudness analysis | Each one reads every file in full |
| Transcode scratch space in RAM (`/transcode`, 2 GB) | Rare transcodes don't grind the system disk |

In each Plex app, set quality to **Original** and switch **off** "Automatically Adjust Quality".

## Quick answers

| Problem | Answer |
|---|---|
| Something new doesn't appear | The media drive may be off, or the library hasn't rescanned. Jellyfin rescans the moment Radarr or Sonarr imports, and on a schedule every 12 hours; real-time folder watching is off so the drive can rest. Force it with **Dashboard → Scan All Libraries** |
| Buffering at home | **Dashboard → Activity** says *Transcode*: an app's quality setting is too low (see above) |
| Works at home, not away | Tailscale isn't connected on that device |
| A show has no poster or description | See the [known issue](https://github.com/bugrauluyurt/homelab-media-stack/blob/main/ai/homelab-plugin/skills/stack-logs/references/known-issues.md#a-show-is-in-jellyfin-but-has-no-poster-or-description) |
| "Account disabled" | Jellyfin locks a non-admin account after 3 wrong passwords; the owner re-enables it in Jellyfin → Users |
| Subtitles missing | Search for them in Bazarr (`:6767`), as above |

More in [Troubleshooting](../troubleshooting.md).

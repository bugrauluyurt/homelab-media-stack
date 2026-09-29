# Maintenance

This page is for the owner: the day-to-day care of the server. Most of it runs by itself; the
page says what does, what is left to you, and how to check on it. `health` (the
[terminal alias](terminal.md) for `scripts/health-check`) covers nearly all of it at a glance.

## The chores at a glance

| Chore | Runs by itself | Left to you |
|---|---|---|
| [Image updates](#updates) | A check every morning at 06:00, pushed to your phone | Apply them with `update` when it suits you |
| [Stack upgrades](#upgrading-the-stack) | Nothing | Pull a new release of this repository when you want its changes |
| [Stalled and fake downloads](#cleanuparr) | Cleanuparr, every 5 minutes | Nothing, unless you change its rules |
| [Disk space](#disk-space) | `health-check` fails above 90% full | Delete what you no longer want |
| [Drive health](#drive-health) | SMART checks every 6 hours, with a push on failure | Replace a failing drive in time |
| [Backups](#backups) | Every night at 04:30 | Check now and then that they run; keep the password off the server |
| The VPN's forwarded port | `sync-port`, every 15 minutes | Nothing ([VPN and ports](../flows/vpn-and-ports.md)) |
| [Credentials](#rotating-credentials) | Nothing | Rotate one when it may have leaked |

Everything that needs a person arrives on your phone through ntfy; the full list of alerts is in
[Monitoring](../flows/monitoring.md).

## Updates

Nothing updates itself. `arr-updates.timer` runs `check-updates` every morning at 06:00: it
compares each image with what is published for the server's own architecture and pushes anything
new to your phone once, as `old -> new`, flagging a change of the first version number as
**MAJOR** (read the release notes of those first). `health` lists pending updates in yellow.

```bash
update                              # every service with an update
update jellyfin sonarr              # or just these
update --rollback jellyfin          # previous image and its settings
update --rollback jellyfin --image-only
```

`update` snapshots the settings first, keeps each current image as a rollback tag, recreates
only the updated services and runs the health check afterwards. It is never automatic because
these apps depend on each other: a single Jellyfin release once broke the logins of Seerr,
Sonarr, Radarr and Homepage at once. The whole story, including rollback, is in
[Updates](../flows/updates.md).

## Upgrading the stack

`update` changes app images; the stack itself (the compose file, scripts and units) changes
only when you pull a new version of this repository. Read the release notes on the
[releases page](https://github.com/bugrauluyurt/homelab-media-stack/releases) first: a major
version lists what to change in `.env` or on the server, and new keys are in `.env.example`.

```bash
cd ~/homelab-media-stack
sudo scripts/backup-config pre-update   # settings snapshot, kept like update's
git pull --ff-only                      # main; or git checkout vX.Y.Z for a tagged release
scripts/install-host                    # re-renders changed units and timers
scripts/stack-up                        # recreates only the services whose definition changed
health
```

A release that needs a configure script run again says so in its notes; all of them are safe to
re-run.

## Cleanuparr

Cleanuparr removes downloads that will never finish or should never be imported, and blocklists
them so Radarr and Sonarr grab a different release. Open it at `http://<tailscale-ip>:11011`,
user `admin`, password `CLEANUPARR_PASSWORD` from `.env`. `configure-cleanuparr.py` sets it up,
and is safe to re-run.

| Rule | What it does |
|---|---|
| **Stalled** | No progress at all for about an hour (12 strikes, one per 5-minute run) removes the download and blocklists the release. Any progress resets the count, so slow but moving downloads are never touched |
| **Failed import** | A download that can't be imported after 3 checks is removed and blocklisted |
| **Stuck on metadata** | A magnet that never resolves is removed after 3 checks |
| **Malware** | Blocks executables, shortcuts and archives inside downloads |
| Slow downloads | **Off**: slow is normal on public trackers |
| Download cleaner (seeding, orphans, no-hardlink) | **Off**: seeding costs no disk space, thanks to hardlinks |

Its safety settings, and why:

- **No access to your media.** Cleanuparr has no `/data` mount; it acts only through the
  qBittorrent, Radarr and Sonarr APIs and can't touch files itself.
- **Game downloads are ignored.** The qBittorrent category `games` is on its ignore list: game
  releases always contain executables and archives, so the malware rule would reject every one.
- **The malware list is `blacklist_permissive`, on purpose.** The stricter default list blocks
  `*.srt`, `*.sub` and `*.idx`, so any release carrying its own subtitles would quietly lose them.
  The permissive list blocks no video, subtitle or audio format.
- **Archives are blocked**, which suits this setup: there is no extractor, so an archived release
  could never be imported anyway. Blocking it makes the arr apps find a normal one.
- **The download cleaner stays off.** The configure script refuses to go live if it finds it on.

`health-check` confirms all of it: Cleanuparr is healthy, live (not dry-run), its download
cleaner is off, it ignores games, and it has no media mount.

To try a change safely, use dry-run mode: Cleanuparr then only logs what it *would* do.

```bash
scripts/configure-cleanuparr.py --dry-run   # dry-run; watch its log in Dozzle
scripts/configure-cleanuparr.py             # back to live
scripts/cleanuparr-state                    # prints e.g. "live downloadcleaner=off ignored=games"
```

## Disk space

`health-check` fails when the media drive or the system disk is 90% full or more, and Glance's
Lab page shows the media drive's free space, how fast it has grown over the last week, and the
date it would be full at that rate (in red when that is less than 30 days away).

What takes the space, and what to know before freeing it:

- **Media and seeding share the space.** A finished torrent is hardlinked into the library: the
  same file appears in `torrents/` and `media/` and uses the disk once. The space comes back only
  when both are gone: delete the title in Radarr or Sonarr (with its files) and remove its
  torrent from qBittorrent. Don't delete things out of `torrents/` by hand.
- **Usenet downloads** are moved into the library when complete; nothing stays behind.
- **Settings backups** live on the media drive under `$STORAGE_MOUNT/backups`; see
  [Backups](../flows/backups.md) for how they are thinned.
- **On the system disk**, Prometheus keeps at most 30 days and 4 GB, container logs are capped at
  three 10 MB files per container, and `update` keeps one rollback image per app.

## Drive health

Every 6 hours `arr-health.timer` runs `health-check --notify`, which reads the media drive's SMART
data and pushes a failure to your phone. It checks three things:

| Check | Fails when |
|---|---|
| SMART health | The drive's own self-assessment fails |
| Bad sectors | Any reallocated, pending or offline-uncorrectable sector (or, on NVMe, any media error): failure is near |
| Temperature | 55 °C or more |

On a Raspberry Pi it also checks that the board isn't throttled or short of power, and that the
chip stays under 80 °C.

For history, Scrutiny (`:3006`, [Dashboards](../using/dashboards.md#scrutiny)) keeps the SMART
attributes and temperature over time. For a closer look, ask an AI agent with the `drive-health`
skill, which also checks the USB link of a drive in an enclosure. Before you switch the drive
off, run `storage-off` first ([Storage and boot](../flows/storage-and-boot.md)).

## Backups

The settings of every app are backed up every night at 04:30; media never is. To check they
run:

- `health` has a **BACKUPS** section: the timer is enabled, the last backup is under 48 hours old
  (checked only while the media drive is mounted), the password copy is on the media drive, and
  the second copy exists on the system disk.
- Glance's Lab page shows when the settings were last backed up, in red after 48 hours.
- `cat /var/lib/arr-backup/last-success` prints the time of the last successful run.

What is backed up, where, the offsite copy and every way to restore: [Backups](../flows/backups.md).

## Intro Skipper (removed)

The Intro Skipper plugin was removed: its audio fingerprinting ran ffmpeg over every new episode
and kept a CPU core busy on a Raspberry Pi. `configure-jellyfin-plugins.py` uninstalls it and
drops its repository, and `health-check` confirms it stays gone. There is no Skip Intro button.

## Rotating credentials

Every login and key lives in `.env` (see [Configuration](../reference/configuration.md)). How to
change one depends on who applies it:

| Credential | Change it | Then |
|---|---|---|
| `DOZZLE_PASSWORD`, `JELLYDASH_PASSWORD`, `UPTIME_KUMA_PASSWORD`, `QUESTARR_PASSWORD`, `GAMES_PASSWORD`, `SABNZBD_PASSWORD` | In `.env` | Re-run the matching script (`configure-dozzle.py`, `configure-jellydash.py`, `configure-uptime-kuma.py`, `configure-questarr.py`, `configure-sftpgo.py`, `configure-sabnzbd.py`). Each notices the login no longer works and writes the new password |
| `JELLYFIN_PASSWORD` | In Jellyfin (your user → Password), then in `.env` | `configure-seerr.py` signs in with it |
| `NAVIDROME_PASS` | In Navidrome, then in `.env` | `configure-lidarr.py`, `configure-navidrome.py` and `add-viewer.py` sign in with it |
| `CLEANUPARR_PASSWORD` | In Cleanuparr, then in `.env` | `cleanuparr-state` and `health-check` sign in with it |
| `GRAFANA_PASSWORD` | In Grafana (your profile), then in `.env` | `configure-grafana-watch.py` signs in with it |
| A viewer's password | Ask them to change it in each app | `add-viewer.py` never changes an existing account's password |
| `NTFY_TOPIC` | In `.env` (the stack's own scripts read it on every run) | Re-run `configure-seerr.py` and `configure-questarr.py`, recreate JellyDash (`docker compose up -d jellydash`), and change the topic by hand in the ntfy notification of Radarr, Sonarr, Lidarr, Prowlarr and Uptime Kuma (their scripts add it once and leave it alone). Then subscribe to the new topic on your phone |
| `WIREGUARD_PRIVATE_KEY` | A new Proton configuration | Changes the VPN: see [VPN and ports](../flows/vpn-and-ports.md) |
| `RESTIC_PASSWORD` | Not in `.env` alone | The existing backup repositories open only with it; see [Backups](../flows/backups.md) |

An app's API key is copied into several places (other apps, Homepage, Glance, Scraparr). Rotate
one only when it may have leaked, update every app that uses it, and run `health` afterwards to
find anything still holding the old one.

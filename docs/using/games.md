# Games

This page is for everyone who gets PC games through the server: finding and grabbing a game in
Questarr, then copying it to a PC from the read-only games download page or over SFTP, including
how to resume a big download. Games are the `games` module in `COMPOSE_PROFILES`. The pipeline
behind it is in [Games flow](../flows/games.md).

The server only stores these games. They are Windows or PC files; it can't run them.

## Questarr: finding a game

Open **Questarr** at `http://<tailscale-ip>:5000` and log in as `admin` with `QUESTARR_PASSWORD`
from `.env`. Questarr needs a free IGDB key before it can search for games or show covers; the
owner sets that up once ([Getting started](../getting-started.md#fill-in-env)).

Questarr works like Radarr, with one difference: **it doesn't pick releases for you.**

1. Search for the game, add it and mark it **Wanted**.
2. Questarr searches the indexers on a schedule and lists what it found on the game's page.
3. Choose a release: a known repack group with plenty of seeders. Public trackers carry fakes, so
   check a release's comments and uploader before you run anything from it.
4. Click download. A Usenet release goes to SABnzbd, a torrent to qBittorrent inside the VPN.

Questarr's "auto download" only fires when a search returns exactly one release, so it stays off.
Finished downloads sometimes stay untracked in Questarr; use **Claim** on its Downloads page.

The owner gets push notifications (ntfy): **Game Available** when a wanted game has releases to
pick from, and **Download Started**, **Completed** or **Aborted** for downloads.

**For viewers:** everyone shares the one Questarr login, and Questarr has no approval step. So
the rule is: mark games *Wanted*, and leave picking the release to the owner. "Download Started"
is how the owner learns someone picked one anyway.

Where the files land:

| Source | Folder | On the games page |
|---|---|---|
| Torrent | `$DATA_ROOT/torrents/games` | *Torrent* |
| Usenet | `$DATA_ROOT/usenet/complete/games` | *Usenet* |

Cleanuparr leaves game downloads alone: game releases always contain `.exe` files and archives,
which its malware rule would otherwise reject. Questarr takes its indexers from Prowlarr; after
adding an indexer there, the owner re-runs `configure-questarr.py` to pick it up.

## The games download page

The page is SFTPGo, set up read-only: nobody can upload, rename, delete or share anything there.

| From | Address |
|---|---|
| At home, on the home network (fastest) | `http://<lan-ip>:8090` |
| Anywhere, over Tailscale | `http://<tailscale-ip>:8090` |

Log in with your games login: the owner's is `GAMES_USER` / `GAMES_PASSWORD` from `.env`, and
viewers get their own from `add-viewer.py` (the same password as their Jellyfin one). The page
shows two folders, *Torrent* and *Usenet*.

- **One file:** click it to download.
- **Several files or folders:** tick them and press **Download** to get one zip.

### Resuming big downloads

- A **single file** continues where it stopped if the connection drops: press **Resume** in the
  browser's downloads list.
- A **zip of several items** is built on the fly and starts over if interrupted.

So for a big game over the internet, download the files one by one, or use SFTP.

### Whole folders with resume: SFTP

SFTP copies a whole game folder and resumes after an interruption. It answers on the tailnet
only (port 2022 is closed to the home network), so connect over Tailscale.

In **WinSCP** (Windows) or **FileZilla**:

| Field | Value |
|---|---|
| Protocol | SFTP |
| Host | `<tailscale-ip>` |
| Port | `2022` |
| User and password | Your games login |

Then drag a game folder across. It is read-only, like the page.

The owner can use `rsync` over SSH instead (the path shown is the default `DATA_ROOT`):

```bash
rsync -avP --partial "<host>:/mnt/storage/data/torrents/games/<game>" ~/Downloads/
```

## How fast

The server's disk usually reads a game faster than a gigabit network can carry it.

| Where you are | What limits it |
|---|---|
| At home, wired, on `http://<lan-ip>:8090` | Your network: up to about 110 MB/s on gigabit |
| At home, through Tailscale | Encryption and relaying: slower |
| Away from home | Your home **upload**, shared with anyone streaming from Jellyfin and with torrent seeding |

Away from home, a 50 GB game over a 30 Mbps upload takes about four hours.

When something goes wrong, see [Troubleshooting](../troubleshooting.md#games).

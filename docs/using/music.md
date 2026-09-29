# Listening to music

This page is for everyone who listens to music from the server: Needle, the player, on a
computer or as a phone home-screen app; how to get albums and single songs you don't have yet;
and Navidrome, the music server underneath. Music is the `music` module in `COMPOSE_PROFILES`.
How the pieces fit together behind the scenes is in [Music flow](../flows/music.md).

## Needle, the player

**Needle** is a music player built for this stack, on top of Navidrome. Open it at its HTTPS
address, `NEEDLE_PUBLIC_URL` in `.env`:

```text
https://<host>.<tailnet>.ts.net:4535
```

That address is the only way in. Tailscale Serve provides it with a Tailscale certificate, on
the tailnet only ([how it is set up](../operations/host.md#https-for-needle-tailscale-serve)).
Offline downloads, the phone home-screen app and Spotify all need HTTPS anyway.

Sign in with a Navidrome account. The owner uses `NAVIDROME_USER` / `NAVIDROME_PASS` from `.env`.
Viewers get an account from `add-viewer.py`, with the same password as their Jellyfin one; the
username is their name up to any "@", so `you@example.com` signs in as `you`.

What you get:

- **Home:** mixes made from your library, recently added music, a card to pick up where
  another device stopped, and your ListenBrainz playlists once you connect them (below).
- **Search** of your library, matching text anywhere in a title, artist or album. It also offers
  music you don't have, which you can ask for (below).
- **Your library:** All, Songs, Albums, Artists and Playlists, with its own search.
- Album, artist and playlist pages, liked songs, timed lyrics, song and artist radio, internet
  radio, and your listening stats.
- **Devices:** every other open Needle shows up here. Pause it, skip, or pull its music over to
  the device in your hand.
- **Settings → Your photo** sets the picture in the corner, on every device.

Everyone signs in with their own account, so likes, playlists, stats and mixes are personal.

### As a home-screen app

On an iPhone, open the Needle address in Safari, then **Share → Add to Home Screen**. It then runs
full screen, with lock-screen controls and downloads for offline listening.

## Getting music you don't have

Search for it in Needle. Results you don't have yet come with a button:

| Button | What happens | Where it lands |
|---|---|---|
| **Get album** | Lidarr starts watching that one album (never the whole artist) and downloads it | The **Music Library**, Lidarr's albums |
| **Get song** | Needle fetches just that song from Soulseek, through the VPN | The **Singles** library |

Searching an artist's exact name also lists that artist's studio albums. When several artists
share a name, the one Lidarr already knows (or the best-known one) is used.

Follow progress on the **Requests** page (the account menu, or **You** on a phone). Each request
moves through *searching*, *downloading*, *adding* and finally *in your library*. The page
refreshes every few seconds while something downloads. Navidrome rescans every 15 minutes, so a
finished album or song appears within that time.

Who may ask: Navidrome admins always can. Anyone else can once the owner switches on **Request
music** for them in **Settings → People**, or adds them with `add-viewer.py --music-requests`.
People appear in Settings → People after their first sign-in.

### For the owner

Admins also see **Downloading now** on the Requests page: every album Lidarr is downloading,
whoever asked, and every song Needle is fetching, with progress and failures.

- **"Album match is not close enough"**: Lidarr downloaded a copy that doesn't match the album.
  Press **Find another copy** (blocklists that release and searches again) or **×** (removes and
  blocklists it without a new search).
- **A FLAC-only album never downloads**: new artists get the *Standard* quality profile, which is
  lossy only. Switch that artist to *Any* or *Lossless* in Lidarr (`:8686`) to take it.
- **A single song came out wrong**: Soulseek copies vary. Delete the file from
  `$DATA_ROOT/media/singles` and ask again.

More music problems and their fixes are in [Troubleshooting](../troubleshooting.md#music).

You can also use **Lidarr** (`http://<tailscale-ip>:8686`) directly: search an artist, add it and
choose what to monitor. Nothing downloads unless you choose it: new artists start unmonitored, and
Lidarr's import lists (such as Spotify followed artists) stay off, because they once added
hundreds of artists with every album monitored and pulled in music nobody asked for.
`configure-arr.py` keeps it that way. For a search by hand, slskd has its own web page
(`http://<tailscale-ip>:5030`, user `admin`, password `SLSKD_PASSWORD`).

## Discovery with ListenBrainz

[ListenBrainz](https://listenbrainz.org) is a free, open service that learns what you like from
what you play and makes playlists for you every week: **Weekly Exploration** with songs you
haven't heard, **Weekly Jams** and **Daily Jams** with songs you like and more like them. Each
person connects their own account; the owner sets nothing up.

To connect:

1. Create an account at <https://listenbrainz.org> and copy your **user token** from
   <https://listenbrainz.org/settings/>.
2. In Needle, open **Settings → ListenBrainz** and paste the token.
3. Optionally type your Navidrome password (the one you sign in to Needle with). Needle uses it
   once to switch on scrobbling in Navidrome, so everything you play is sent to ListenBrainz, and
   never stores it. Leave it empty to do that yourself: in Navidrome
   (`http://<tailscale-ip>:4533`, owner only) open **Settings → Personal → ListenBrainz** and paste
   the same token.
4. Choose **Connect ListenBrainz**. Settings then shows *Connected as* your ListenBrainz name, and
   whether Navidrome sends your listens.

ListenBrainz needs about a week of listening before the first playlists appear. They show up on
Home under **Made for you by ListenBrainz**, with how many songs you already have and how many
you could get. On a playlist:

- **Play** and **Shuffle** play the songs in your library.
- **Get N missing** fetches the rest from Soulseek into the **Singles** library, like **Get song**
  (only for people who may request music). Each song also has its own **Get song**.
- **Save as playlist** keeps the songs you have as a Navidrome playlist, named after the playlist
  and its date.

**Disconnect** in Settings removes your token from Needle. Navidrome keeps sending your listens
until you remove the token there too.

## Spotify (optional)

With Spotify connected, your Spotify liked songs, playlists and saved albums show up in Your
library, Home and Search, and play inside Needle. The server never downloads from Spotify: **Get
song** on a Spotify track goes through Soulseek like any other.

- Playlists you made can be edited; playlists you only follow can't be read, a Spotify rule for
  personal apps.
- Settings can copy a Spotify playlist into a Navidrome playlist from the songs you own, and send
  the rest to Lidarr.
- **Settings → Use Spotify in Needle** switches Spotify off for your account on every device
  without disconnecting it. Off means no request to Spotify at all.
- Spotify rate-limits personal apps, and everyone connected shares one limit. When Spotify refuses
  (`429`), Needle stops asking for as long as Spotify says (an hour when the browser can't read the
  wait) and hides Spotify meanwhile; it comes back by itself.

Each person connects their own Spotify, and only if the owner allows **Spotify** for them in
Settings → People (or adds them with `add-viewer.py --spotify`).

To set it up (the owner, once; it needs Spotify Premium):

1. Create an app at <https://developer.spotify.com> with the redirect URI
   `<NEEDLE_PUBLIC_URL>/api/spotify/callback`.
2. Put its `SPOTIFY_CLIENT_ID` and `SPOTIFY_CLIENT_SECRET` in `.env`.
3. `docker compose up -d needle`, then connect in Needle's Settings.
4. Spotify's development mode requires every Spotify account that connects to be listed under
   **User Management** in the Spotify dashboard.

## Navidrome, the music server

Navidrome holds the library, the accounts, playlists and likes. It has two libraries:

| Library | Folder | Filled by |
|---|---|---|
| **Music Library** | `$DATA_ROOT/media/music` | Lidarr, album by album |
| **Singles** | `$DATA_ROOT/media/singles` | Needle, song by song |

They are kept apart so Lidarr never manages Needle's single songs. Every non-admin account can see
both libraries.

The owner can also use Navidrome's own web page at `http://<tailscale-ip>:4533`: plainer than
Needle, but fine for admin work such as users, scanning and Last.fm scrobbling
(Settings → Personal). Any Subsonic app works against that address too:

| Device | App |
|---|---|
| iPhone | **Amperfy** (free, offline downloads) or play:Sub (paid) |
| Mac or Windows | **Feishin** |
| Android | Symfonium (paid) or Tempo (free) |

Viewers reach Needle only, not Navidrome's port 4533: the Tailscale policy leaves it closed, and
Needle passes the music through.

## What is kept safe

Your likes, playlists, play history, requests, Spotify sign-in and ListenBrainz token are in the
nightly settings backup; the music files are not, since they can be fetched again
([what's backed up](../flows/music.md#whats-backed-up)).

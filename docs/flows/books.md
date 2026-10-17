# Books

The optional `books` profile pairs Shelfmark (search and requests) with
Calibre-Web Automated (CWA, library and reader). Images are pinned to explicit
release versions, not floating `latest`; validate a new version before changing the pins.
Both selected images publish arm64 and amd64 variants.

## Boundaries

- Shelfmark searches existing Prowlarr indexers. It sends torrents to
  `gluetun:8080` and Usenet jobs to `sabnzbd:8080`. Do not add an embedded torrent
  client or bypass gluetun. No second VPN is needed.
- Both web ports bind to loopback only: Shelfmark 8084, CWA 8083. First configure
  authentication over an SSH tunnel. Publish through Tailscale Serve only after
  setup. Do not add these ports to `HOME_APPS` or expose them on the LAN.
- Shelfmark has read-only access to book download directories and the final
  catalogue. It writes completed copies into a separate ingest folder. Keep
  `HARDLINK_TORRENTS=false`: CWA can modify imported books, so hardlinks would
  risk changing files still being seeded. Torrent action stays `keep`.
- CWA owns the library and consumes/deletes ingest files after processing. Never
  mount original downloads as its ingest folder. Neither app can modify movies,
  music, games or other download categories.
- The standard Shelfmark image includes its bundled browser and has a 2 GiB
  memory limit. Prowlarr still uses the stack's existing indexer/proxy
  configuration. Direct sources are optional and require separate configuration;
  switching images does not enable them. Availability depends on configured sources.

## Storage

| Host path below `DATA_ROOT` | Purpose |
|---|---|
| `torrents/books` | Originals retained for seeding |
| `usenet/complete/books` | Completed SABnzbd jobs |
| `books/ingest` | Completed copies waiting for CWA; disposable after import |
| `media/books` | CWA library and `metadata.db` |

Settings live in `CONFIG_ROOT/shelfmark` and
`CONFIG_ROOT/calibre-web-automated`. The existing settings backup snapshots their
SQLite databases. It also snapshots `media/books/metadata.db` to
`/var/tmp/arr-backup/books/metadata.db` when the profile is enabled. Book files
are **not** included. Restore this catalogue only with its matching book library;
image rollback restores app settings, not this separately staged catalogue.

## Installation (approval required)

1. Take a settings backup. Confirm the storage mount is present. Create the four
   data directories above and the two configuration directories, owned by
   `PUID:PGID`. Bind mounts refuse to create missing media paths automatically.
2. Add `books` to `COMPOSE_PROFILES` in `.env` after approval. A value of `*`
   already includes it; adding this Compose definition makes it eligible on the
   next full `stack-up`. Do not run a full-stack restart just to add books.
3. Ensure the existing `PROWLARR_API_KEY` and `SABNZBD_API_KEY` values are populated
   without printing them. Create a `books` category in SABnzbd with relative
   folder `books` under `/data/usenet/complete`. In qBittorrent use category
   `books` and save path `/data/torrents/books`.
4. Run `docker compose up -d --no-deps shelfmark calibre-web-automated`.
5. From your workstation, open an SSH tunnel:

   ```bash
   ssh -N -L 8083:127.0.0.1:8083 -L 8084:127.0.0.1:8084 bugra-raspi
   ```

6. At `http://localhost:8083`, finish CWA setup and immediately change the
   upstream default administrator credentials. Disable anonymous access and
   public registration. Use `/calibre-library` for the library. At
   `http://localhost:8084`, complete Shelfmark's local administrator setup;
   authentication is configured as `builtin`, never `none`. Viewer accounts and
   approvals are separate from Jellyfin; do not grant admin access to viewers.
7. In Shelfmark, test Prowlarr, qBittorrent and SABnzbd connections. Verify book
   categories and paths. Keep torrent action `keep`, Usenet action `copy` and
   hardlinks off. Settings saved in the UI can override environment defaults.
8. Configure Tailscale Serve for the two loopback ports after approval and verify
   access using the intended account. Do not grant viewer access in the tailnet
   policy until shared access is requested. Add the resulting HTTPS URLs to your
   dashboard; never link users to a loopback URL.

## Acceptance checks

- `scripts/stack-health` includes both endpoints when the profile is enabled.
- Test each configured download-client connection, not just the HTTP endpoints.
- Search for a public-domain book; inspect results before downloading.
- Download an authorized test title and confirm one completed copy is imported,
  readable in CWA, and downloadable to a computer. Confirm the torrent original
  remains unchanged and seeding. Also test a manual EPUB import to distinguish
  a source/indexer problem from an ingest problem.
- Verify anonymous access is denied, normal users cannot administer either app,
  and neither web port is accessible from the home LAN.
- Take a backup and verify the app databases and separate catalogue are included.

Until these checks pass, the profile is staged infrastructure, not a verified
end-to-end deployment. Adding it does not modify existing downloader settings,
create users, publish web ports, or download any books automatically.

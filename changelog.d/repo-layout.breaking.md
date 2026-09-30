- The repository layout is tidier, and upgrading needs two steps after `git pull`: run
  `scripts/host-install`, then `scripts/stack-up`.
  - Scripts are named area first: `health-check` is now `stack-health`, `update` is `stack-update`,
    `backup-config` is `stack-backup`, `check-updates` is `stack-update-check`, `notify-failure` is
    `stack-failure-notify`, `storage-off` is `drive-off` (the alias too), `sync-port` is
    `vpn-port-sync`, `leak-test` is `vpn-leak-test`, `install-host` is `host-install`, `firewall` is
    `host-firewall`, `install-agent` is `agent-install`, `check-indexers` is `indexers-check`,
    `add-indexers.py` is `configure-indexers.py`, `render-scraparr-config` is `configure-scraparr`,
    `throttle-downloads` is `downloads-throttle`, `watch-activity` is `activity-watch`,
    `sync-youtube.py` is `youtube-sync.py`, `add-viewer.py` is `viewer-add.py` and `check` is
    `repo-check`. `host-install` points the installed units at the new names.
  - The per-app config folders moved into `apps/`, so `stack-up` recreates the containers that
    mount them (gluetun with qBittorrent and slskd, Jellyfin, Glance, Homepage, Grafana,
    Prometheus, Scrutiny, Recyclarr). A local edit in one of them survives
    `git stash && git pull --ff-only && git stash pop`.
  - The unit templates moved to `host/systemd/`, and the community files to `.github/`.

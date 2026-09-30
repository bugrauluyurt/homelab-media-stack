# Terminal

This page is for the owner, when you are already logged in to the server over SSH and don't want
a browser: the shell aliases the repository ships, the terminal tools they open, and how to load
them in zsh or bash.

## The aliases

`scripts/aliases.zsh` defines them:

| Alias | Runs | For |
|---|---|---|
| `health` | `scripts/stack-health` | One-shot status of the whole stack ([Troubleshooting](../troubleshooting.md)) |
| `update` | `scripts/stack-update` | Snapshot, update, health check; `update --rollback <service>` ([Updates](../flows/updates.md)) |
| `leaktest` | `scripts/vpn-leak-test` | Proves torrent traffic exits through the VPN ([VPN and ports](../flows/vpn-and-ports.md)) |
| `indexers` | `scripts/indexers-check` | Which indexers work ([Indexers](indexers.md#testing-indexers-indexers-check)) |
| `drive-off` | `scripts/drive-off` | Stops the stack and unmounts the media drive before you switch it off ([Storage and boot](../flows/storage-and-boot.md)) |
| `stack` | `cd $MEDIA_STACK_DIR` | Jump to the repository |
| `qbt` | qbt-tui | What is downloading: torrents, speed, peers, progress |
| `arr` | managarr | Radarr, Sonarr and Lidarr: library, queue, history, blocklist |
| `dock` | lazydocker | Every container: status, logs, CPU and memory, restart |

**btop** needs no alias: run `btop` for the server's CPU, memory, temperature and processes.

## Loading them

The aliases are plain `alias` lines, so zsh and bash both read them. Add one line to your shell's
startup file:

```bash
echo 'source ~/homelab-media-stack/scripts/aliases.zsh' >> ~/.zshrc     # zsh
echo 'source ~/homelab-media-stack/scripts/aliases.zsh' >> ~/.bashrc    # bash
```

Open a new shell (or `source` the file) to use them. They point at `~/homelab-media-stack` unless
`MEDIA_STACK_DIR` is set before the `source` line (`export MEDIA_STACK_DIR=/path/to/homelab-media-stack`).

## The tools

The repository doesn't install the four terminal tools; install them with your package manager
or from their releases. Their settings live in your home folder, and the nightly backup keeps
`~/.config/managarr` and `~/.config/qbt-tui`.

### qbt: what is downloading

A live list of every torrent: name, progress, speed, seeds and peers, time left. Arrow keys move,
`Enter` shows details (files, trackers, peers), `q` quits.

It talks to qBittorrent's API on `127.0.0.1:8080` and needs no login: requests from the Docker
network and the tailnet skip it, while the home network must always log in. `vpn-port-sync` keeps
that setting in place.

### arr: Radarr, Sonarr and Lidarr

[Managarr](https://github.com/Dark-Alex-17/managarr) browses the library, the queue, history
and the blocklist, and starts searches, without the web pages. `Tab` switches between the apps,
`?` shows the keys. It also works as a plain command, handy in scripts:

```bash
managarr radarr list movies
managarr sonarr list series
```

Its settings, `~/.config/managarr/config.yml`, hold API keys: keep it `chmod 600`.

### dock: every container

[lazydocker](https://github.com/jesseduffield/lazydocker) is the quickest answer to "is
something broken?": pick a container to see its live logs, CPU and memory; `r` restarts it and `s`
stops it. The same logs are in Dozzle in the browser ([Dashboards](../using/dashboards.md#dozzle)).

On a Raspberry Pi 5, use the released binary rather than a local build, which has a known display
bug there.

Restarting from here is a real restart: check that nothing is playing in Jellyfin first.

## What has no terminal tool

No maintained terminal interface exists for Prowlarr, Bazarr or Jellyfin; Managarr lists Prowlarr
and Bazarr as planned. Use their web pages, or Homepage for a summary
([Dashboards](../using/dashboards.md)).

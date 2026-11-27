# Sync an Obsidian vault

Each device keeps a local copy of the vault. Remotely Save exchanges edits with a shared WebDAV directory while Obsidian is open. A device on the server's tailnet connects directly. A desktop on another tailnet can use a local proxy that routes the server's DNS name through the correct tailnet.

## Start the service

On a Linux host with Docker Compose, Tailscale and `htpasswd`, run the following from the repository root. Choose a private directory outside the checkout. The commands below assume a new deployment.

```sh
export VAULT_SERVICE_ROOT="$HOME/.local/share/vault-sync"
export VAULT_HTTP_PORT=8087
export PUID="$(id -u)" PGID="$(id -g)"

umask 077
mkdir -p "$VAULT_SERVICE_ROOT/data"
touch "$VAULT_SERVICE_ROOT/htpasswd"
htpasswd -B "$VAULT_SERVICE_ROOT/htpasswd" notes
```

`htpasswd` prompts for the WebDAV password. Keep these environment settings in the host's private configuration for future Compose commands.

```sh
docker compose -f compose.obsidian.yml up -d
tailscale serve --bg --https=8443 "http://127.0.0.1:$VAULT_HTTP_PORT"
tailscale serve status
```

Choose an unused HTTPS port for Tailscale Serve. Copy the private HTTPS URL it prints. The service requires WebDAV credentials and listens on loopback. The Compose project can run independently of the media services. [Tailscale Serve](https://tailscale.com/kb/1242/tailscale-serve)

## Connect your devices

1. Back up each existing vault, including its hidden files. Compare copies and collect edits unique to each device. Disable other sync providers on the vault you will connect.
2. On the device with the complete vault, install and enable the **Remotely Save** community plugin. Choose **WebDAV**, enter the private HTTPS URL and the credentials you created, and choose a remote base directory for this vault. Enable sync for underscore-prefixed items if you use them.
3. Run the first sync and wait for it to finish. On each remaining device, start with an empty local vault, install the plugin and enter the same settings and remote base directory. Keep the app open for the first download.
4. Create a test note on one device, sync, then sync a second device and open the note. Edit it on the second device and repeat in reverse. Set each device's automatic sync interval after the round trip succeeds.

Sync before switching devices while editing the same note. The plugin's hidden-file settings control which Obsidian preferences and plugins travel between devices. [Remotely Save](https://github.com/remotely-save/remotely-save)

## Back up and recover a note

Deletions propagate to other clients. Schedule versioned backups of the private service directory to a separate disk and store the recovery key separately. For example, with a dedicated encrypted restic repository, point `RESTIC_REPOSITORY` and `RESTIC_PASSWORD_FILE` at that repository and its private password file. Initialize a new repository once with `restic init`.

```sh
restic backup --tag vault-sync "$VAULT_SERVICE_ROOT"
restic snapshots --tag vault-sync
```

Run the backup hourly with a timer. A retention policy of 24 hourly, 30 daily and 12 weekly snapshots provides multiple recovery points. Test recovery in a temporary directory.

```sh
restore_dir="$(mktemp -d)"
restic restore latest --tag vault-sync --target "$restore_dir"
```

Open the recovered note under `$restore_dir$VAULT_SERVICE_ROOT/data`. To publish a recovered version, copy it into one client vault under a new name, then sync and verify it on another device.

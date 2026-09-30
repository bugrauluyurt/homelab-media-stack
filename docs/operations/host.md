# Host setup

This page is for the owner: every change made to the server itself rather than to the containers,
why it is there, and how to put it back after reinstalling the operating system. `host-install`
applies most of them; the rest are a few manual steps, listed here with the command for each.

## What goes where

| Change | Why | Applied by | Checked by `stack-health` |
|---|---|---|---|
| [systemd units and the udev rule](#systemd-units-and-the-udev-rule) | Start the stack with the drive, run the timers | `host-install` (enable by hand) | Yes |
| [SSH: keys only, no root](#ssh-keys-only-no-root-login) | No password guessing | `host-install` | Yes |
| [SSH keys pinned with `from=`](#ssh-keys-pinned-to-where-they-are-used) | A leaked key is useless elsewhere | By hand | Yes |
| [Docker log rotation](#docker-log-rotation) | Logs can't fill the system disk | `host-install` (restart Docker by hand) | No |
| [rpcbind off](#rpcbind-off) | No NFS here, one service fewer | `host-install` | Yes |
| [mDNS on real interfaces only](#mdns-only-on-real-network-interfaces) | `<host>.local` never resolves to a Docker address | By hand | Yes |
| [Memory cgroup](#memory-cgroup-raspberry-pi-os) | Container memory limits work | By hand, Raspberry Pi OS only | Yes |
| [Media drive in fstab, immutable mount point](#the-media-drive) | The drive mounts in one place; nothing writes to the system disk in its place | By hand | Yes (mounted) |
| [Firewall](#firewall) | The home network reaches only what it should | `host-install` installs its units | Yes |
| [HTTPS for Needle](#https-for-needle-tailscale-serve) | Needle's only address, with a certificate | By hand (`tailscale serve`) | Needle answers |
| [Tailscale access policy](#tailscale-access-policy) | Who reaches which port | Tailscale's admin console | No |
| [Passwordless sudo, docker group](#prerequisites) | Timers run unattended | By hand; `host-install` checks | No |
| [Chrome new-tab extension](#chrome-new-tab-extension) | Glance on every new tab | On your computer | No |

The nightly backup keeps a copy of the hand-edited files (`/etc/fstab`,
`/boot/firmware/cmdline.txt`, `/etc/docker/daemon.json`, `/etc/avahi/avahi-daemon.conf` and
`~/.ssh/authorized_keys`), so after a reinstall you can take them from there
([Backups](../flows/backups.md)).

## After a reinstall

1. Install the prerequisites and run `host-install` ([below](#what-host-install-does)).
2. Enable the units, as in [Getting started](../getting-started.md#enable-the-timers).
3. Restart Docker once for log rotation: `sudo systemctl restart docker`.
4. Put back the manual changes: `authorized_keys` with its `from=` pins, the avahi interfaces, the
   memory cgroup on a Raspberry Pi, the fstab line and the immutable mount point.
5. Sign the server in to Tailscale again, re-apply `tag:media` in the admin console, and run the
   `tailscale serve` command for Needle.
6. Run `health` and fix anything it reports.

## What host-install does

```bash
scripts/host-install
```

It is safe to re-run. In order, it:

1. **Checks the prerequisites** and stops with the exact install command for anything missing:
   Docker with the compose and buildx plugins, restic, smartmontools, hdparm, lsof, iptables,
   Tailscale, avahi with mDNS name resolution, and Python 3.9 or newer. It prints `apt-get`
   package names on Debian and Ubuntu and `pacman` ones on Arch. Docker and Tailscale come from
   their own apt repositories on Debian and Ubuntu.
2. **Renders the templates** in `host/systemd/`, filling in `@REPO@`, `@STACK_USER@`, `@STACK_GROUP@`,
   `@STORAGE_UUID@`, `@STORAGE_MOUNT@` and `@STORAGE_UNIT@` from `.env`, and installs units to
   `/etc/systemd/system` and the udev rule to `/etc/udev/rules.d`. Without a `STORAGE_UUID` it
   skips (and removes) the udev rule: an always-mounted disk has nothing to hot-plug.
3. **Installs the SSH hardening** from `host/sshd_config.d/`, tests the configuration and reloads
   sshd.
4. **Installs Docker's log settings** from `host/docker/daemon.json` when they differ.
5. **Disables and masks rpcbind.**

It enables nothing: each unit needs `sudo systemctl enable --now <unit>` once.

## Prerequisites

The timers run `stack-health` and the firewall with `sudo`, unattended, so the stack's user needs
passwordless sudo and the docker group. `host-install` checks both and prints the fix:

```bash
echo '<user> ALL=(ALL) NOPASSWD: ALL' | sudo tee /etc/sudoers.d/homelab-media-stack
sudo usermod -aG docker <user>        # then log in again
```

That makes any SSH key for this account effectively root, which is why every key is
[pinned](#ssh-keys-pinned-to-where-they-are-used).

On Arch, after installing `nss-mdns`, add `mdns_minimal [NOTFOUND=return]` before `resolve` on
the `hosts` line of `/etc/nsswitch.conf`; `host-install` reminds you.

## systemd units and the udev rule

The units start the stack when the media drive mounts and stop it when the drive goes, and run
the timers: backups, update checks, the VPN port sync, the health check, the firewall, the
download throttle, activity alerts and the weekly YouTube sync. Every unit, timer and the boot
timeline are in [systemd reference](../reference/systemd.md); the drive and boot story is in
[Storage and boot](../flows/storage-and-boot.md).

```bash
systemctl list-timers 'arr-*'      # what runs when
```

## SSH: keys only, no root login

`host/sshd_config.d/10-arr-hardening.conf` sets `PasswordAuthentication no`,
`KbdInteractiveAuthentication no` and `PermitRootLogin no`. Its name sorts before
`50-cloud-init.conf`, which some images ship to turn passwords back on: sshd keeps the first value
it reads. If `host-install` warns that the hardening isn't active, your `sshd_config` lacks the
`Include /etc/ssh/sshd_config.d/*.conf` line at the top.

```bash
sudo sshd -T | grep -E 'passwordauthentication|permitrootlogin'
```

SSH answers on the tailnet only; the [firewall](#firewall) closes it to the home network. If
Tailscale is ever down, log in with a keyboard and screen.

## SSH keys pinned to where they are used

Every key in `~/.ssh/authorized_keys` carries a `from="..."` list, because any key is effectively
root here. The file is per machine and not in the repository:

```text
from="100.64.0.0/10,fd7a:115c:a1e0::/48" ssh-ed25519 AAAA... you@laptop
from="<agent's tailnet IPv4>,<its IPv6>",no-agent-forwarding,no-X11-forwarding ssh-ed25519 AAAA... agent
```

The first form accepts your key from any tailnet device (Tailscale's policy already limits port
22 to your own devices); the second limits another machine's key, such as an AI agent's, to that
machine alone. `stack-health` fails if any key has no `from=`.

## Docker log rotation

`host/docker/daemon.json` makes Docker keep at most three 10 MB log files per container, in its
compact `local` format:

```json
{"log-driver": "local", "log-opts": {"max-size": "10m", "max-file": "3"}}
```

Docker's default `json-file` logs never rotate; a container that logs a progress line every second
can grow its log by hundreds of megabytes. `docker-compose.yml` sets the same limits for every
stack service, so this file covers everything else on the machine. It takes effect after
`sudo systemctl restart docker` (which restarts every container), and only for containers created
afterwards.

## rpcbind off

`rpcbind` serves NFS, which the stack doesn't use, so `host-install` disables and masks it:
one listening service fewer. `stack-health` checks it stays off.

## mDNS only on real network interfaces

In `/etc/avahi/avahi-daemon.conf`, list only the wired and Wi-Fi interfaces (`eth0,wlan0` on a
Raspberry Pi; `ip -br link` shows yours):

```ini
allow-interfaces=eth0,wlan0
```

Without it, avahi advertises `<host>.local` on every interface, including Docker's bridges and one
`veth` link per container. Another device can then be handed a Docker-internal address it can't
reach, and connecting by name fails now and then.

```bash
sudo systemctl restart avahi-daemon
getent hosts <host>.local        # must show the home-network address, never 172.x
```

`stack-health` checks that `<host>.local` resolves inside `LAN_CIDR`.

## Memory cgroup (Raspberry Pi OS)

Raspberry Pi OS leaves the kernel's memory controller off, so Docker ignores every `mem_limit`.
Append this to the single line in `/boot/firmware/cmdline.txt`, then reboot:

```text
cgroup_memory=1 cgroup_enable=memory
```

Check with `cat /sys/fs/cgroup/cgroup.controllers`: it must list `memory`. Containers created
before the reboot keep running without a limit, because compose sees their configuration
unchanged; recreate them with `docker compose up -d --force-recreate`. `stack-health` checks both
the kernel and that every container has a limit. Other systems usually have the controller on
already; the same check tells you.

## The media drive

A drive switched on by hand is pinned by filesystem UUID in `/etc/fstab`, a hand edit
(`STORAGE_UUID` in `.env` holds the same UUID; `lsblk -f` shows it):

```text
UUID=<STORAGE_UUID>  /mnt/storage  ext4  defaults,noatime,nofail,x-systemd.device-timeout=60  0  2
```

`nofail` lets the server boot with the drive off, and the udev rule that `host-install` installs
mounts it when it is switched on. On a single-disk machine, bind-mount a folder at the mount point
instead (`/srv/media /mnt/storage none bind 0 0`) and leave `STORAGE_UUID` empty.

Then, with the drive **unmounted**, make the empty mount point immutable, once:

```bash
sudo chattr +i /mnt/storage
```

While the drive is off, nothing can then write into `/mnt/storage` and quietly fill the system disk
in its place. The stack adds two more guards: `arr-stack.service` refuses to start without the
mount, and the compose bind mounts refuse to create a missing media folder. Use your
`STORAGE_MOUNT` if it isn't `/mnt/storage`.

## Firewall

`scripts/host-firewall`, run by `arr-firewall.service` at boot and by `arr-firewall.timer` every 15
minutes, lets the home network reach only Jellyfin, Seerr and the games page, over IPv4 and IPv6,
including Docker's published ports. `host-install` installs the units; you enable them. The rules
and the reasoning are in [Security](../security.md).

```bash
sudo scripts/host-firewall status
```

## HTTPS for Needle (Tailscale Serve)

Needle, the music player, is served only at `https://<host>.<tailnet>.ts.net:4535`, with a
Tailscale certificate, on the tailnet only. Its container publishes 4535 on `127.0.0.1` alone, so
Tailscale Serve can take port 4535 on the tailnet addresses and HTTPS is the only way in. Port 443
stays free. Offline downloads, the phone home-screen app and Spotify need the HTTPS address.

```bash
sudo tailscale serve --bg --https=4535 http://127.0.0.1:4535
tailscale serve status
```

It survives reboots. Put the address in `.env` as `NEEDLE_PUBLIC_URL`; the Spotify app's redirect
URI is `<NEEDLE_PUBLIC_URL>/api/spotify/callback`. Your devices, and viewers', need port 4535 on
`tag:media` in the access policy (below). `sudo tailscale serve --https=4535 off` removes it.

## Tailscale access policy

This lives in Tailscale, not on the server: the admin console's **Access controls** (JSON editor)
enforces it. The reference copy, with placeholder e-mail addresses, is
[`host/tailscale-policy.hujson`](https://github.com/bugrauluyurt/homelab-media-stack/blob/main/host/tailscale-policy.hujson):

- **You** reach everything on every device you sign in to.
- **Viewers** (members listed in `group:viewers`) reach only Jellyfin (8096), Seerr (5055),
  Questarr (5000), the games page (8090), SFTP (2022) and Needle (4535) on the server, and none of
  your other devices.
- **The server is tagged `tag:media`**, so it belongs to the tag rather than to a person: it may
  start no connections to anyone's devices, and its key doesn't expire.

Never put back Tailscale's default allow-all grant (`"src": ["*"], "dst": ["*"]`): rules only ever
add access, so it would cancel all of the above. The file carries `tests` that the console runs
when you save.

After a reinstall, sign the server in to Tailscale again and re-apply the tag: **Machines → the
server → ... → Edit ACL tags → `tag:media`**. Adding a viewer is in [Viewers](../flows/viewers.md).

## Chrome new-tab extension

`host/chrome-new-tab/` is a tiny Chrome extension, for your computer rather than the server, that
opens Glance's Lab page in every new tab with the cursor in its search box. It asks for no
permissions. Chrome keeps the cursor in the address bar on an extension's new-tab page, so
`newtab.js` opens Lab as a fresh tab in the same spot and closes the blank one.

1. Copy the folder to your computer, for example `scp -r <host>:homelab-media-stack/host/chrome-new-tab ~/`.
2. In `newtab.js`, replace `YOUR_HOSTNAME` with the server's name (or its Tailscale address).
3. In Chrome, open `chrome://extensions`, switch on **Developer mode** (top right), press **Load
   unpacked** and pick the folder.
4. When Chrome asks whether to keep the changed new-tab page, choose **Keep it**.

To change the address later, edit `newtab.js` and press the reload arrow on the extension's card.

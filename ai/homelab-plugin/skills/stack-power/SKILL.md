---
name: stack-power
description: Safely stop the media stack and unmount the media drive before it is powered off or unplugged, or bring the stack back up; check the UPS and run its power-cut tests. Use only when the user explicitly asks to turn off, unplug or restart the drive or the whole stack, or asks about the UPS, a power cut or a UPS test.
---

# Stopping and starting the stack

This interrupts everything: playback, downloads and requests. **Get the user's
explicit yes first**, and check that nothing is playing (see the `stack-update`
skill for the Jellyfin sessions check).

```bash
STACK=${MEDIA_STACK_DIR:-$(git rev-parse --show-toplevel 2>/dev/null)}; [ -x "$STACK/scripts/stack-health" ] || STACK=~/homelab-media-stack
```

## Power the drive off safely

```bash
"$STACK/scripts/drive-off"
```

This stops the stack, flushes writes and unmounts the media mount (`STORAGE_MOUNT` in `.env`, default `/mnt/storage`). Only then is it
safe to cut the enclosure's power.

A backup drive (`BACKUP_UUID` set, mounted at `BACKUP_MOUNT`, default `/mnt/backup`) is read-only
between mirrors and needs no unmount when only the media drive is powered off. If both drives
share a dock that is being switched off, also stop the mirror and unmount it:

```bash
sudo systemctl stop arr-mirror.service
sudo umount /mnt/backup        # BACKUP_MOUNT
```

## Bring it back

Power the drive on and it mounts by its UUID; `arr-stack.service` then starts the
stack on its own. To start it by hand:

```bash
sudo systemctl start arr-stack.service     # or: "$STACK/scripts/stack-up"
```

`stack-up` refuses to start without the drive, re-attaches qBittorrent and
slskd to the VPN, and syncs the forwarded port. Afterwards, run `stack-health`.

## UPS (only where `/etc/apcupsd/apcupsd.conf` exists)

Status and history are safe to read:

```bash
/usr/sbin/apcaccess status               # STATUS ONLINE, ONBATT or COMMLOST; BCHARGE, TIMELEFT, MBATTCHG, MINTIMEL
tail -20 /var/log/apcupsd.events         # power events with their times
systemctl is-active apcupsd; systemctl list-timers arr-ups-metrics.timer --no-pager
```

At 10% charge or 5 minutes left, apcupsd shuts the server down, the UPS cuts its outlets, and
the server boots by itself when mains returns. `COMMLOST` means a power cut would not shut it
down: check the USB cable and that `DEVICE` is empty in `/etc/apcupsd/apcupsd.conf`.
`docs/flows/power.md` has the whole sequence.

The tests cut power. **Ask first, every time**, and check that nothing is playing:

- **Short test:** the user unplugs the UPS from the wall for 60 seconds. Expect "on battery" and
  "power restored" pushes and everything staying up.
- **Full test (shuts the server down):** set `BATTERYLEVEL 95` in `/etc/apcupsd/apcupsd.conf`,
  `sudo systemctl restart apcupsd`, then the user unplugs the UPS. Expect a clean shutdown and the
  UPS output going off; plugged back in, the server boots. Afterwards check `journalctl -b -1`,
  run `"$STACK/scripts/host-install"` to put `BATTERYLEVEL 10` back, and
  `sudo systemctl restart apcupsd`. If you run on the server, your session ends with the shutdown:
  tell the user these follow-up steps first.

## Rebooting the server

Everything comes back automatically: the drive mounts, Docker and Tailscale
start, and `arr-stack.service` brings the stack up. If you are an agent running
on the server, your session ends with the reboot, so tell the user to run
`stack-health` once it's back up.

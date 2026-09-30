---
name: stack-power
description: Safely stop the media stack and unmount the media drive before it is powered off or unplugged, or bring the stack back up. Use only when the user explicitly asks to turn off, unplug or restart the drive or the whole stack.
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

## Bring it back

Power the drive on and it mounts by its UUID; `arr-stack.service` then starts the
stack on its own. To start it by hand:

```bash
sudo systemctl start arr-stack.service     # or: "$STACK/scripts/stack-up"
```

`stack-up` refuses to start without the drive, re-attaches qBittorrent and
slskd to the VPN, and syncs the forwarded port. Afterwards, run `stack-health`.

## Rebooting the server

Everything comes back automatically: the drive mounts, Docker and Tailscale
start, and `arr-stack.service` brings the stack up. If you are an agent running
on the server, your session ends with the reboot, so tell the user to run
`stack-health` once it's back up.

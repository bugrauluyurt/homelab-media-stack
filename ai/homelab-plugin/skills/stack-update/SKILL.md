---
name: stack-update
description: Check for and apply Docker image updates to the media stack safely, with a settings snapshot first and rollback if something breaks. Use only when the user explicitly asks to check for updates, update services, or roll back an update.
---

# Updating the stack

This changes the running system. Checking is safe. **Applying an update or a
rollback needs the user's explicit yes, every time.** Before running anything,
show what will change (which services, which images).

```bash
STACK=${MEDIA_STACK_DIR:-$(git rev-parse --show-toplevel 2>/dev/null)}; [ -x "$STACK/scripts/stack-health" ] || STACK=~/homelab-media-stack
```

## 1. See what's available (safe)

```bash
"$STACK/scripts/stack-update-check"      # about 1-2 minutes; also refreshes the list stack-health shows
```

It lists `update available: <image>  <old> -> <new>`. When the first number of
the version changes (a major release), say so: those are the updates that
break things. A daily timer runs it at 06:00 and pushes new updates to the
user's phone through ntfy, with major releases flagged `MAJOR`.

## 2. Apply (only after the user says yes)

```bash
"$STACK/scripts/stack-update"                  # every service with an update
"$STACK/scripts/stack-update jellyfin sonarr"  # or named services
```

It does four things in order:
1. Takes a restic snapshot tagged `pre-update`. If that fails, it stops and updates nothing.
2. Keeps the current images as `<image>:rollback-<date>`.
3. Pulls and recreates only those services. qBittorrent and slskd follow gluetun automatically.
4. Runs `stack-health`. After a Jellyfin update, the health check also confirms that every
plugin is still Active; a plugin built for an older Jellyfin shows up as a FAIL.

Jellyfin updates are the risky ones: Jellyfin 12 once broke logins in four other
apps at once. Mention that when Jellyfin is in the list, and check that nothing is
playing first:

```bash
K=$(sed -nE "s/^JELLYFIN_API_KEY=(['\"]?)(.*)\1$/\2/p" "$STACK/.env")
curl -s -H "Authorization: MediaBrowser Token=\"$K\"" http://127.0.0.1:8096/Sessions | python3 -c 'import json,sys;print([s.get("Client") for s in json.load(sys.stdin) if s.get("NowPlayingItem")] or "nothing playing")'
```

## 3. Roll back (only after the user says yes)

```bash
"$STACK/scripts/stack-update" --rollback <service>               # previous image AND its settings
"$STACK/scripts/stack-update" --rollback <service> --image-only  # previous image, current settings
```

The default restores settings, because updates often migrate the app's database
and the older version can't read a migrated one. It discards anything changed in
that app since the update, so say so before running it. Only use `--image-only`
when you know the update didn't change the database.

## After
Report what was updated, the stack-health summary, and the rollback command.

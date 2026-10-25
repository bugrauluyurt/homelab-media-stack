---
name: stack-backup
description: Check, run or restore the media stack's settings backups (restic snapshots of app configs and databases) and the optional nightly mirror of the whole media drive onto a backup drive. Use when asked whether backups or the mirror are working, to take a backup or mirror now, to list snapshots, to restore an app's settings, or to get back a deleted media file.
---

# Settings backups

Backups cover every app's settings and databases, the Jellystat dump, `.env`,
a few home-folder configs and the hand-edited host files (fstab, cmdline.txt,
Docker's daemon.json, Avahi, authorized_keys). **restic never backs up media;** it can be re-downloaded.
With a backup drive (`BACKUP_UUID` set in `.env`), a nightly mirror copies the whole media drive,
media included (see Media mirror below).
The restic repository is at `$STORAGE_MOUNT/backups/restic` (`STORAGE_MOUNT` in `.env`, default
`/mnt/storage`), on the media drive. Its password is in the root-only file
`$STORAGE_MOUNT/backups/RESTIC_PASSWORD` (and in `.env`), and the user keeps a copy off the server. Always pass it with `--password-file`, never on the command line,
where `ps` would show it.
Each run then copies the snapshots to a second repository on the system disk,
`/var/backups/arr-stack/restic` (same password), which keeps the history if the
media drive dies. `docs/flows/backups.md` has the full picture.

```bash
STACK=${MEDIA_STACK_DIR:-$(git rev-parse --show-toplevel 2>/dev/null)}; [ -x "$STACK/scripts/stack-health" ] || STACK=~/homelab-media-stack
```

## Status (safe)

```bash
cat /var/lib/arr-backup/last-success                      # last successful nightly run
systemctl list-timers arr-backup.timer --no-pager
sudo restic -r $STORAGE_MOUNT/backups/restic --password-file $STORAGE_MOUNT/backups/RESTIC_PASSWORD snapshots --compact | tail -12
```

The timer runs nightly at 04:30, and only while the drive is mounted. What's kept:
7 daily, 4 weekly and 6 monthly snapshots, plus the last 5 tagged `pre-update`,
which are kept outside that thinning. On Sundays the run also does
`restic check --read-data-subset=5%` on both repositories. If `RESTIC_OFFSITE_REPO` is set in `.env`
(B2 or S3-compatible, credentials beside it), every nightly run then copies the
snapshots there with `restic copy`; a failure in either shows in the unit's log
(`journalctl -u arr-backup`) and is pushed to ntfy.

## Take one now (safe, about a minute)

```bash
sudo "$STACK/scripts/stack-backup"            # or with a tag: stack-backup pre-change
```

It prints `snapshot <id>` at the end.

## Restore (only when the user explicitly asks, and after they say yes)

- **An app changed by `stack-update`:** `"$STACK/scripts/stack-update" --rollback <service>` (restores its settings too)
- **Anything else:** restore into a temporary folder and show the user what differs
  before copying anything into `$CONFIG_ROOT`:
  ```bash
  sudo restic -r $STORAGE_MOUNT/backups/restic --password-file $STORAGE_MOUNT/backups/RESTIC_PASSWORD restore <id> --include /var/tmp/arr-backup/config/<app> --target /tmp/restore
  ```
  Stop the app before copying. Delete any `*.db-wal` and `*.db-shm` files next to
  restored databases, then `chown` to match the original folder's owner.

## Media mirror

Only when `BACKUP_UUID` is set in `.env`. `storage-mirror` copies the whole media drive onto the
backup drive at `BACKUP_MOUNT` (default `/mnt/backup`) daily at 05:30, after the settings backup,
with hardlinks kept. Files deleted or overwritten since the last run move to
`$BACKUP_MOUNT/.trash/<YYYY-MM-DD>/` (the night the mirror noticed) and stay 30 days. The backup
drive is mounted read-only between runs, and sleeps after 10 idle minutes (`arr-spindown.service`);
the mirror wakes it. After each copy, while the drive is awake, the run has Scrutiny read the
drives and checks the backup drive's SMART health, bad sectors and temperature.

### Status (safe)

```bash
systemctl status arr-mirror.service --no-pager          # last run and its result
journalctl -u arr-mirror --no-pager | tail -30           # rsync's summary, or the FATAL reason
systemctl list-timers arr-mirror.timer --no-pager
STATE=$(dirname "$(sed -n 's/^CONFIG_ROOT=//p' "$STACK/.env")")/state
echo "$(( ($(date +%s) - $(awk '{print $2}' "$STATE/metrics/mirror.prom")) / 3600 )) h since the last mirror"
```

`stack-health` fails once the last mirror is 48 hours old and none is running; a run that hangs
fails by itself after 24 hours. A `FATAL` line means a guard stopped
it: the backup drive not mounted, a UUID that doesn't match `.env`, or an empty `DATA_ROOT`.
`FATAL: the backup drive failed its SMART <check> check` comes after the copy instead: the copy
and its success metric are fine, but the drive needs attention (the `drive-health` skill).

### Mirror now (ask first: it can run for hours)

```bash
sudo "$STACK/scripts/storage-mirror" --dry-run | tail -40   # what would change, touches nothing
sudo systemctl start --no-block arr-mirror.service          # then follow: journalctl -fu arr-mirror
```

### Restore media files (only when the user explicitly asks, and after they say yes)

Show the user what you would copy first. The backup drive is read-only, so copy back with
`sudo`, keeping owners:

```bash
sudo cp -a "$BACKUP_MOUNT/<path under the drive>" "$STORAGE_MOUNT/<same path's parent>/"    # as of the last mirror
ls "$BACKUP_MOUNT/.trash/"                                                              # deleted or replaced: find the night
sudo rsync -aH "$BACKUP_MOUNT/.trash/<date>/<path>/" "$STORAGE_MOUNT/<path>/"
```

Never write into `$BACKUP_MOUNT` and never remount it read-write by hand.

Never print the restic password.

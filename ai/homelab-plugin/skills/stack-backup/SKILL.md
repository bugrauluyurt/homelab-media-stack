---
name: stack-backup
description: Check, run or restore the media stack's settings backups (restic snapshots of app configs and databases, never media). Use when asked whether backups are working, to take a backup now, to list snapshots, or to restore an app's settings.
---

# Settings backups

Backups cover every app's settings and databases, the Jellystat dump, `.env`,
a few home-folder configs and the hand-edited host files (fstab, cmdline.txt,
Docker's daemon.json, Avahi, authorized_keys). **Media is never backed up;** it can be re-downloaded.
The restic repository is at `$STORAGE_MOUNT/backups/restic` (`STORAGE_MOUNT` in `.env`, default
`/mnt/storage`), on the media drive. Its password is in the root-only file
`$STORAGE_MOUNT/backups/RESTIC_PASSWORD` (and in `.env`), and the user keeps a copy off the server. Always pass it with `--password-file`, never on the command line,
where `ps` would show it.
Each run then copies the snapshots to a second repository on the system disk,
`/var/backups/arr-stack/restic` (same password), which keeps the history if the
media drive dies. `docs/flows/backups.md` has the full picture.

```bash
STACK=${MEDIA_STACK_DIR:-$(git rev-parse --show-toplevel 2>/dev/null)}; [ -x "$STACK/scripts/health-check" ] || STACK=~/homelab-media-stack
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
sudo "$STACK/scripts/backup-config"            # or with a tag: backup-config pre-change
```

It prints `snapshot <id>` at the end.

## Restore (only when the user explicitly asks, and after they say yes)

- **An app changed by `update`:** `"$STACK/scripts/update" --rollback <service>` (restores its settings too)
- **Anything else:** restore into a temporary folder and show the user what differs
  before copying anything into `$CONFIG_ROOT`:
  ```bash
  sudo restic -r $STORAGE_MOUNT/backups/restic --password-file $STORAGE_MOUNT/backups/RESTIC_PASSWORD restore <id> --include /var/tmp/arr-backup/config/<app> --target /tmp/restore
  ```
  Stop the app before copying. Delete any `*.db-wal` and `*.db-shm` files next to
  restored databases, then `chown` to match the original folder's owner.

Never print the restic password.

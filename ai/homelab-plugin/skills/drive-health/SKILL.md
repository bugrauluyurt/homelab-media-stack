---
name: drive-health
description: Check the SMART health, temperature and, in a USB enclosure, the link of the media drive and of the backup drive when there is one. Use when asked about the hard drives, disk failure risk, disk temperature, or slow disk performance.
---

# Drive health

Read-only. The media drive is mounted at `STORAGE_MOUNT` (`.env`, default `/mnt/storage`). With
`BACKUP_UUID` set there is a second drive, the backup drive, at `BACKUP_MOUNT` (default
`/mnt/backup`, read-only); check it the same way with `MOUNT` set to that path. `smartctl` needs
`sudo`. A drive in a USB enclosure needs `-d sat`; internal SATA and NVMe drives don't.

With two USB drives, `/dev/sda` and `/dev/sdb` can swap at boot, so name a disk by its stable
path when you check it directly:

```bash
ls -l /dev/disk/by-id/ | grep -v part
sudo smartctl -a -d sat /dev/disk/by-id/<disk>
```

`stack-health` checks SMART health, bad sectors and temperature on both drives.

```bash
STACK=${MEDIA_STACK_DIR:-$(git rev-parse --show-toplevel 2>/dev/null)}; [ -x "$STACK/scripts/stack-health" ] || STACK=~/homelab-media-stack
MOUNT=$(sed -n 's/^STORAGE_MOUNT=//p' "$STACK/.env"); MOUNT=${MOUNT:-/mnt/storage}
SOURCE=$(findmnt -no SOURCE "$MOUNT" | sed 's/\[.*//')
PARENT=$(lsblk -no PKNAME "$SOURCE" | head -1)
DEV=/dev/${PARENT:-${SOURCE#/dev/}}
TYPE=$([ "$(lsblk -dno TRAN "$DEV")" = usb ] && echo "-d sat")
sudo smartctl $TYPE -H "$DEV"
sudo smartctl $TYPE -A "$DEV" | grep -iE 'temp|realloc|pending|uncorr|crc|power_on|start_stop|media_err|percent'
[ -n "$TYPE" ] && cat "/sys/block/${DEV#/dev/}/device/../../../../speed" 2>/dev/null
sudo journalctl -k --since '-7 days' --no-pager | grep -ciE 'uas.*(abort|reset)|reset SuperSpeed|USB disconnect|I/O error'
```

The USB link speed line prints the enclosure's negotiated speed in Mbps (5000 is USB 3); it is
empty for internal drives.

Scrutiny (`http://<host>:3006`, `curl -s localhost:3006/api/summary`) keeps the
same attributes as history, collected every hour, so a trend is visible without sudo. It has the
backup drive too only with the `compose.backup-drive.yml` override on.

With `arr-drive-metrics.timer` enabled, each drive's temperature is read every minute, without
waking a sleeping drive: Grafana's Media Server: Overview dashboard has it in the Drive
temperatures panel, Glance's Lab page in the Drives block, and the file itself needs no sudo:

```bash
STATE=$(dirname "$(sed -n 's/^CONFIG_ROOT=//p' "$STACK/.env")")/state
cat "$STATE/metrics/drives.prom"    # arr_drive_temperature_celsius{drive="media"} 41
```

A drive missing from the file is unmounted or asleep.

## Reading it

- **These rising above 0 means failure is approaching:** `Reallocated_Sector_Ct`,
  `Current_Pending_Sector`, `Offline_Uncorrectable`. If you see that, recommend
  replacing the drive calmly.
- **`UDMA_CRC_Error_Count` rising** points to the cable or enclosure, not the disk.
- **Temperature:** under 50 °C is comfortable, 55 °C or more deserves attention,
  and the rated limit is 70 °C.
- **Ignore the large raw values** of `Raw_Read_Error_Rate` and `Seek_Error_Rate`.
  On Seagate they are packed counters; compare the normalized value with the threshold instead.
- **If performance is slow,** check whether qBittorrent is busy before blaming USB.
  Many simultaneous downloads saturate the disk (look at the `%util`-style busy
  figure in `/proc/diskstats`).

If the media drive dies, only media is lost, and that can be re-downloaded; with a backup drive
it holds last night's copy, which can take the media drive's place (`docs/flows/backups.md`).
Settings live on the system disk and are backed up nightly to the media drive.

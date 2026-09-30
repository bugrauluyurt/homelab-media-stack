---
name: drive-health
description: Check the media drive's SMART health, temperature and, in a USB enclosure, its link. Use when asked about the hard drive, disk failure risk, disk temperature, or slow disk performance.
---

# Media drive health

Read-only. The media drive is mounted at `STORAGE_MOUNT` (`.env`, default `/mnt/storage`); `smartctl` needs `sudo`.
A drive in a USB enclosure needs `-d sat`; internal SATA and NVMe drives don't.

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
same attributes as history, so a trend is visible without sudo.

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

If the drive dies, only media is lost, and that can be re-downloaded. Settings live on the
system disk and are backed up nightly to this drive.

- A second drive can now hold a nightly copy of the whole media drive: set `BACKUP_UUID` and
  `storage-mirror` mirrors it at 05:30 with hardlinks kept, read-only between runs, and keeps
  deleted or replaced files in a dated trash for 30 days. `stack-health`, Glance and ntfy watch it.
- An APC UPS on USB now shuts the server down cleanly near the end of its battery (5 minutes or
  10% left) and powers it back on when mains returns: install apcupsd and rerun `host-install`.
  Power events push to ntfy, and a new Grafana dashboard and a Glance line show the UPS readings.

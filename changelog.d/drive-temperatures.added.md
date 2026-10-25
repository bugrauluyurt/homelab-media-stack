- Drive temperatures are visible live: `drive-metrics` reads both drives every minute without waking
  a sleeping one, for a new "Drive temperatures" graph in Grafana and a "Drives" block in Glance.
  Scrutiny now collects hourly, and `compose.backup-drive.yml` adds the backup drive to it.

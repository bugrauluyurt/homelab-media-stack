- Glance's YouTube rows show videos again. YouTube's RSS feed answers 404 for hours at a time, so
  `sync-youtube.py` now fetches the latest uploads hourly, through the Data API once you are signed
  in, and keeps a channel's last videos when it can't be read. `arr-youtube.timer` runs hourly
  instead of weekly; rerun `install-host` to pick up the new schedule.

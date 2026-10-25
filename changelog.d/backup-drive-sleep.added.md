- The backup drive now spins down after 10 idle minutes (`arr-spindown.service`, run each time it
  mounts), so it no longer heats the dock around the clock. `stack-health` and Scrutiny leave a
  sleeping drive asleep, and `storage-mirror` reads its SMART health and Scrutiny history after each
  nightly copy while it is awake, alerting when a check fails.

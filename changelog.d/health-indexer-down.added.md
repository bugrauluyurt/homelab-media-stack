- `stack-health` now fails when Prowlarr reports an indexer down for more than 6 hours and names it,
  so the six-hourly check pushes it to ntfy. Before, one dead indexer stayed silent while others worked.

- `scripts/check` passes on a Raspberry Pi 5. ruff's arm64 build crashes on its 16 KiB-page
  kernel, so the check skips ruff there and says so; CI still runs it.

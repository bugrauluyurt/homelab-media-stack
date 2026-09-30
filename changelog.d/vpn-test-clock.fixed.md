- VPN recovery tests now use a controlled clock and boot time, so release checks also pass
  on freshly booted CI runners. Regression coverage preserves the production reboot safeguard
  and verifies the recovery delay and restart cooldown without changing runtime behavior.
- Agent instructions now explicitly require focused tests, full source checks, regression
  coverage and accurate validation results before handing off changes or opening/updating PRs.

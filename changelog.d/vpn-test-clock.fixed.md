- VPN recovery tests now use a controlled clock and boot time, so release checks also pass
  on freshly booted CI runners. Regression coverage preserves the production reboot safeguard
  and verifies the recovery delay and restart cooldown without changing runtime behavior.

# Host files

Files for the machines themselves, outside Docker. `scripts/host-install` installs the first two:

- `systemd/`: the unit, timer and udev templates, filled in from `.env` and installed into
  `/etc/systemd/system` and `/etc/udev/rules.d`. Each one has an entry in
  [docs/reference/systemd.md](../docs/reference/systemd.md).
- `sshd_config.d/` and `docker/`: SSH hardening and Docker's daemon defaults.

The rest you apply by hand:

- `tailscale-policy.hujson`: the reference Tailscale policy.
- `chrome-new-tab/`: a Chrome extension for your own computer that opens Glance on every new tab.

What each change does, and how to re-apply the manual ones, is in
[docs/operations/host.md](../docs/operations/host.md).

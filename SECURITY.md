# Security

Please report security problems privately: open the repository's **Security** tab and choose
**Report a vulnerability**. Don't open a public issue for them.

Include what you found, how to reproduce it, and which release or commit you ran. You'll get a
reply within a week.

## Scope

This repository is the configuration and scripts around the apps: the firewall, the VPN
confinement of torrents and Soulseek, the Tailscale access model, SFTPGo's read-only setup, the
socket proxy, the backup and update scripts, and the AI agent. A flaw in one of the apps
themselves (Jellyfin, the *arr apps, qBittorrent and the others) belongs with that project;
tell us too if this stack's configuration makes it worse. How the pieces are meant to protect
each other is in [docs/security.md](docs/security.md).

## Verifying what you run

Releases are immutable and signed by GitHub:

```bash
gh release verify v2.0.0 -R bugrauluyurt/homelab-media-stack
```

Needle, the music player the stack pulls, publishes its images with build provenance:

```bash
gh attestation verify oci://ghcr.io/bugrauluyurt/needle:1 --owner bugrauluyurt
```

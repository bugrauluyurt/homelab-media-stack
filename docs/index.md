# homelab-media-stack

A self-hosted media server managed as code. It runs on a Raspberry Pi 5 or any x86-64
machine with Debian, Ubuntu or Arch, and turns a request for a movie, a show, an album or a
game into a file on your own disk: searched automatically, downloaded from Usenet or (inside a
VPN) from torrents, and played in Jellyfin, Needle or a PC. Your home network sees three apps;
everything else stays behind Tailscale.

These pages explain how to install it, how it works, and how to run it day to day.

## Where to start

- **Installing it?** [Getting started](getting-started.md) goes from a bare machine to a
  healthy stack.
- **Want to understand it first?** [Architecture](architecture.md) shows the containers,
  networks, storage and the reasons behind them.
- **Deciding whether to trust it?** [Security](security.md) covers the threat model and who
  can reach what.
- **Just using it?** [Requesting](using/requesting.md) explains how to ask for a movie or
  show and what happens next.
- **Something is wrong?** [Troubleshooting](troubleshooting.md) explains how to diagnose and
  lists problems already solved.

The source, releases and issue tracker are on
[GitHub](https://github.com/bugrauluyurt/homelab-media-stack).

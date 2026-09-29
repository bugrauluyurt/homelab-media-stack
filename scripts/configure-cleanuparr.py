#!/usr/bin/env python3
"""Configure Cleanuparr: stalled, failed and fake/malicious downloads.

Idempotent. Pass --dry-run to leave (or put) it in dry-run mode, where every
destructive action is skipped and only logged; without it, it ends live.
"""
import copy
import sys

from stack_env import ENV, arr_key, http

B = "http://127.0.0.1:11011/api"
# Not the stricter `blacklist`: it matches *.srt / *.sub / *.idx and would strip subtitle files.
BLOCKLIST = "https://cleanuparr.pages.dev/static/blacklist_permissive"
LIVE = "--dry-run" not in sys.argv


def raw(path, body=None, method=None, tok=None):
    # A bodiless POST is sent without Content-Length, which Cleanuparr rejects.
    if method == "POST" and body is None:
        body = {}

    return http(B + path, body, method, {"Authorization": f"Bearer {tok}"} if tok else None, timeout=30)


def ensure(path, label, change):
    cur = call(path)
    new = copy.deepcopy(cur)
    change(new)

    if new == cur:
        print(f"  = {label}")
        return

    call(path, new, "PUT")
    print(f"  + {label}")


def general(dry_run):
    def change(g):
        g["dryRun"] = dry_run
        # Game releases legitimately ship .exe files and archives, which the malware list would strip.
        g["ignoredDownloads"] = sorted(set(g["ignoredDownloads"]) | {"games"})

    ensure("/configuration/general", f"general ({'dry-run' if dry_run else 'live'}, games ignored)", change)


def malware(m):
    m.update({"enabled": True, "deleteIfAnyFileBlocked": False})

    for app in ("sonarr", "radarr"):
        m[app].update({"enabled": True, "blocklistType": "Blacklist", "blocklistPath": BLOCKLIST})


def queue(q):
    q["enabled"] = True
    # Exclude + no patterns = every failed import counts.
    q["failedImport"].update({"maxStrikes": 3, "patternMode": "Exclude", "patterns": []})
    q["downloadingMetadataMaxStrikes"] = 3


pw = ENV["CLEANUPARR_PASSWORD"]
if not raw("/auth/status").get("setupCompleted"):
    raw("/auth/setup/account", {"Username": "admin", "Password": pw})
    raw("/auth/setup/complete", method="POST")
    print("  + created admin account")

tok = raw("/auth/login", {"username": "admin", "password": pw})["tokens"]["accessToken"]


def call(path, body=None, method=None):
    return raw(path, body, method, tok)


ARRS = (("sonarr", 8989, 4), ("radarr", 7878, 6))
clients_missing = not call("/configuration/download_client")["clients"]
arrs_missing = [a for a in ARRS if not call(f"/configuration/{a[0]}").get("instances")]

# Dry-run before anything is connected, so nothing can act mid-setup.
if clients_missing or arrs_missing:
    general(True)

if clients_missing:
    call("/configuration/download_client", {
        "Enabled": True, "Name": "qBittorrent", "TypeName": "qBittorrent", "Type": "Torrent",
        "Host": f"http://gluetun:{ENV['QBIT_PORT']}", "Username": "", "Password": "", "UrlBase": ""})
    print("  + qBittorrent")

for app, port, ver in arrs_missing:
    call(f"/configuration/{app}/instances", {
        "Enabled": True, "Name": app.capitalize(), "Url": f"http://{app}:{port}",
        "ApiKey": arr_key(app), "Version": ver})
    print(f"  + {app}")

ensure("/configuration/malware_blocker", "malware blocker", malware)
ensure("/configuration/queue_cleaner", "queue cleaner", queue)

if not call("/queue-rules/stall"):
    call("/queue-rules/stall", {
        "Name": "Stalled for ~1 hour", "Enabled": True, "MaxStrikes": 12,
        "PrivacyType": "Public", "MinCompletionPercentage": 0, "MaxCompletionPercentage": 100,
        "ResetStrikesOnProgress": True, "DeletePrivateTorrentsFromClient": False,
        "ChangeCategory": False})
    print("  + stall rule")
else:
    print("  = stall rule")

if call("/configuration/download_cleaner")["enabled"]:
    sys.exit("download cleaner is enabled - refusing to go live")

general(not LIVE)

#!/usr/bin/env python3
"""Complete Jellyfin's startup wizard and add the Movies/TV libraries.

Runs: by hand, once, after the stack's first start and before the other configure scripts.
Changes: Jellyfin's startup API.
Idempotent: yes; it exits at once when the wizard is already complete.

Takes the admin account from JELLYFIN_USER / JELLYFIN_PASSWORD in .env. Safe
to re-run: exits early if the wizard is already done.
"""
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

from stack_env import ENV

BASE = "http://127.0.0.1:8096"
USER = ENV.get("JELLYFIN_USER", "admin")
PW = ENV.get("JELLYFIN_PASSWORD") or sys.exit("set JELLYFIN_PASSWORD in .env")


def req(path, body=None, method=None, ctype="application/json"):
    data = None
    if body is not None:
        data = json.dumps(body).encode() if ctype == "application/json" else body.encode()

    r = urllib.request.Request(BASE + path, data=data,
                               method=method or ("POST" if data else "GET"),
                               headers={"Content-Type": ctype})

    with urllib.request.urlopen(r, timeout=60) as resp:
        raw = resp.read()
        return json.loads(raw) if raw else None


if req("/System/Info/Public")["StartupWizardCompleted"]:
    print("  = startup wizard already completed")
    sys.exit(0)

req("/Startup/Configuration", {"UICulture": "en-US", "MetadataCountryCode": "US",
                               "PreferredMetadataLanguage": "en"})

# Jellyfin 12 creates the first user only when the wizard reads it; the POST then names it.
req("/Startup/User")

try:
    req("/Startup/User", {"Name": USER, "Password": PW})
    print(f"  + created admin user '{USER}'")
except urllib.error.HTTPError as e:
    # 403 means the admin already exists from a previous partial run.
    if e.code != 403:
        raise

    print("  = admin user already exists")

for name, coll, path in (("Movies", "movies", "/data/media/movies"),
                         ("TV Shows", "tvshows", "/data/media/tv")):
    q = urllib.parse.urlencode({"name": name, "collectionType": coll,
                                "refreshLibrary": "false"})

    try:
        req(f"/Library/VirtualFolders?{q}",
            {"LibraryOptions": {"PathInfos": [{"Path": path}],
                                "EnableRealtimeMonitor": False,
                                "EnableChapterImageExtraction": False}})
        print(f"  + added library {name} -> {path}")
    except urllib.error.HTTPError as e:
        print(f"  ! library {name}: HTTP {e.code} {e.read().decode()[:120]}")

req("/Startup/Complete", {})
print("  + startup wizard completed")

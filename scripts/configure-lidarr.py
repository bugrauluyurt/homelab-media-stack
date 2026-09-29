#!/usr/bin/env python3
"""Music: give Lidarr its Soulseek source and Navidrome its admin user.

Installs the Tubifarry plugin (Lidarr's plugins branch), then adds slskd as
both indexer and download client. Root folder, hardlinks, qBittorrent and the
Prowlarr link come from configure-arr.py. Idempotent.
"""
import json
import subprocess
import sys
import time

from stack_env import ENV, arr_key, http, require_service, wait_ready

require_service("lidarr")

LIDARR = "http://127.0.0.1:8686/api/v1"
NAVIDROME = "http://127.0.0.1:4533"
PLUGIN = "https://github.com/TypNull/Tubifarry"
SLSKD = {"baseUrl": "http://gluetun:5030", "apiKey": ENV["SLSKD_API_KEY"]}
MUSIC_PATH = "/data/torrents/music"


def lidarr(path, body=None, method=None):
    return http(LIDARR + path, body, method, {"X-Api-Key": arr_key("lidarr")})


def wait_for_lidarr():
    wait_ready(f"{LIDARR}/system/status", "Lidarr", headers={"X-Api-Key": arr_key("lidarr")})


def qbit(path, *args):
    return subprocess.run(["docker", "exec", "qbittorrent", "curl", "-sf", f"http://127.0.0.1:{ENV['QBIT_PORT']}/api/v2/torrents/{path}",
                           *args], capture_output=True, text=True, check=True).stdout


def ensure_plugin():
    if any(s["implementation"] == "SlskdIndexer" for s in lidarr("/indexer/schema")):
        print("  = Tubifarry plugin already installed")
        return

    cmd = lidarr("/command", {"name": "InstallPlugin", "githubUrl": PLUGIN})
    for _ in range(60):
        time.sleep(3)
        state = lidarr(f"/command/{cmd['id']}")
        if state["status"] in ("completed", "failed"):
            break

    if state["status"] != "completed":
        sys.exit(f"plugin install failed: {state.get('message')}")

    subprocess.run(["docker", "restart", "lidarr"], check=True, capture_output=True)
    wait_for_lidarr()
    print("  + installed Tubifarry and restarted Lidarr")


def ensure(kind, implementation, name, fields, **extra):
    if any(x["implementation"] == implementation for x in lidarr(f"/{kind}")):
        print(f"  = {name} already added as {kind}")
        return

    schema = next(s for s in lidarr(f"/{kind}/schema") if s["implementation"] == implementation)
    body = {**schema, "name": name, "enable": True, **extra,
            "fields": [{**f, "value": fields.get(f["name"], f.get("value"))} for f in schema["fields"]]}

    lidarr(f"/{kind}?forceSave=true", body)
    print(f"  + added {name} as {kind}")


def ensure_fields(kind, implementation, wanted, label, **extra):
    """Set some fields (and top-level settings) on an existing item; True if it changed."""
    item = next(x for x in lidarr(f"/{kind}") if x["implementation"] == implementation)
    current = {f["name"]: f.get("value") for f in item["fields"]}
    if all(current.get(k) == v for k, v in wanted.items()) and all(item.get(k) == v for k, v in extra.items()):
        print(f"  = {label}")
        return False

    fields = [{**f, "value": wanted.get(f["name"], f.get("value"))} for f in item["fields"]]
    lidarr(f"/{kind}/{item['id']}?forceSave=true", {**item, **extra, "fields": fields}, "PUT")
    print(f"  + {label}")
    return True


def ensure_navidrome_admin():
    out = http(f"{NAVIDROME}/auth/createAdmin",
               {"username": ENV["NAVIDROME_USER"], "password": ENV["NAVIDROME_PASS"]}, fatal=False)
    print("  + created Navidrome admin" if out and "username" in out else "  = Navidrome admin already exists")


print("[lidarr]")
wait_for_lidarr()
ensure_plugin()

# Priority 1 (default 25) so Soulseek wins over public torrents, which rarely have seeders for music.
ensure("indexer", "SlskdIndexer", "Soulseek", SLSKD, priority=1)
ensure("downloadclient", "SlskdClient", "Soulseek", {**SLSKD, "host": "gluetun"})

# The indexer template leaves searching off (Soulseek has no RSS). Rare albums answer slowly and
# often drop accents, hence the 20 s wait (default 5), accent-free search and a looser fallback.
SEARCH = {"timeoutInSeconds": 20, "normalizedSeach": True, "useFallbackSearch": True}
ensure_fields("indexer", "SlskdIndexer", SEARCH, "Soulseek searched first: 20 s wait, accents ignored, fallback",
              enableAutomaticSearch=True, enableInteractiveSearch=True)

naming = lidarr("/config/naming")
if naming.get("renameTracks"):
    print("  = track renaming already on")
else:
    # Off by default, which leaves source filenames and no album folder.
    lidarr(f"/config/naming/{naming['id']}", {**naming, "renameTracks": True}, "PUT")
    print("  + track renaming on (Artist/Album (Year)/Artist - Album - 01 - Title)")

# Lidarr writes no tags, so Navidrome shows no cover; the Kodi/Emby writer saves only folder.jpg
# (and discart.jpg) in each album folder, where Navidrome looks.
COVERS_ONLY = {"artistMetadata": False, "albumMetadata": False, "artistImages": False, "albumImages": True}
if ensure_fields("metadata", "XbmcMetadata", COVERS_ONLY, "album covers saved as folder.jpg", enable=True):
    lidarr("/command", {"name": "RefreshArtist"})
    print("    refreshing artists so existing albums get their cover")

# The qBittorrent category Lidarr uses must save under torrents/ for hardlinks
# into media/ to work, like the radarr/sonarr categories.
music = json.loads(qbit("categories")).get("music")
if music and music["savePath"] == MUSIC_PATH:
    print(f"  = qBittorrent category 'music' -> {MUSIC_PATH}")
else:
    qbit("editCategory" if music else "createCategory", "-d", f"category=music&savePath={MUSIC_PATH}")
    print(f"  + qBittorrent category 'music' -> {MUSIC_PATH}")

print("[navidrome]")
ensure_navidrome_admin()
print("Done.")

#!/usr/bin/env python3
"""Configure Questarr: admin account, qBittorrent, indexers from Prowlarr, IGDB, ntfy.

Idempotent. IGDB is set only once IGDB_CLIENT_ID and IGDB_CLIENT_SECRET are in
.env; they come from your own Twitch developer app.
"""
import secrets
import subprocess
import urllib.parse

from stack_env import ENV, NTFY_SERVER, arr_key, http, require_service

require_service("questarr")

B = "http://127.0.0.1:5000/api"


def raw(path, body=None, method=None, tok=None, fatal=True):
    return http(B + path, body, method, {"Authorization": f"Bearer {tok}"} if tok else None, fatal=fatal)


# Questarr's password policy rejects `admin`, but login only compares the bcrypt hash.
SET_HASH = """
const d = new (require("better-sqlite3"))("/app/data/sqlite.db");
d.prepare("update users set password_hash = ? where username = 'admin'")
 .run(require("bcryptjs").hashSync(process.env.PW, 10));
"""

creds = {"username": "admin", "password": ENV["QUESTARR_PASSWORD"]}
if not raw("/auth/status")["hasUsers"]:
    raw("/auth/setup", {**creds, "password": secrets.token_urlsafe(12) + "a1"})
    print("  + created admin account")

login = raw("/auth/login", creds, fatal=False)
if not login:
    subprocess.run(["docker", "exec", "-w", "/app", "-e", f"PW={creds['password']}", "questarr",
                    "node", "-e", SET_HASH], check=True)
    print("  + set admin password")
    login = raw("/auth/login", creds)

tok = login["token"]


def call(path, body=None, method=None):
    return raw(path, body, method, tok)


if not any(d["type"] == "qbittorrent" for d in call("/downloaders")):
    call("/downloaders", {"name": "qBittorrent", "type": "qbittorrent", "url": "http://gluetun",
                           "port": int(ENV["QBIT_PORT"]), "username": "", "password": "", "category": "games",
                           "downloadPath": "/data/torrents/games", "allowInsecureLan": True})
    print("  + qBittorrent")

d = next(d for d in call("/downloaders") if d["type"] == "qbittorrent")
print(f"  qBittorrent test: {call(f'/downloaders/{d['id']}/test', {}).get('message', 'ok')}")

# Questarr's SABnzbd client reads the API key from its "username" field.
if ENV.get("SABNZBD_API_KEY"):
    if not any(d["type"] == "sabnzbd" for d in call("/downloaders")):
        call("/downloaders", {"name": "SABnzbd", "type": "sabnzbd", "url": "http://sabnzbd", "port": 8080,
                               "username": ENV["SABNZBD_API_KEY"], "password": "", "category": "games",
                               "allowInsecureLan": True})
        print("  + SABnzbd")

    d = next(d for d in call("/downloaders") if d["type"] == "sabnzbd")
    print(f"  SABnzbd test: {call(f'/downloaders/{d['id']}/test', {}).get('message', 'ok')}")

# By IP, not name: Prowlarr puts the host it was called on into its download
# links and Questarr rejects links whose host differs from this URL's.
print("  " + call("/indexers/prowlarr/sync", {"url": f"http://{ENV['PROWLARR_IP']}:9696", "apiKey": arr_key("prowlarr")})["message"])
prowlarr_ids = [i["id"] for i in http(f"http://{ENV['PROWLARR_IP']}:9696/api/v1/indexer",
                                       headers={"X-Api-Key": arr_key("prowlarr")})]

for idx in call("/indexers"):
    # The sync adds and updates but never removes, so also drop indexers Prowlarr deleted.
    if not any(f"{ENV['PROWLARR_IP']}:9696/{i}/" in idx["url"] for i in prowlarr_ids):
        raw(f"/indexers/{idx['id']}", method="DELETE", tok=tok, fatal=False)
        print(f"  - removed stale indexer {idx['name']} ({idx['url']})")

if ENV.get("IGDB_CLIENT_ID") and ENV.get("IGDB_CLIENT_SECRET"):
    igdb = call("/settings/igdb")
    if igdb.get("configured") and igdb.get("clientId") == ENV["IGDB_CLIENT_ID"]:
        print("  = IGDB credentials")
    else:
        call("/settings/igdb", {"clientId": ENV["IGDB_CLIENT_ID"], "clientSecret": ENV["IGDB_CLIENT_SECRET"]})
        print("  + IGDB credentials")
else:
    print("  ! IGDB not set - fill IGDB_CLIENT_ID / IGDB_CLIENT_SECRET in .env and re-run")

# Questarr has one shared login and no approval step, so "Download Started" is how you learn
# a viewer picked a release.
if ENV.get("NTFY_TOPIC"):
    host = urllib.parse.urlparse(NTFY_SERVER).netloc
    urls = f"ntfys://{host}/{ENV['NTFY_TOPIC']}"

    if call("/settings/apprise").get("urls") == urls:
        print("  = ntfy notifications")
    else:
        call("/settings/apprise", {"mode": "cli", "apiUrl": "", "key": "", "urls": urls})
        print("  + ntfy notifications")

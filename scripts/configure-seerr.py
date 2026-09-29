#!/usr/bin/env python3
"""Point Seerr at Jellyfin and connect it to Radarr and Sonarr. Safe to re-run."""
import sys
import time
import urllib.request
from http.cookiejar import CookieJar

from stack_env import ENV, arr_key, http

BASE = "http://127.0.0.1:5055/api/v1"
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))


def call(path, body=None, method=None, quiet=False):
    out = http(BASE + path, body, method, timeout=120, fatal=False, opener=op)
    if out is None and not quiet:
        print(f"  ! {method or ('POST' if body is not None else 'GET')} {path} failed")

    return out


def arr_profile_id(app, port, name):
    """Seerr wants the numeric quality profile id, not just its name."""
    profs = http(f"http://127.0.0.1:{port}/api/v3/qualityprofile", headers={"X-Api-Key": arr_key(app)})
    return next(p["id"] for p in profs if p["name"] == name)


# Re-sending the Jellyfin hostname once it is stored returns 500, so log in with credentials only.
creds = {"username": ENV.get("JELLYFIN_USER", "admin"), "password": ENV["JELLYFIN_PASSWORD"]}
if not call("/auth/jellyfin", creds, quiet=True):
    # First run: the hostname has not been stored yet.
    if not call("/auth/jellyfin", {**creds, "hostname": "jellyfin", "port": 8096, "useSsl": False,
                                   "urlBase": "", "email": "admin@localhost", "serverType": 2}):
        sys.exit("  could not authenticate against Jellyfin")
print("  = logged in")

stored = (call("/settings/jellyfin", method="GET") or {}).get("libraries") or []
if stored and all(library["enabled"] for library in stored):
    print(f"  = libraries enabled: {', '.join(library['name'] for library in stored)}")
else:
    # Reading this endpoint resets every library to enabled=false: read once for the ids, then enable,
    # and never read it again or the enable is silently undone.
    libs = call("/settings/jellyfin/library", method="GET") or []
    if not libs:
        libs = call("/settings/jellyfin/library?sync=true") or []

    if libs:
        libs = call(f"/settings/jellyfin/library?enable={','.join(library['id'] for library in libs)}") or libs
        print(f"  + libraries enabled: {', '.join(library['name'] for library in libs)}")

for app, port, ep, prof, root in (
        ("radarr", 7878, "/settings/radarr", "HD Bluray + WEB", "/data/media/movies"),
        ("sonarr", 8989, "/settings/sonarr", "WEB-1080p", "/data/media/tv")):
    if call(ep, method="GET"):
        print(f"  = {app} already configured")
        continue

    body = {"name": app.capitalize(), "hostname": app, "port": port,
            "apiKey": arr_key(app), "useSsl": False, "baseUrl": "",
            "activeProfileId": arr_profile_id(app, port, prof),
            "activeProfileName": prof, "activeDirectory": root,
            "is4k": False, "isDefault": True, "externalUrl": "",
            "syncEnabled": True, "preventSearch": False, "tagRequests": False}
    if app == "sonarr":
        body.update({"activeAnimeProfileId": None, "activeAnimeDirectory": "",
                     "animeTags": [], "enableSeasonFolders": True})
    else:
        # Radarr-only: only chase a film once it has actually been released.
        body["minimumAvailability"] = "released"

    print(f"  + {app}: {'added' if call(ep, body) else 'FAILED'}")

# Seerr notification type bits: 8 = media available, 16 = request failed.
# New requests are left out: JellyDash already pushes those.
NTFY_TYPES = 8 | 16
if ENV.get("NTFY_TOPIC"):
    ntfy = call("/settings/notifications/ntfy", method="GET") or {}
    opts = {**ntfy.get("options", {}), "url": ENV.get("NTFY_SERVER", "https://ntfy.sh"), "topic": ENV["NTFY_TOPIC"]}
    if ntfy.get("enabled") and ntfy.get("types") == NTFY_TYPES and ntfy.get("options") == opts:
        print("  = ntfy: available and failed requests")
    else:
        call("/settings/notifications/ntfy", {**ntfy, "enabled": True, "types": NTFY_TYPES, "options": opts})
        print("  + ntfy: available and failed requests")

if (call("/settings/public", method="GET") or {}).get("initialized"):
    print("  = initialized")
    sys.exit()

call("/settings/initialize", {}, method="POST")

# Sync the existing library so what's already on disk shows as available, not requestable.
call("/settings/jellyfin/sync", {"start": True})
for _ in range(25):
    time.sleep(8)
    if not (call("/settings/jellyfin/sync", method="GET") or {}).get("running"):
        break

pub = call("/settings/public", method="GET")
media = call("/media?take=1", method="GET") or {}
print(f"\n  + initialized={pub.get('initialized')} "
      f"mediaServerType={pub.get('mediaServerType')} (2=Jellyfin) "
      f"knownMedia={media.get('pageInfo', {}).get('results', 0)}")

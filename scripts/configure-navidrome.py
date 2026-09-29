#!/usr/bin/env python3
"""Give Navidrome a second library, "Singles", for the songs Needle fetches one by one.

Makes sure $DATA_ROOT/media/singles (outside Lidarr's reach) exists, Navidrome has a library
on /singles and every non-admin user can see it. Signs in with NAVIDROME_USER / NAVIDROME_PASS.
Idempotent: a second run prints only "=" lines.
"""
import os
from pathlib import Path

from stack_env import ENV, http, require_service

require_service("navidrome")

URL = "http://127.0.0.1:4533"
NAME, PATH = "Singles", "/singles"
FOLDER = Path(ENV["DATA_ROOT"]) / "media" / "singles"
uid, gid = int(ENV["PUID"]), int(ENV["PGID"])

if FOLDER.is_dir():
    print(f"  = {FOLDER} exists")
else:
    FOLDER.mkdir(parents=True)
    os.chown(FOLDER, uid, gid)
    print(f"  + created {FOLDER}")

token = http(f"{URL}/auth/login", {"username": ENV["NAVIDROME_USER"], "password": ENV["NAVIDROME_PASS"]})["token"]
auth = {"x-nd-authorization": f"Bearer {token}"}

libraries = http(f"{URL}/api/library", headers=auth)
library = next((known for known in libraries if known["path"] == PATH), None)

if library:
    print(f"  = Navidrome library '{library['name']}' on {PATH}")
else:
    library = http(f"{URL}/api/library", {"name": NAME, "path": PATH, "defaultNewUsers": True}, headers=auth)
    print(f"  + Navidrome library '{NAME}' on {PATH}")

for user in http(f"{URL}/api/user", headers=auth):
    if user.get("isAdmin"):
        continue

    ids = [user_library["id"] for user_library in user.get("libraries") or []]
    if library["id"] in ids:
        print(f"  = {user['userName']} sees {NAME}")
        continue

    http(f"{URL}/api/user/{user['id']}/library", {"libraryIds": ids + [library["id"]]}, method="PUT", headers=auth)
    print(f"  + {user['userName']} can see {NAME}")

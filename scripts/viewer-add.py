#!/usr/bin/env python3
"""Give someone their own Jellyfin account, sign them up in Seerr with it, give them a
login to the games download page (SFTPGo) and a Navidrome account for music in Needle,
all with the same password.

Runs: by hand.
Changes: Jellyfin, Seerr, SFTPGo, Navidrome and Needle accounts through their APIs.
Idempotent: yes; existing accounts keep their password, and the flags only switch permissions on.

  viewer-add.py NAME [--auto-approve] [--music-requests] [--spotify]
                                          asks for the password (or reads it from stdin)

The account watches and listens to everything but can't manage the servers or delete
media. In Seerr it can request; requests wait for your approval unless --auto-approve
is given. In Needle it listens; --music-requests lets it get albums and songs, and
--spotify lets it connect Spotify (Settings → People in Needle shows and changes both).
The Navidrome username is NAME up to any "@", so an email NAME signs in to Needle as its
first part.
Idempotent: existing accounts keep their password, and the flags only switch things on.
Tailscale access is a separate step, see docs/flows/viewers.md.
"""
import functools
import getpass
import hashlib
import secrets
import sys

from games_accounts import ensure, exists
from stack_env import ENV, enabled_services, http, jellyfin_headers

JELLYFIN = ("http://127.0.0.1:8096", jellyfin_headers())
SEERR = ("http://127.0.0.1:5055/api/v1", {"X-Api-Key": ENV["SEERR_API_KEY"]})
NAVIDROME_URL = "http://127.0.0.1:4533"
NEEDLE_URL = "http://127.0.0.1:4535/api"

FLAGS = {"--auto-approve", "--music-requests", "--spotify"}

SEERR_REQUEST, SEERR_AUTO_APPROVE = 32, 128

VIEWER_POLICY = {"IsAdministrator": False, "IsDisabled": False, "EnableAllFolders": True,
                 "EnableMediaPlayback": True, "EnableRemoteAccess": True, "EnableContentDeletion": False,
                 "EnableCollectionManagement": False, "EnableSubtitleManagement": False,
                 "EnableLiveTvManagement": False}


def call(api, path, body=None, method=None):
    base, headers = api
    return http(base + path, body, method, headers)


@functools.cache
def password():
    pw = getpass.getpass(f"Password for {name}: ") if sys.stdin.isatty() else sys.stdin.readline().rstrip("\n")

    if not pw:
        sys.exit("empty password")

    return pw


def navidrome():
    """Navidrome's own API, signed in as the admin from .env."""
    login = call((NAVIDROME_URL, {}), "/auth/login", {"username": ENV["NAVIDROME_USER"], "password": ENV["NAVIDROME_PASS"]})
    return NAVIDROME_URL + "/api", {"x-nd-authorization": f"Bearer {login['token']}"}


def needle():
    """Needle's API, signed in as the Navidrome admin with a Subsonic token."""
    salt = secrets.token_hex(6)
    token = hashlib.md5((ENV["NAVIDROME_PASS"] + salt).encode()).hexdigest()

    return NEEDLE_URL, {"x-needle-user": ENV["NAVIDROME_USER"], "x-needle-token": token, "x-needle-salt": salt}


args = sys.argv[1:]
flags = {a for a in args if a in FLAGS}
names = [a for a in args if a not in FLAGS]

if len(names) != 1 or any(a.startswith("--") for a in names):
    sys.exit(__doc__)

auto_approve = "--auto-approve" in flags
name = names[0]

user = next((u for u in call(JELLYFIN, "/Users") if u["Name"].lower() == name.lower()), None)
if user:
    print(f"  = Jellyfin user '{name}' exists (password unchanged)")
else:
    user = call(JELLYFIN, "/Users/New", {"Name": name, "Password": password()})
    print(f"  + Jellyfin user '{name}'")

policy = user["Policy"]
if all(policy.get(k) == v for k, v in VIEWER_POLICY.items()):
    print("  = viewer permissions")
else:
    call(JELLYFIN, f"/Users/{user['Id']}/Policy", {**policy, **VIEWER_POLICY})
    print("  + viewer permissions (watch everything, no admin, no deleting)")


def seerr_user():
    return next((u for u in call(SEERR, "/user?take=1000")["results"] if u.get("jellyfinUserId") == user["Id"]), None)


seerr = seerr_user()
if seerr:
    print(f"  = Seerr user '{name}'")
else:
    call(SEERR, "/user/import-from-jellyfin", {"jellyfinUserIds": [user["Id"]]})
    seerr = seerr_user()
    print(f"  + Seerr user '{name}' (signs in with the Jellyfin login)")

wanted = seerr["permissions"] | SEERR_REQUEST | (SEERR_AUTO_APPROVE if auto_approve else 0)
if wanted == seerr["permissions"]:
    print("  = Seerr permissions" + (" (auto-approve)" if seerr["permissions"] & SEERR_AUTO_APPROVE else ""))
else:
    call(SEERR, f"/user/{seerr['id']}/settings/permissions", {"permissions": wanted})
    print("  + Seerr: can request" + (", auto-approved" if auto_approve else ""))

if "sftpgo" in enabled_services():
    print(f"  {ensure(name, None if exists(name) else password())} games download login '{name}' (read-only)")

if "navidrome" not in enabled_services():
    sys.exit()

music_name = name.split("@")[0]
nd = navidrome()
if any(u["userName"].lower() == music_name.lower() for u in call(nd, "/user")):
    print(f"  = Navidrome user '{music_name}' exists (password unchanged)")
else:
    call(nd, "/user", {"userName": music_name, "name": music_name, "password": password(), "isAdmin": False})
    print(f"  + Navidrome user '{music_name}' (signs in to Needle, not an admin)")

grant = {"canRequest": "--music-requests" in flags, "canSpotify": "--spotify" in flags}
if any(grant.values()):
    api = needle()
    known = {p["user"].lower(): p for p in call(api, "/people")}
    person = known.get(music_name.lower(), {"user": music_name, "canRequest": False, "canSpotify": False})
    missing = {k: True for k, on in grant.items() if on and not person[k]}

    if missing:
        person = call(api, f"/people/{person['user']}", missing, "PUT")

    labels = [label for key, label in (("canRequest", "request music"), ("canSpotify", "use Spotify")) if person[key]]
    print(f"  {'+' if missing else '='} Needle: can {' and '.join(labels)}")

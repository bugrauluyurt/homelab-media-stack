#!/usr/bin/env python3
"""Set up SFTPGo, the read-only games download page: start it, lock its admin
to the server, and create your login from GAMES_USER / GAMES_PASSWORD in .env.
Viewers' logins come from viewer-add.py. Idempotent: a second run changes nothing.
"""
import subprocess
from pathlib import Path

from games_accounts import admin, ensure, lock_admin, login_works, wait_ready
from stack_env import CONFIG, ENV, REPO, require_service

require_service("sftpgo")

USENET_GAMES = Path(ENV["DATA_ROOT"]) / "usenet" / "complete" / "games"
user, password = ENV["GAMES_USER"], ENV["GAMES_PASSWORD"]

# Compose mounts the Usenet games folder but will not create it.
for folder in (USENET_GAMES, CONFIG / "sftpgo"):
    if not folder.is_dir():
        folder.mkdir(parents=True)
        print(f"  + {folder}")

subprocess.run(["docker", "compose", "up", "-d", "sftpgo"], cwd=REPO, check=True, capture_output=True)
wait_ready()

print(f"  {'+ admin limited' if lock_admin(admin()) else '= admin limited'} to the server and Docker")

if login_works(user, password):
    print(f"  {ensure(user)} games login '{user}' (read-only)")
else:
    ensure(user, password)

    if not login_works(user, password):
        raise SystemExit("games login still fails after setting it")

    print(f"  + games login '{user}' set from .env")

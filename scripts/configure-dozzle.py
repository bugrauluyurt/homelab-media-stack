#!/usr/bin/env python3
"""Configure Dozzle's login from DOZZLE_USER / DOZZLE_PASSWORD in .env.

Idempotent: when the login already works nothing changes; otherwise users.yml is
regenerated with Dozzle's own generator and the container restarted.
"""
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from stack_env import CONFIG, ENV, REPO, require_service

require_service("dozzle")

URL = "http://127.0.0.1:8888"
USERS = CONFIG / "dozzle" / "users.yml"

user, password = ENV["DOZZLE_USER"], ENV["DOZZLE_PASSWORD"]


def login_works():
    body = urllib.parse.urlencode({"username": user, "password": password}).encode()

    try:
        return urllib.request.urlopen(urllib.request.Request(f"{URL}/api/token", data=body), timeout=15).status == 200
    except urllib.error.HTTPError:
        return False


def wait_for_dozzle():
    for _ in range(40):
        try:
            urllib.request.urlopen(f"{URL}/healthcheck", timeout=5)
            return
        except OSError:
            time.sleep(3)

    sys.exit("Dozzle did not come up")


def write_users():
    # Password through stdin, never on a command line.
    yml = subprocess.run(["docker", "run", "--rm", "-i", "amir20/dozzle", "generate", user,
                          "--email", f"{user}@localhost", "--name", user.capitalize()],
                         input=f"{password}\n", capture_output=True, text=True, check=True).stdout

    USERS.parent.mkdir(parents=True, exist_ok=True)
    USERS.write_text(yml)
    USERS.chmod(0o600)


# Dozzle refuses to start without users.yml, so a first run writes it up front.
fresh = not USERS.exists()
if fresh:
    write_users()

subprocess.run(["docker", "compose", "up", "-d", "dozzle"], cwd=REPO, check=True, capture_output=True)
wait_for_dozzle()

if login_works():
    print(f"  {'+ Dozzle login' if fresh else '= Dozzle login'} '{user}' {'set from .env' if fresh else 'works'}")
    sys.exit(0)

write_users()
subprocess.run(["docker", "compose", "restart", "dozzle"], cwd=REPO, check=True, capture_output=True)
wait_for_dozzle()

if not login_works():
    sys.exit("Dozzle login still fails after writing users.yml")

print(f"  + Dozzle login '{user}' set from .env")

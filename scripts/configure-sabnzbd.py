#!/usr/bin/env python3
"""Configure SABnzbd: the Usenet server from .env, download folders on the
media drive, and one category per app. Idempotent.
"""
import json
import subprocess
import sys
import time
import urllib.parse
import urllib.request

from stack_env import CONFIG, ENV, REPO, set_env

URL = "http://127.0.0.1:8085/api"
SERVER = "usenet"
CATEGORIES = {"movies": "movies", "tv": "tv", "music": "music", "games": "games"}

# Hostnames the UI is opened by (from Homepage's allow-list) plus "sabnzbd" for
# other containers; SABnzbd rejects any other hostname. IPs are always allowed.
HOSTNAMES = ["sabnzbd"] + sorted({h.split(":")[0] for h in ENV["HOMEPAGE_ALLOWED_HOSTS"].split(",")
                                  if not h.split(":")[0].replace(".", "").isdigit()} - {"localhost"})

# Networks treated as local. Replaces SABnzbd's default private-only list, which
# lacks Tailscale's 100.64.0.0/10 and so refused phones on the tailnet.
LOCAL_RANGES = [ENV["LAN_CIDR"], "100.64.0.0/10", "172.16.0.0/12", "127.0.0.0/8"]

MISC = {"download_dir": "/data/usenet/incomplete", "complete_dir": "/data/usenet/complete",
        "host_whitelist": ",".join(HOSTNAMES),
        "username": ENV.get("SABNZBD_USER", ""), "password": ENV.get("SABNZBD_PASSWORD", "")}

INI = CONFIG / "sabnzbd" / "sabnzbd.ini"
KEY = subprocess.run(["sudo", "grep", "-oP", r"^api_key = \K\S+", f"{CONFIG}/sabnzbd/sabnzbd.ini"],
                     capture_output=True, text=True).stdout.strip()

if ENV.get("SABNZBD_API_KEY") != KEY:
    set_env("SABNZBD_API_KEY", KEY)
    print("  + stored SABnzbd's API key in .env (for the Homepage widget)")


def api(**params):
    q = urllib.parse.urlencode({**params, "apikey": KEY, "output": "json"})
    return json.loads(urllib.request.urlopen(f"{URL}?{q}", timeout=60).read())


def wait_for_api():
    for _ in range(40):
        try:
            return api(mode="version")
        except OSError:
            time.sleep(3)
    sys.exit("SABnzbd did not come back")


# SABnzbd ignores API changes to local_ranges (a security setting), so it is
# written into sabnzbd.ini directly while the container is stopped.
wanted = "local_ranges = " + ", ".join(LOCAL_RANGES)
lines = INI.read_text().splitlines()
index = next(i for i, line in enumerate(lines) if line.startswith("local_ranges ="))

if lines[index] == wanted:
    print("  = local_ranges " + ", ".join(LOCAL_RANGES))
else:
    subprocess.run(["docker", "compose", "stop", "sabnzbd"], cwd=REPO, check=True, capture_output=True)
    lines[index] = wanted
    INI.write_text("\n".join(lines) + "\n")
    subprocess.run(["docker", "compose", "start", "sabnzbd"], cwd=REPO, check=True, capture_output=True)
    wait_for_api()
    print("  + local_ranges -> " + ", ".join(LOCAL_RANGES) + " (sabnzbd.ini, restarted)")

config = api(mode="get_config")["config"]

for keyword, value in MISC.items():
    current = config["misc"].get(keyword)
    current = ",".join(current) if isinstance(current, list) else current
    # SABnzbd returns the password masked, so compare it by trying the login instead.
    if keyword == "password":
        continue
    if current == value:
        print(f"  = {keyword} {value}")
        continue
    api(mode="set_config", section="misc", keyword=keyword, value=value)
    print(f"  + {keyword} -> {value}")


def login_works():
    body = urllib.parse.urlencode({"username": MISC["username"], "password": MISC["password"]}).encode()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor())

    return not opener.open(urllib.request.Request("http://127.0.0.1:8085/login/", data=body),
                           timeout=30).geturl().rstrip("/").endswith("/login")


if login_works():
    print(f"  = login '{MISC['username']}' works")
else:
    api(mode="set_config", section="misc", keyword="password", value=MISC["password"])
    print("  + login password set from .env")

if not ENV.get("USENET_HOST"):
    print("  ~ Usenet server skipped (set USENET_HOST in .env)")
    sys.exit()

server = {"host": ENV["USENET_HOST"], "port": ENV.get("USENET_PORT", "563"), "ssl": "1",
          "username": ENV["USENET_USER"], "password": ENV["USENET_PASS"],
          "connections": ENV.get("USENET_CONNECTIONS", "20"), "enable": "1", "ssl_verify": "2"}

existing = next((s for s in config.get("servers", []) if s["name"] == SERVER), None)
same = existing and all(str(existing.get(k)) == v for k, v in server.items() if k != "password")
if same:
    print(f"  = server {server['host']}")
else:
    api(mode="set_config", section="servers", keyword=SERVER, name=SERVER, displayname="Usenet", **server)
    print(f"  + server {server['host']}:{server['port']} (SSL, {server['connections']} connections)")

test = api(mode="config", name="test_server", server=SERVER, **server)
if not test.get("value", {}).get("result"):
    sys.exit(f"  ! server test failed: {test.get('value', {}).get('message')}")

print(f"  = server test: {test['value'].get('message', 'ok')}")

# The full config omits categories; ask for the section itself.
have = {c["name"]: c.get("dir") for c in api(mode="get_config", section="categories")["config"]["categories"]}
for name, folder in CATEGORIES.items():
    if have.get(name) == folder:
        print(f"  = category {name}")
        continue
    api(mode="set_config", section="categories", keyword=name, name=name, dir=folder)
    print(f"  + category {name} -> complete/{folder}")

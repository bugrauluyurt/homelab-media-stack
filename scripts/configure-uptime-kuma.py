#!/usr/bin/env python3
"""Configure Uptime Kuma: admin account, ntfy alerts, one monitor per published
TCP port in docker-compose.yml, and a status page at /status/stack.

Runs: by hand, last among the configure scripts, and again after adding or removing a service or
  switching a module off.
Changes: creates a Python venv in $STATE/venv with python-socketio from PyPI on first run; Kuma
  settings, monitors and status page; the admin password's hash in Kuma's database through docker
  exec.
Idempotent: yes.

Monitors added by hand are
never touched. Kuma 2 has no REST API, so this re-runs itself in a venv with
python-socketio.
"""
import json
import os
import secrets
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

from stack_env import ENV, NTFY_SERVER, REPO, STATE, STORAGE, enabled_services, require_service

require_service("uptime-kuma")

VENV = STATE / "venv"
try:
    import socketio
except ImportError:
    if sys.prefix == str(VENV):
        sys.exit("python-socketio missing from the venv")
    if not VENV.exists():
        subprocess.run([sys.executable, "-m", "venv", str(VENV)], check=True)
        subprocess.run([str(VENV / "bin/pip"), "-q", "install", "python-socketio[client]"], check=True)
    os.execv(str(VENV / "bin/python"), [str(VENV / "bin/python"), *sys.argv])

KUMA = "http://127.0.0.1:3003"
SLUG = "stack"
SKIP = {("uptime-kuma", 3001), ("sftpgo", 2022)}

# qBittorrent and slskd are reached through gluetun's network namespace.
GLUETUN_PORTS = {int(ENV["QBIT_PORT"]): "qbittorrent", 5030: "slskd"}
PATHS = {"questarr": "/api/health", "navidrome": "/ping", "slskd": "/health",
         "dozzle": "/healthcheck", "jellydash": "/healthz.php", "sftpgo": "/healthz",
         "glance": "/api/healthz", "scrutiny": "/api/health", "needle": "/api/health"}

# Not published on the host, but Kuma reaches them over the Docker network.
EXTRA_HTTP = {"plex": "http://host.docker.internal:32400/identity",
              "byparr": "http://byparr:8191/", "scraparr": "http://scraparr:7100/",
              "node-exporter": "http://host.docker.internal:9100/",
              "media drive mounted": "http://host.docker.internal:9100/metrics"}
KEYWORDS = {"media drive mounted": f'mountpoint="{STORAGE}"'}

# Proton can stop handing out a forwarded port while the tunnel stays up; torrents
# then quietly lose incoming peers. (url, JSON field, operator, expected value)
JSON_QUERIES = {"vpn forwarded port": ("http://gluetun:8000/v1/portforward", "port", ">", "0")}
DOCKER_HEALTH = ["gluetun"]


def http_monitors():
    services = json.loads(subprocess.run(["docker", "compose", "config", "--format", "json"], cwd=REPO,
                                         capture_output=True, text=True, check=True).stdout)["services"]

    found = {}
    for name, svc in services.items():
        for p in svc.get("ports", []):
            if p.get("protocol", "tcp") != "tcp" or (name, p["target"]) in SKIP:
                continue
            label = GLUETUN_PORTS.get(p["target"], name) if name == "gluetun" else name
            found[label] = f"http://{name}:{p['target']}{PATHS.get(label, '/')}"

    # "media drive mounted" reads node-exporter; the rest are named after their service.
    extra = {label: url for label, url in EXTRA_HTTP.items()
             if ("node-exporter" if label == "media drive mounted" else label) in enabled_services()}

    return {**found, **extra}


sio = socketio.Client()
lists = {}
for event in ("monitorList", "notificationList", "dockerHostList"):
    sio.on(event, lambda data, event=event: lists.__setitem__(event, data))


def emit(event, *args, fatal=True, wait=60):
    result, done = {}, threading.Event()

    def reply(res=None):
        result.update(res if isinstance(res, dict) else {"value": res})
        done.set()

    sio.emit(event, args or None, callback=reply)
    if not done.wait(wait):
        if not fatal:
            return None
        sys.exit(f"{event}: no answer from Kuma")

    if result.get("ok") is False and fatal:
        sys.exit(f"{event}: {result.get('msg')}")

    return result


# Kuma refuses weak passwords like "admin", so the .env one is written as a bcrypt hash into its
# database, through stdin so it never shows in a process list.
SET_HASH = """let pw = "";
process.stdin.on("data", d => pw += d).on("end", () => {
  const bcrypt = require("bcryptjs"), sqlite = require("@louislam/sqlite3");
  const db = new sqlite.Database("/app/data/kuma.db");
  db.run("UPDATE user SET password = ? WHERE username = ?", [bcrypt.hashSync(pw, 10), process.argv[1]],
    function (e) { if (e || this.changes !== 1) { console.error(e || "no such user"); process.exit(1); } db.close(); });
});"""


def set_password(user, password):
    subprocess.run(["docker", "exec", "-i", "uptime-kuma", "node", "-e", SET_HASH, user],
                   input=password, text=True, check=True)


def pushed(name):
    for _ in range(100):
        if name in lists:
            return lists[name]
        sio.sleep(0.1)
    sys.exit(f"Kuma never sent {name}")


def status_page():
    # Kuma caches this route for 5 minutes per URL; a unique query bypasses it.
    try:
        return json.loads(urllib.request.urlopen(f"{KUMA}/api/status-page/{SLUG}?t={time.time()}", timeout=30).read())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


# Kuma can be slow to answer right after it or its neighbours restart.
for attempt in range(3):
    sio.connect(KUMA, transports=["websocket"])
    setup = emit("needSetup", fatal=False, wait=20)
    if setup is not None:
        break
    sio.disconnect()
else:
    sys.exit("Kuma is not answering")

user, password = ENV["UPTIME_KUMA_USER"], ENV["UPTIME_KUMA_PASSWORD"]
if setup.get("value"):
    emit("setup", user, secrets.token_urlsafe(24) + "Aa1!")
    print(f"  + created Kuma admin '{user}'")

if emit("login", {"username": user, "password": password, "token": ""}, fatal=False).get("ok") is False:
    set_password(user, password)
    emit("login", {"username": user, "password": password, "token": ""})
    print("  + set the Kuma password from .env")

ntfy = next((n for n in pushed("notificationList") if n["name"] == "ntfy"), None)
ntfy_id = None
if not ENV.get("NTFY_TOPIC"):
    print("  ~ ntfy alerts skipped (set NTFY_TOPIC in .env)")
elif ntfy:
    ntfy_id = ntfy["id"]
    print("  = ntfy notification exists")
else:
    ntfy_id = emit("addNotification", {
        "name": "ntfy", "type": "ntfy", "isDefault": True, "applyExisting": True,
        "ntfyserverurl": NTFY_SERVER, "ntfytopic": ENV["NTFY_TOPIC"],
        "ntfyPriority": 4, "ntfyAuthenticationMethod": "none"}, None)["id"]
    print("  + added ntfy notification (default for all monitors)")

# Kuma's DNS cache (nscd) keeps a recreated container's old address and reports it down for good.
settings = emit("getSettings").get("data") or {}
if settings.get("nscd") is False:
    print("  = Kuma DNS cache off")
else:
    emit("setSettings", {**settings, "nscd": False}, password)
    print("  + turned off Kuma's DNS cache")

docker_host = next((h["id"] for h in pushed("dockerHostList") if h["name"] == "socket-proxy"), None)
if docker_host is None:
    docker_host = emit("addDockerHost", {"name": "socket-proxy", "dockerType": "tcp",
                                         "dockerDaemon": "http://socket-proxy:2375"}, None)["id"]
    print("  + added docker host (read-only socket proxy)")
else:
    print("  = docker host exists")

BASE = {"interval": 60, "retryInterval": 60, "maxretries": 2, "resendInterval": 0,
        "accepted_statuscodes": ["200-299"], "notificationIDList": {str(ntfy_id): True} if ntfy_id else {},
        "conditions": [], "active": True, "maxredirects": 10, "timeout": 48}

wanted = {name: {**BASE, "name": name, "type": "keyword" if name in KEYWORDS else "http",
                 "url": url, "keyword": KEYWORDS.get(name)}
          for name, url in http_monitors().items()}
wanted.update({name: {**BASE, "name": name, "type": "json-query", "url": url, "jsonPath": path,
                       "jsonPathOperator": op, "expectedValue": value}
               for name, (url, path, op, value) in JSON_QUERIES.items()})
wanted.update({f"{c} healthy": {**BASE, "name": f"{c} healthy", "type": "docker",
                                "docker_container": c, "docker_host": docker_host} for c in DOCKER_HEALTH})

monitors = pushed("monitorList").values()
# Only monitors this script derived from compose point at http://<their own name>:.
stale = [m for m in monitors if m["name"] not in wanted and (m.get("url") or "").startswith(f"http://{m['name']}:")]
for m in stale:
    emit("deleteMonitor", m["id"])
    print(f"  - monitor {m['name']} (service gone)")

existing = {m["name"]: m["id"] for m in monitors if m not in stale}

# Monitors are matched by name, so one whose service moved (to the host network, say) needs its URL edited.
for m in monitors:
    url = wanted.get(m["name"], {}).get("url")
    if m not in stale and url not in (None, m.get("url")):
        emit("editMonitor", {**m, "url": url})
        print(f"  + monitor {m['name']} now checks {url}")

added = [name for name in sorted(wanted) if name not in existing]
for name in added:
    existing[name] = emit("add", wanted[name])["monitorID"]
    print(f"  + monitor {name}")

if not added:
    print(f"  = all {len(wanted)} monitors exist")

page = status_page()
if page is None:
    emit("addStatusPage", "Media stack", SLUG)
    page = status_page()
    print(f"  + status page /status/{SLUG}")

ids = [existing[name] for name in sorted(wanted)]
groups = page.get("publicGroupList") or []
if [m["id"] for g in groups for m in g["monitorList"]] == ids:
    print("  = status page lists every monitor")
else:
    config = {**page["config"], "domainNameList": [], "analyticsType": page["config"].get("analyticsType")}
    group = {"name": "Services", "monitorList": [{"id": i} for i in ids],
             **({"id": groups[0]["id"]} if groups else {})}
    emit("saveStatusPage", SLUG, config, config.get("icon") or "/icon.svg", [group])
    print("  + status page updated with every monitor")

sio.disconnect()

"""Paths, settings and HTTP helpers shared by the Python scripts, read from the repo's .env."""
import functools
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _value(raw):
    # .env single-quotes values holding $ (Compose and bash expand it); every tool reads them unquoted.
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "'\"":
        return raw[1:-1]

    return raw


ENV = {k: _value(v) for k, v in (line.split("=", 1) for line in (REPO / ".env").read_text().splitlines()
                                 if "=" in line and not line.lstrip().startswith("#"))}

CONFIG = Path(ENV["CONFIG_ROOT"])
STATE = CONFIG.parent / "state"
STORAGE = Path(ENV.get("STORAGE_MOUNT") or "/mnt/storage")

# Every module runs unless .env lists the wanted profiles.
os.environ.setdefault("COMPOSE_PROFILES", ENV.get("COMPOSE_PROFILES") or "*")


def set_env(key, value):
    """Set KEY=value in .env, replacing an existing line or appending one."""
    path = REPO / ".env"
    lines = path.read_text().splitlines()

    for i, line in enumerate(lines):
        if line.startswith(f"{key}="):
            lines[i] = f"{key}={value}"
            break
    else:
        lines.append(f"{key}={value}")

    path.write_text("\n".join(lines) + "\n")
    ENV[key] = value


def http(url, body=None, method=None, headers=None, timeout=60, fatal=True, opener=None):
    """JSON request. On an HTTP or connection error: exit if fatal, else return None."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method or ("POST" if data is not None else "GET"),
                                 headers={"Content-Type": "application/json", **(headers or {})})

    try:
        with (opener or urllib.request.build_opener()).open(req, timeout=timeout) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        if fatal:
            sys.exit(f"{req.method} {url} -> {e.code}: {e.read().decode()[:300]}")

        return None
    except OSError as e:
        if fatal:
            sys.exit(f"{req.method} {url} -> {e}")

        return None


@functools.cache
def arr_key(app):
    """API key of an *arr app: from .env when set, else from its config.xml."""
    key = ENV.get(f"{app.upper()}_API_KEY") or subprocess.run(
        ["sudo", "grep", "-oPm1", "(?<=<ApiKey>)[^<]+", f"{CONFIG}/{app}/config.xml"],
        capture_output=True, text=True).stdout.strip()

    if not key:
        sys.exit(f"could not read the {app} API key")

    return key


def wait_ready(url, what, tries=60, delay=2, headers=None):
    for _ in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers or {}), timeout=10):
                return
        except urllib.error.HTTPError:
            return
        except OSError:
            time.sleep(delay)

    sys.exit(f"{what} did not come up")


def notify(title, tags, body):
    """Push to the stack's ntfy topic, if one is set. JSON, so titles may hold any language."""
    if not ENV.get("NTFY_TOPIC"):
        return

    http(ENV.get("NTFY_SERVER", "https://ntfy.sh"), {"topic": ENV["NTFY_TOPIC"], "title": title,
         "tags": tags.split(","), "message": body}, timeout=15, fatal=False)


@functools.cache
def enabled_services():
    """Compose services in an active profile (COMPOSE_PROFILES)."""
    listed = subprocess.run(["docker", "compose", "config", "--services"], cwd=REPO,
                            capture_output=True, text=True, check=True)

    return set(listed.stdout.split())


def require_service(name):
    """Exit quietly when NAME's module is switched off in COMPOSE_PROFILES."""
    if name not in enabled_services():
        print(f"  ~ {name} is off (COMPOSE_PROFILES in .env); skipped")
        sys.exit(0)

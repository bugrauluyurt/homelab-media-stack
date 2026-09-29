#!/usr/bin/env python3
"""Give Glance the API keys it can't get from the apps' own settings pages.

Creates Jellystat's "glance" key and copies ChangeDetection.io's into .env, recreating
Glance only when one changed. Idempotent: a second run prints only = lines.
"""
import json
import subprocess
import urllib.request
import uuid

from stack_env import CONFIG, ENV, REPO, enabled_services, require_service, set_env, wait_ready

require_service("glance")

JELLYSTAT = "http://127.0.0.1:3002"
CHANGEDETECTION_SETTINGS = CONFIG / "changedetection" / "changedetection.json"
PSQL = ["docker", "exec", "-i", "jellystat-db", "sh", "-c", 'psql -U "$POSTGRES_USER" -d jfstat -tA']


def jellystat_key_works(key):
    req = urllib.request.Request(f"{JELLYSTAT}/stats/getLibraryOverview", headers={"x-api-token": key})

    try:
        return urllib.request.urlopen(req, timeout=15).status == 200
    except OSError:
        return False


def psql(sql):
    return subprocess.run(PSQL, input=sql, capture_output=True, text=True, check=True).stdout.strip()


def ensure_jellystat_key():
    wait_ready(JELLYSTAT, "Jellystat")

    key = ENV.get("JELLYSTAT_API_KEY")
    if key and jellystat_key_works(key):
        print("  = Jellystat API key for Glance works")
        return False

    keys = [k for k in json.loads(psql('SELECT COALESCE(api_keys, \'[]\') FROM app_config WHERE "ID"=1;') or "[]")
            if k.get("name") != "glance"]
    key = str(uuid.uuid4())
    keys.append({"name": "glance", "key": key})
    psql(f"UPDATE app_config SET api_keys='{json.dumps(keys)}' WHERE \"ID\"=1;")

    if not jellystat_key_works(key):
        raise SystemExit("Jellystat refused the new API key")

    set_env("JELLYSTAT_API_KEY", key)
    print("  + Jellystat API key 'glance' created")
    return True


def ensure_changedetection_key():
    key = json.loads(CHANGEDETECTION_SETTINGS.read_text())["settings"]["application"]["api_access_token"]

    if ENV.get("CHANGEDETECTION_API_KEY") == key:
        print("  = ChangeDetection API key in .env")
        return False

    set_env("CHANGEDETECTION_API_KEY", key)
    print("  + ChangeDetection API key copied to .env")
    return True


changed = [ensure_jellystat_key() if "jellystat" in enabled_services() else False, ensure_changedetection_key()]
if any(changed):
    subprocess.run(["docker", "compose", "up", "-d", "glance"], cwd=REPO, check=True, capture_output=True)
    print("  + Glance recreated with the new keys")

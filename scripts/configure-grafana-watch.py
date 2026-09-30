#!/usr/bin/env python3
"""Connect Grafana to narrowly scoped, read-only Jellystat viewing history."""
import base64
import json
import secrets
import subprocess
import sys
import urllib.error
import urllib.request

from stack_env import ENV, require_service

require_service("grafana")
require_service("jellystat-db")

URL = "http://127.0.0.1:3001"
UID = "jellystat-readonly"
ROLE = "grafana_watch_reader"
COLUMNS = ("Id", "UserId", "UserName", "NowPlayingItemName", "SeriesName",
           "PlaybackDuration", "ActivityDateInserted", "PlayMethod")

AUTH = "Basic " + base64.b64encode(
    f'{ENV["GRAFANA_USER"]}:{ENV["GRAFANA_PASSWORD"]}'.encode()).decode()


def api(path, body=None):
    req = urllib.request.Request(URL + path, method="POST" if body is not None else "GET",
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": AUTH, "Content-Type": "application/json"})

    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        if error.code == 404 and body is None:
            return None
        sys.exit(f"Grafana request failed: HTTP {error.code}; credentials omitted")


def sql(statement):
    result = subprocess.run(
        ["docker", "exec", "-i", "jellystat-db", "sh", "-c",
         'psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At'],
        input=statement, text=True, capture_output=True, timeout=30)

    if result.returncode:
        sys.exit("Database configuration failed; SQL output omitted to protect credentials")

    return result.stdout.strip()


def verify_permissions():
    allowed = ", ".join(f"'{column}'" for column in COLUMNS)

    scoped = sql(f"SELECT bool_and(has_column_privilege('{ROLE}', attrelid, attnum, 'SELECT') "
                 f"= (attname IN ({allowed}))) "
                 "FROM pg_attribute WHERE attrelid='public.jf_playback_activity'::regclass "
                 "AND attnum > 0 AND NOT attisdropped;")
    writes = sql(f"SELECT has_table_privilege('{ROLE}', 'public.jf_playback_activity', "
                 "'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER') "
                 f"OR has_any_column_privilege('{ROLE}', 'public.jf_playback_activity', "
                 "'INSERT,UPDATE,REFERENCES');")

    if scoped != "t" or writes != "f":
        sys.exit("Reader permissions failed verification")


def main():
    existing = api(f"/api/datasources/uid/{UID}")
    role = sql(f"SELECT rolname FROM pg_roles WHERE rolname='{ROLE}';")

    if role:
        elevated = sql(f"SELECT rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication "
                       f"OR rolbypassrls OR EXISTS (SELECT 1 FROM pg_auth_members "
                       f"WHERE member=pg_roles.oid) FROM pg_roles WHERE rolname='{ROLE}';")
        if elevated != "f":
            sys.exit("Existing reader role has unexpected privileges; refusing to proceed")

    if existing:
        if (not role or existing.get("user") != ROLE
                or existing.get("url") != "jellystat-db:5432"
                or existing.get("type") != "grafana-postgresql-datasource"
                or existing.get("jsonData", {}).get("database") != "jfstat"):
            sys.exit("Existing datasource differs from expected configuration; inspect manually")

    password = None if existing else secrets.token_hex(32)
    columns = ", ".join(f'"{column}"' for column in COLUMNS)
    statements = ["BEGIN;"]
    if not role:
        statements.append(f"CREATE ROLE {ROLE} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;")
    if password:
        statements.append(f"ALTER ROLE {ROLE} PASSWORD '{password}';")
    statements.extend([
        f"ALTER ROLE {ROLE} SET default_transaction_read_only=on;",
        f"ALTER ROLE {ROLE} SET statement_timeout='10s';",
        f"GRANT CONNECT ON DATABASE jfstat TO {ROLE};",
        f"GRANT USAGE ON SCHEMA public TO {ROLE};",
        f"GRANT SELECT ({columns}) ON public.jf_playback_activity TO {ROLE};",
        "COMMIT;",
    ])

    sql("\n".join(statements))
    verify_permissions()

    if not existing:
        api("/api/datasources", {
            "name": "Jellystat (read-only)", "uid": UID,
            "type": "grafana-postgresql-datasource", "access": "proxy",
            "url": "jellystat-db:5432", "user": ROLE, "isDefault": False,
            "jsonData": {"database": "jfstat", "sslmode": "disable", "postgresVersion": 1600,
                         "timescaledb": False, "maxOpenConns": 2, "maxIdleConns": 1,
                         "connMaxLifetime": 14400},
            "secureJsonData": {"password": password},
        })
        print("  + Jellystat read-only Grafana datasource created")
    else:
        print("  = Jellystat read-only Grafana datasource already configured")

    health = api(f"/api/datasources/uid/{UID}/health")
    if not health or health.get("status") != "OK":
        sys.exit("Grafana datasource health check failed")
    print("  = Connection healthy; viewing columns readable, writes and client IP column denied")


if __name__ == "__main__":
    main()

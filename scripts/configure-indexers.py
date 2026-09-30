#!/usr/bin/env python3
"""Add indexers to Prowlarr and report which actually work.

Runs: by hand, after configure-arr.py so Prowlarr syncs the new indexers to the apps.
Changes: Prowlarr API (new indexers at priority 25; the RSS only app profile, which the account
  trackers use).
Idempotent: yes; indexers already present are skipped, except that account trackers are moved to RSS
  only. The test searches run every time.

Adds the public indexers always, and those in ACCOUNTS once their API key is in .env.
Cloudflare-protected sites commonly fail here; that is expected, not a configuration error.
"""
import json
import urllib.error
import urllib.request

from stack_env import ENV, arr_key

PROWLARR = "http://127.0.0.1:9696"

# 1337x is left out: its Cloudflare often blocks residential IPs (error 1006); Knaben indexes its listings.
WANTED = ["thepiratebay", "yts", "eztv", "limetorrents",
          "torrentproject2", "Knaben",
          # French TV and film (M6, TF1...), which the English sites don't carry.
          "torrent9", "world-torrent"]

# Semi-private French trackers: free sign-up, API key on the profile page.
ACCOUNTS = {"draupnirr": "DRAUPNIRR_API_KEY", "tr4ker": "TR4KER_API_KEY"}
FRENCH = {"torrent9", "world-torrent", *ACCOUNTS}

# Account trackers enforce a ratio, so the apps get them for RSS and interactive search only: new
# releases have downloaders to upload to, while a backlog search grabs old ones that have none.
RSS_ONLY = {"name": "RSS only", "enableRss": True, "enableAutomaticSearch": False,
            "enableInteractiveSearch": True, "minimumSeeders": 1}


def call(method, path, body=None, timeout=90):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(PROWLARR + path, data=data, method=method,
                                 headers={"X-Api-Key": arr_key("prowlarr"),
                                          "Content-Type": "application/json"})

    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        return json.loads(raw) if raw else None


def rss_only_profile_id():
    rss_only_profile = next((profile for profile in call("GET", "/api/v1/appprofile")
                             if profile["name"] == RSS_ONLY["name"]), None)

    if not rss_only_profile:
        print(f"  + app profile {RSS_ONLY['name']}")
        return call("POST", "/api/v1/appprofile", RSS_ONLY)["id"]

    if {**rss_only_profile, **RSS_ONLY} != rss_only_profile:
        call("PUT", f"/api/v1/appprofile/{rss_only_profile['id']}", {**rss_only_profile, **RSS_ONLY})
        print(f"  + app profile {RSS_ONLY['name']} reset")
    else:
        print(f"  = app profile {RSS_ONLY['name']}")

    return rss_only_profile["id"]


schema = call("GET", "/api/v1/indexer/schema")
rss_profile_id = rss_only_profile_id()
existing = {i["name"] for i in call("GET", "/api/v1/indexer")}
by_def = {i["definitionName"]: i for i in schema}

added, failed, skipped = [], [], []

for name, key in ACCOUNTS.items():
    if not ENV.get(key):
        print(f"  ~ {name} skipped (set {key} in .env to enable)")

for name in WANTED + [n for n, k in ACCOUNTS.items() if ENV.get(k)]:
    tmpl = by_def.get(name)
    if not tmpl:
        failed.append((name, "no definition"))
        continue

    if tmpl["name"] in existing:
        skipped.append(tmpl["name"])
        continue

    body = dict(tmpl)
    body.update({"enable": True, "priority": 25, "tags": [],
                 "appProfileId": rss_profile_id if name in ACCOUNTS else 1})
    if name in ACCOUNTS:
        body["fields"] = [{**f, "value": ENV[ACCOUNTS[name]]} if f["name"] == "apikey" else f
                          for f in tmpl["fields"]]

    try:
        call("POST", "/api/v1/indexer?forceSave=true", body)
        added.append(tmpl["name"])
    except urllib.error.HTTPError as e:
        failed.append((name, e.read().decode()[:120]))
    except OSError as e:
        failed.append((name, f"unreachable ({type(e).__name__})"))

for account_indexer in call("GET", "/api/v1/indexer"):
    if account_indexer["definitionName"] not in ACCOUNTS:
        continue

    if account_indexer["appProfileId"] == rss_profile_id:
        print(f"  = {account_indexer['name']} RSS only")
        continue

    call("PUT", f"/api/v1/indexer/{account_indexer['id']}?forceSave=true",
         {**account_indexer, "appProfileId": rss_profile_id})
    print(f"  + {account_indexer['name']} moved to RSS only")

print(f"  added:   {', '.join(added) or '(none)'}")
print(f"  skipped: {', '.join(skipped) or '(none)'} (already present)")
for n, why in failed:
    print(f"  FAILED {n}: {why}")

print("\n  Testing each with a real search...")
for idx in call("GET", "/api/v1/indexer"):
    try:
        query = "france" if idx["definitionName"] in FRENCH else "ubuntu"
        res = call("GET", f"/api/v1/search?query={query}&indexerIds={idx['id']}&type=search",
                   timeout=120)

        n = len(res or [])
        print(f"    {idx['name']:<18} {'OK' if n else 'no results'} ({n} hits)")
    except Exception as e:
        print(f"    {idx['name']:<18} FAIL ({type(e).__name__})")

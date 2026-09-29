#!/usr/bin/env python3
"""Keep Glance's YouTube channel lists in step with your subscriptions.

Sorts your subscriptions (YouTube Data API, read-only) into the tabs of
glance/youtube-channels.json and writes each tab to $CONFIG_ROOT/glance/youtube-<tab>.yml.

  sync-youtube.py            sync (the weekly arr-youtube timer)
  sync-youtube.py --login    one-time sign-in; stores YOUTUBE_REFRESH_TOKEN in .env
  sync-youtube.py --offline  write missing lists from the pinned channels only (stack-up)
"""
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from stack_env import CONFIG, ENV, REPO, STATE, require_service, set_env

require_service("glance")

SCOPE = "https://www.googleapis.com/auth/youtube.readonly"
API = "https://www.googleapis.com/youtube/v3"
TOKEN_URL = "https://oauth2.googleapis.com/token"

CHANNELS = json.loads((REPO / "glance" / "youtube-channels.json").read_text())
OUT = CONFIG / "glance"
METRIC = STATE / "metrics" / "youtube.prom"

TOPICS = {"Gaming": ("game",), "Tech": ("technology",), "Markets": ("business", "finance", "economics")}


def post_form(url, fields):
    req = urllib.request.Request(url, data=urllib.parse.urlencode(fields).encode())

    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        return json.load(e)


def client():
    if not (ENV.get("YOUTUBE_CLIENT_ID") and ENV.get("YOUTUBE_CLIENT_SECRET")):
        sys.exit("set YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET in .env (see docs/using/dashboards.md)")

    return {"client_id": ENV["YOUTUBE_CLIENT_ID"], "client_secret": ENV["YOUTUBE_CLIENT_SECRET"]}


def login():
    device = post_form("https://oauth2.googleapis.com/device/code", {"client_id": client()["client_id"], "scope": SCOPE})
    if "device_code" not in device:
        sys.exit(f"Google refused the sign-in request: {device.get('error_description') or device.get('error')}")
    print(f"Open {device['verification_url']} and enter the code {device['user_code']}")

    deadline = time.time() + device["expires_in"]
    while time.time() < deadline:
        time.sleep(device.get("interval", 5))
        token = post_form(TOKEN_URL, {**client(), "device_code": device["device_code"],
                                      "grant_type": "urn:ietf:params:oauth:grant-type:device_code"})

        if "refresh_token" in token:
            set_env("YOUTUBE_REFRESH_TOKEN", token["refresh_token"])
            print("  + signed in; refresh token stored in .env")
            return

        if token.get("error") not in ("authorization_pending", "slow_down"):
            sys.exit(f"sign-in failed: {token.get('error_description') or token.get('error')}")

    sys.exit("sign-in timed out")


def access_token():
    token = post_form(TOKEN_URL, {**client(), "refresh_token": ENV["YOUTUBE_REFRESH_TOKEN"], "grant_type": "refresh_token"})
    if "access_token" not in token:
        sys.exit(f"Google refused the refresh token ({token.get('error')}); run --login again")

    return token["access_token"]


def api(path, token, **params):
    req = urllib.request.Request(f"{API}/{path}?{urllib.parse.urlencode(params)}",
                                 headers={"Authorization": f"Bearer {token}"})

    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def subscriptions(token):
    subs, page = [], None

    while True:
        data = api("subscriptions", token, part="snippet", mine="true", order="relevance", maxResults=50,
                   **({"pageToken": page} if page else {}))
        subs += [(i["snippet"]["resourceId"]["channelId"], i["snippet"]["title"]) for i in data["items"]]

        page = data.get("nextPageToken")
        if not page:
            return subs


def topics(token, ids):
    found = {}

    for i in range(0, len(ids), 50):
        data = api("channels", token, part="topicDetails", id=",".join(ids[i:i + 50]), maxResults=50)
        found |= {c["id"]: c.get("topicDetails", {}).get("topicCategories", []) for c in data.get("items", [])}

    return found


def tab_for(urls):
    words = " ".join(urls).lower()
    return next((tab for tab, keys in TOPICS.items() if any(k in words for k in keys)), None)


def build(subs, tags):
    pinned = {cid: tab for tab, chans in CHANNELS["pinned"].items() for cid in chans}
    lists = {tab: [] for tab in CHANNELS["limits"]}

    for first_pass in (True, False):
        for cid, title in subs:
            if cid in CHANNELS["skip"] or any(cid == c for chans in lists.values() for c, _ in chans):
                continue

            tab = pinned.get(cid) if first_pass else (None if cid in pinned else tab_for(tags.get(cid, [])))
            if tab in lists and len(lists[tab]) < CHANNELS["limits"][tab]:
                lists[tab].append((cid, title))

    rank = {cid: n for n, (cid, _) in enumerate(subs)}
    return {tab: sorted(chans, key=lambda c: rank[c[0]]) for tab, chans in lists.items()}


def write(lists, only_missing=False):
    OUT.mkdir(parents=True, exist_ok=True)
    for tab, chans in lists.items():
        path = OUT / f"youtube-{tab.lower()}.yml"
        if only_missing and path.exists():
            continue

        if not chans:
            print(f"  ! {tab}: no channels, keeping the previous list")
            continue

        text = "".join(f"- {cid} # {title}\n" for cid, title in chans)
        if path.exists() and path.read_text() == text:
            print(f"  = {tab}: {len(chans)} channels")
            continue

        with open(path, "w") as f:
            f.write(text)
        print(f"  + {tab}: {len(chans)} channels written")


if "--login" in sys.argv:
    login()
elif "--offline" in sys.argv:
    write({tab: list(chans.items()) for tab, chans in CHANNELS["pinned"].items()}, only_missing=True)
elif not ENV.get("YOUTUBE_REFRESH_TOKEN"):
    print("  ~ not signed in to YouTube; the pinned lists stay (run scripts/sync-youtube.py --login)")
else:
    token = access_token()
    subs = subscriptions(token)
    write(build(subs, topics(token, [cid for cid, _ in subs])))

    METRIC.parent.mkdir(exist_ok=True)
    METRIC.write_text(f"arr_youtube_sync_timestamp_seconds {int(time.time())}\n")
    METRIC.chmod(0o644)

    print(f"  synced from {len(subs)} subscriptions")

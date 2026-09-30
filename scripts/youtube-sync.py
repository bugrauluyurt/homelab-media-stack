#!/usr/bin/env python3
"""Keep Glance's YouTube rows in step with your subscriptions.

Runs: arr-youtube.timer hourly; stack-up with --offline; by hand once with --login.
Changes: the list files, the video rows, the metric; .env with --login.
Idempotent: yes.

Sorts your subscriptions (YouTube Data API, read-only) into the tabs of
apps/glance/youtube-channels.json (or your private copy in $CONFIG_ROOT/glance/) and writes each tab to $CONFIG_ROOT/glance/youtube-<tab>.yml.
Then writes each tab's latest uploads to $CONFIG_ROOT/glance/youtube/<tab>.json, which
Glance renders; a channel that fails keeps its previous videos.

  youtube-sync.py            sync lists and videos (the hourly arr-youtube timer)
  youtube-sync.py --login    one-time sign-in; stores YOUTUBE_REFRESH_TOKEN in .env
  youtube-sync.py --offline  write missing lists from the pinned channels and empty rows (stack-up)
"""
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from stack_env import CONFIG, ENV, REPO, STATE, require_service, set_env

require_service("glance")

SCOPE = "https://www.googleapis.com/auth/youtube.readonly"
API = "https://www.googleapis.com/youtube/v3"
TOKEN_URL = "https://oauth2.googleapis.com/token"

OUT = CONFIG / "glance"
PRIVATE_CHANNELS = OUT / "youtube-channels.json"
CHANNELS = json.loads((PRIVATE_CHANNELS if PRIVATE_CHANNELS.exists() else REPO / "apps" / "glance" / "youtube-channels.json").read_text())
FEEDS = OUT / "youtube"
METRIC = STATE / "metrics" / "youtube.prom"

VIDEOS_PER_CHANNEL = 5
VIDEOS_PER_ROW = 25
ATOM = {"atom": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}

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


def listed_channels(tab):
    path = OUT / f"youtube-{tab.lower()}.yml"
    return re.findall(r"^- (UC[\w-]{22}) # (.*)$", path.read_text(), re.M) if path.exists() else []


def video(video_id, title, channel_id, channel, published):
    published_utc = datetime.fromisoformat(published).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"id": video_id, "title": title, "channel_id": channel_id, "channel": channel, "published": published_utc}


# YouTube's RSS feed often answers 404 for hours, so a signed-in sync reads uploads through the API instead.
def api_uploads(token, channel_id, channel):
    items = api("playlistItems", token, part="snippet,contentDetails", playlistId="UULF" + channel_id[2:],
                maxResults=VIDEOS_PER_CHANNEL)["items"]

    return [video(item["contentDetails"]["videoId"], item["snippet"]["title"], channel_id, channel,
                  item["contentDetails"]["videoPublishedAt"])
            for item in items if "videoPublishedAt" in item["contentDetails"]]


def rss_uploads(channel_id, channel):
    url = f"https://www.youtube.com/feeds/videos.xml?playlist_id=UULF{channel_id[2:]}"
    with urllib.request.urlopen(url, timeout=30) as r:
        entries = ET.parse(r).getroot().findall("atom:entry", ATOM)[:VIDEOS_PER_CHANNEL]

    return [video(entry.findtext("yt:videoId", namespaces=ATOM), entry.findtext("atom:title", namespaces=ATOM),
                  channel_id, channel, entry.findtext("atom:published", namespaces=ATOM))
            for entry in entries]


def write_feeds(token):
    FEEDS.mkdir(parents=True, exist_ok=True)

    for tab in CHANNELS["limits"]:
        path = FEEDS / f"{tab.lower()}.json"
        previous_videos = json.loads(path.read_text())["videos"] if path.exists() else []
        videos, failed_channels = [], []

        for channel_id, channel in listed_channels(tab):
            try:
                videos += api_uploads(token, channel_id, channel) if token else rss_uploads(channel_id, channel)
            except (OSError, ET.ParseError, KeyError, TypeError, ValueError):
                failed_channels.append(channel)
                videos += [previous for previous in previous_videos if previous["channel_id"] == channel_id]

        row_videos = sorted(videos, key=lambda row_video: row_video["published"], reverse=True)[:VIDEOS_PER_ROW]
        text = json.dumps({"videos": row_videos}, ensure_ascii=False, indent=1) + "\n"

        if failed_channels:
            print(f"  ! {tab}: kept the last videos of unreachable channels: {', '.join(failed_channels)}")

        if path.exists() and path.read_text() == text:
            print(f"  = {tab}: {len(row_videos)} videos")
            continue

        # Renamed into place so Glance never reads half a file.
        partial = path.with_suffix(".tmp")
        partial.write_text(text)
        partial.replace(path)
        print(f"  + {tab}: {len(row_videos)} videos written")


def seed_feeds():
    FEEDS.mkdir(parents=True, exist_ok=True)

    for tab in CHANNELS["limits"]:
        path = FEEDS / f"{tab.lower()}.json"
        if not path.exists():
            path.write_text('{"videos": []}\n')


def main():
    if "--login" in sys.argv:
        login()
    elif "--offline" in sys.argv:
        write({tab: list(chans.items()) for tab, chans in CHANNELS["pinned"].items()}, only_missing=True)
        seed_feeds()
    else:
        token = None
        if ENV.get("YOUTUBE_REFRESH_TOKEN"):
            token = access_token()
            subs = subscriptions(token)
            write(build(subs, topics(token, [cid for cid, _ in subs])))
            print(f"  synced from {len(subs)} subscriptions")
        else:
            print("  ~ not signed in to YouTube; the pinned lists stay and videos come from its RSS feed "
                  "(run scripts/youtube-sync.py --login)")

        write_feeds(token)

        METRIC.parent.mkdir(exist_ok=True)
        METRIC.write_text(f"arr_youtube_sync_timestamp_seconds {int(time.time())}\n")
        METRIC.chmod(0o644)


if __name__ == "__main__":
    main()

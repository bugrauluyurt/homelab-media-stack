#!/usr/bin/env python3
"""Configure Radarr, Sonarr, Lidarr (with the music module) and Prowlarr.

Runs: by hand, after configure-sabnzbd.py.
Changes: API writes to Radarr, Sonarr, Lidarr and Prowlarr.
Idempotent: yes; every step checks for an existing entry first.
"""

from stack_env import ENV, NTFY_SERVER, arr_key as api_key, enabled_services, http, sabnzbd_key

QBIT_HOST, QBIT_PORT = "gluetun", int(ENV["QBIT_PORT"])

APPS = {
    "radarr":   {"port": 7878, "api": "v3", "root": "/data/media/movies", "cat": "radarr"},
    "sonarr":   {"port": 8989, "api": "v3", "root": "/data/media/tv",     "cat": "sonarr"},
    "lidarr":   {"port": 8686, "api": "v1", "root": "/data/media/music",  "cat": "music"},
    "prowlarr": {"port": 9696, "api": "v1"},
}
CATEGORY_FIELD = {"radarr": "movieCategory", "sonarr": "tvCategory", "lidarr": "musicCategory"}

# Newznab categories each app syncs from Prowlarr: movies, TV, audio.
SYNC_CATEGORIES = {"radarr": [2000, 2010, 2020, 2030, 2040, 2045, 2050, 2060],
                   "sonarr": [5000, 5010, 5020, 5030, 5040, 5045, 5050],
                   "lidarr": [3000, 3010, 3020, 3030, 3040, 3050, 3060]}

# Prowlarr's Newznab preset name -> the .env key that turns it on.
USENET_INDEXERS = {"NZBgeek": "NZBGEEK_API_KEY", "NZBFinder": "NZBFINDER_API_KEY"}


def call(app, method, path, body=None):
    cfg = APPS[app]
    return http(f"http://127.0.0.1:{cfg['port']}/api/{cfg['api']}{path}", body, method,
                {"X-Api-Key": api_key(app)}, timeout=30)


def ensure_root_folder(app):
    root = APPS[app]["root"]
    existing = call(app, "GET", "/rootfolder") or []
    if any(f["path"] == root for f in existing):
        print(f"  = {app}: root folder {root} already set")
        return

    body = {"path": root}
    if app == "lidarr":
        # Lidarr root folders carry the defaults new artists get.
        profile = next(p["id"] for p in call(app, "GET", "/qualityprofile") if p["name"] == "Standard")
        metadata = next(p["id"] for p in call(app, "GET", "/metadataprofile") if p["name"] == "Standard")
        body.update({"name": "Music", "defaultQualityProfileId": profile,
                     "defaultMetadataProfileId": metadata, "defaultMonitorOption": "none",
                     "defaultNewItemMonitorOption": "none", "defaultTags": []})

    call(app, "POST", "/rootfolder", body)
    print(f"  + {app}: added root folder {root}")


def ensure_hardlinks(app):
    mm = call(app, "GET", "/config/mediamanagement")
    changes = {"importExtraFiles": True, "copyUsingHardlinks": True,
               "enableMediaInfo": True, "recycleBin": ""}
    if all(mm.get(k) == v for k, v in changes.items()):
        print(f"  = {app}: media management already correct")
        return

    mm.update(changes)
    call(app, "PUT", f"/config/mediamanagement/{mm['id']}", mm)
    print(f"  + {app}: hardlinks enabled")


def ensure_download_client(app):
    cat = APPS[app]["cat"]
    existing = call(app, "GET", "/downloadclient") or []
    if any(c["name"] == "qBittorrent" for c in existing):
        print(f"  = {app}: download client already configured")
        return

    body = {
        "enable": True, "protocol": "torrent", "priority": 1,
        "name": "qBittorrent", "implementation": "QBittorrent",
        "implementationName": "qBittorrent", "configContract": "QBittorrentSettings",
        "fields": [
            {"name": "host", "value": QBIT_HOST},
            {"name": "port", "value": QBIT_PORT},
            {"name": "useSsl", "value": False},
            {"name": "urlBase", "value": ""},
            {"name": "username", "value": ""},
            {"name": "password", "value": ""},
            {"name": CATEGORY_FIELD[app], "value": cat},
            {"name": "initialState", "value": 0},
            {"name": "sequentialOrder", "value": False},
            {"name": "firstAndLast", "value": False},
        ],
        "tags": [],
    }

    # forceSave: qBittorrent is unreachable until the VPN key is supplied.
    call(app, "POST", "/downloadclient?forceSave=true", body)
    print(f"  + {app}: added qBittorrent (category '{cat}')")


def ensure_prowlarr_app(app):
    """Register radarr/sonarr in Prowlarr so indexers sync automatically."""
    existing = call("prowlarr", "GET", "/applications") or []
    name = app.capitalize()
    if any(a["name"] == name for a in existing):
        print(f"  = prowlarr: {name} already linked")
        return

    port = APPS[app]["port"]
    impl = name
    body = {
        "name": name, "syncLevel": "fullSync",
        "implementation": impl, "implementationName": impl,
        "configContract": f"{impl}Settings",
        "fields": [
            {"name": "prowlarrUrl", "value": "http://prowlarr:9696"},
            {"name": "baseUrl", "value": f"http://{app}:{port}"},
            {"name": "apiKey", "value": api_key(app)},
            {"name": "syncCategories", "value": SYNC_CATEGORIES[app]},
        ],
        "tags": [],
    }

    call("prowlarr", "POST", "/applications?forceSave=true", body)
    print(f"  + prowlarr: linked {name}")


def ensure_sabnzbd_client(app):
    """Usenet download client. Skipped until USENET_HOST is set in .env."""
    if not ENV.get("USENET_HOST"):
        return

    if any(c["implementation"] == "Sabnzbd" for c in call(app, "GET", "/downloadclient") or []):
        print(f"  = {app}: SABnzbd already configured")
        return

    sab_key = sabnzbd_key()
    schema = next(x for x in call(app, "GET", "/downloadclient/schema") if x["implementation"] == "Sabnzbd")

    values = {"host": "sabnzbd", "port": 8080, "apiKey": sab_key, "useSsl": False,
              CATEGORY_FIELD[app]: {"lidarr": "music", "radarr": "movies", "sonarr": "tv"}[app]}
    body = {**schema, "name": "SABnzbd", "enable": True, "priority": 1,
            "fields": [{**f, "value": values.get(f["name"], f.get("value"))} for f in schema["fields"]]}

    call(app, "POST", "/downloadclient?forceSave=true", body)
    print(f"  + {app}: added SABnzbd")


TORRENT_DELAY = 60  # minutes torrents wait, so a Usenet release can win first


def ensure_delay_profile(app):
    """Prefer Usenet over torrents (and, in Lidarr, Soulseek over both)."""
    profile = next(d for d in call(app, "GET", "/delayprofile") if d["id"] == 1)

    if app == "lidarr":
        order = ["SoulseekDownloadProtocol", "UsenetDownloadProtocol", "TorrentDownloadProtocol"]
        items = sorted(profile["items"], key=lambda i: order.index(i["protocol"]) if i["protocol"] in order else 99)

        for i in items:
            if i["protocol"] in order:
                i["allowed"] = True
            if i["protocol"] == "TorrentDownloadProtocol":
                i["delay"] = TORRENT_DELAY

        wanted = {**profile, "items": items, "bypassIfHighestQuality": False}
    else:
        wanted = {**profile, "enableUsenet": True, "enableTorrent": True, "preferredProtocol": "usenet",
                  "usenetDelay": 0, "torrentDelay": TORRENT_DELAY, "bypassIfHighestQuality": False}

    if wanted == profile:
        print(f"  = {app}: delay profile already prefers usenet")
        return

    call(app, "PUT", "/delayprofile/1", wanted)
    print(f"  + {app}: delay profile set ({'Soulseek, then ' if app == 'lidarr' else ''}Usenet first, torrents after {TORRENT_DELAY} min)")


def ensure_usenet_indexers():
    """Usenet indexers in Prowlarr, each once its API key is set; Prowlarr syncs them to every linked app."""
    existing_indexer_names = {indexer["name"] for indexer in call("prowlarr", "GET", "/indexer") or []}
    schema = None

    for indexer_name, env_key in USENET_INDEXERS.items():
        if not ENV.get(env_key):
            continue

        if indexer_name in existing_indexer_names:
            print(f"  = prowlarr: {indexer_name} already added")
            continue

        schema = schema or call("prowlarr", "GET", "/indexer/schema")
        preset = next(template for template in schema
                      if template["implementation"] == "Newznab" and template.get("name") == indexer_name)
        body = {**preset, "name": indexer_name, "enable": True, "appProfileId": 1,
                "fields": [{**field, "value": ENV[env_key] if field["name"] == "apiKey" else field.get("value")}
                           for field in preset["fields"]]}

        call("prowlarr", "POST", "/indexer", body)
        print(f"  + prowlarr: added {indexer_name}")


AD_FORMAT = "Audio Description"
AD_SCORE = -10000
PROFILE = {"radarr": "HD Bluray + WEB", "sonarr": "WEB-1080p"}


def ensure_audio_description_penalty(app):
    """Reject releases whose only audio is an audio-description track.

    Bare "AD" is deliberately not matched: it would hit titles like "AD Astra".
    recyclarr.yml must keep this format under reset_unmatched_scores.except, or
    the nightly sync resets the score to 0.
    """
    fmts = call(app, "GET", "/customformat") or []
    fmt = next((f for f in fmts if f["name"] == AD_FORMAT), None)
    if not fmt:
        fmt = call(app, "POST", "/customformat", {
            "name": AD_FORMAT, "includeCustomFormatWhenRenaming": False,
            "specifications": [{
                "name": AD_FORMAT, "implementation": "ReleaseTitleSpecification",
                "negate": False, "required": True,
                "fields": [{"name": "value", "value": r"\bAudio[ ._-]?Description\b"}]}]})
        print(f"  + {app}: created '{AD_FORMAT}' format")

    prof = next(p for p in call(app, "GET", "/qualityprofile") if p["name"] == PROFILE[app])
    item = next(i for i in prof["formatItems"] if i["format"] == fmt["id"])
    if item["score"] == AD_SCORE:
        print(f"  = {app}: '{AD_FORMAT}' already {AD_SCORE}")
        return

    item["score"] = AD_SCORE
    call(app, "PUT", f"/qualityprofile/{prof['id']}", prof)
    print(f"  + {app}: '{AD_FORMAT}' scored {AD_SCORE}")


def ensure_jellyfin_connect(app):
    """Tell Jellyfin to rescan the moment something is imported.

    Its real-time folder watching is off so the drive can sleep; without this,
    new downloads wait for the 12-hourly scheduled scan.
    """
    if any(n["name"] == "Jellyfin" for n in call(app, "GET", "/notification") or []):
        print(f"  = {app}: Jellyfin connection already configured")
        return

    schema = next(x for x in call(app, "GET", "/notification/schema")
                  if x["implementation"] == "MediaBrowser")
    body = dict(schema)
    body.update({"name": "Jellyfin", "tags": [], "onDownload": True, "onUpgrade": True,
                 "onRename": True})

    for key in ("onSeriesDelete", "onEpisodeFileDelete", "onMovieDelete", "onMovieFileDelete"):
        if key in body:
            body[key] = True

    values = {"host": "jellyfin", "port": 8096, "useSsl": False,
              "apiKey": ENV["JELLYFIN_API_KEY"], "updateLibrary": True, "notify": False}
    for f in body["fields"]:
        if f["name"] in values:
            f["value"] = values[f["name"]]

    call(app, "POST", "/notification", body)
    print(f"  + {app}: Jellyfin refreshes on import")


SERIES_FOLDER = "{Series Title} [tvdbid-{TvdbId}]"


def ensure_series_folder_id():
    """Put the TVDB id in new series folder names so Jellyfin matches the right show.

    Sonarr uses the English title, which matches nothing for a show Jellyfin knows
    only by its own title. Only new series get the new name.
    """
    naming = call("sonarr", "GET", "/config/naming")
    if naming["seriesFolderFormat"] == SERIES_FOLDER:
        print("  = sonarr: series folders carry the TVDB id")
        return

    call("sonarr", "PUT", f"/config/naming/{naming['id']}", {**naming, "seriesFolderFormat": SERIES_FOLDER})
    print(f"  + sonarr: series folders named '{SERIES_FOLDER}'")


def ensure_french_delay_profile():
    """French series grab torrents at once: their new episodes come from the ratio trackers, where an early grab earns ratio."""
    french_tag_id = next(tag["id"] for tag in call("sonarr", "GET", "/tag") if tag["label"] == "french")
    wanted = {"enableUsenet": True, "enableTorrent": True, "preferredProtocol": "usenet",
              "usenetDelay": 0, "torrentDelay": 0, "bypassIfHighestQuality": False, "tags": [french_tag_id]}
    french_profile = next((profile for profile in call("sonarr", "GET", "/delayprofile")
                           if profile["tags"] == [french_tag_id]), None)

    if french_profile and {**french_profile, **wanted} == french_profile:
        print("  = sonarr: French series grab torrents without delay")
        return

    if french_profile:
        call("sonarr", "PUT", f"/delayprofile/{french_profile['id']}", {**french_profile, **wanted})
    else:
        call("sonarr", "POST", "/delayprofile", wanted)

    print("  + sonarr: French series grab torrents without delay")


def ensure_french_tag():
    """Tag French-language series 'french', which picks Bazarr's French subtitle profile."""
    if any(a["name"] == "french" for a in call("sonarr", "GET", "/autotagging")):
        print("  = sonarr: French-language series auto-tagged 'french'")
        return

    tag = next((t["id"] for t in call("sonarr", "GET", "/tag") if t["label"] == "french"), None) \
        or call("sonarr", "POST", "/tag", {"label": "french"})["id"]

    spec = next(x for x in call("sonarr", "GET", "/autotagging/schema")
                if x["implementation"] == "OriginalLanguageSpecification")
    spec = {**spec, "name": "French original language", "required": True, "negate": False,
            "fields": [{**f, "value": 2} for f in spec["fields"]]}

    call("sonarr", "POST", "/autotagging", {"name": "french", "removeTagsAutomatically": True,
                                           "tags": [tag], "specifications": [spec]})
    print("  + sonarr: French-language series auto-tagged 'french'")


def ensure_music_on_request():
    """Music downloads only what the user monitors by hand.

    Import lists stay off: they grabbed albums nobody asked for and slowed every
    artist refresh. Music comes from what Needle or the user asks for.
    """
    off = {"enableAutomaticAdd": False, "shouldMonitor": "none", "monitorNewItems": "none", "shouldSearch": False}
    for lst in call("lidarr", "GET", "/importlist"):
        if all(lst.get(k) == v for k, v in off.items()):
            print(f"  = lidarr: import list '{lst['name']}' off")
            continue
        call("lidarr", "PUT", f"/importlist/{lst['id']}?forceSave=true", {**lst, **off})
        print(f"  + lidarr: import list '{lst['name']}' off")

    defaults = {"defaultMonitorOption": "none", "defaultNewItemMonitorOption": "none"}
    for root in call("lidarr", "GET", "/rootfolder"):
        if all(root.get(k) == v for k, v in defaults.items()):
            print(f"  = lidarr: new artists in {root['path']} start unmonitored")
            continue
        call("lidarr", "PUT", f"/rootfolder/{root['id']}", {**root, **defaults})
        print(f"  + lidarr: new artists in {root['path']} start unmonitored")


NTFY_EVENTS = ("onHealthIssue", "onManualInteractionRequired", "onDownloadFailure", "onImportFailure")


def ensure_ntfy(app):
    """Push errors that need a person to ntfy: health errors, stuck imports, failed downloads."""
    if not ENV.get("NTFY_TOPIC"):
        return

    if any(n["implementation"] == "Ntfy" for n in call(app, "GET", "/notification")):
        print(f"  = {app}: ntfy alerts already configured")
        return

    schema = next(x for x in call(app, "GET", "/notification/schema") if x["implementation"] == "Ntfy")
    values = {"serverUrl": NTFY_SERVER, "topics": [ENV["NTFY_TOPIC"]],
              "tags": ["warning"]}
    body = {**schema, "name": "ntfy", "tags": [], "includeHealthWarnings": False,
            **{e: True for e in NTFY_EVENTS if e in schema},
            "fields": [{**f, "value": values.get(f["name"], f.get("value"))} for f in schema["fields"]]}

    call(app, "POST", "/notification", body)
    print(f"  + {app}: ntfy alerts for {', '.join(e for e in NTFY_EVENTS if e in schema)}")


if __name__ == "__main__":
    for a in ("radarr", "sonarr"):
        print(f"[{a}]")
        ensure_root_folder(a)
        ensure_hardlinks(a)
        ensure_download_client(a)
        ensure_sabnzbd_client(a)
        ensure_delay_profile(a)
        ensure_jellyfin_connect(a)
        ensure_audio_description_penalty(a)
        ensure_ntfy(a)

    ensure_series_folder_id()
    ensure_french_tag()
    ensure_french_delay_profile()

    music = "lidarr" in enabled_services()
    if music:
        print("[lidarr]")
        ensure_root_folder("lidarr")
        ensure_hardlinks("lidarr")
        ensure_download_client("lidarr")
        ensure_sabnzbd_client("lidarr")
        ensure_delay_profile("lidarr")
        ensure_music_on_request()
        ensure_ntfy("lidarr")

    print("[prowlarr]")
    for a in ("radarr", "sonarr", *(("lidarr",) if music else ())):
        ensure_prowlarr_app(a)
    ensure_usenet_indexers()
    ensure_ntfy("prowlarr")

    print("\nDone.")

#!/usr/bin/env python3
"""Set up Jellyfin's plugins and look: the Abyss theme, Home Screen Sections,
Jellyfin Enhanced and Open Subtitles. Abyss's Spotlight banner comes from apps/jellyfin/custom-cont-init.d.
With HWACCEL in .env (and compose.gpu.yml), also hardware transcoding.

Runs: by hand, after configure-seerr.py; again after changing TMDB_API_KEY, MDBLIST_API_KEY,
  OPENSUBTITLES_USER, OPENSUBTITLES_PASS or HWACCEL.
Changes: Jellyfin API and viewer subtitle permissions; docker restart jellyfin only when a plugin
  was added or removed or is not yet active.
Idempotent: yes.
"""
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from stack_env import ENV, http, jellyfin_headers

BASE = "http://127.0.0.1:8096"
AUTH = jellyfin_headers()

REPOS = {"IAmParadox27": "https://www.iamparadox.dev/jellyfin/plugins/manifest.json",
         "n00bcodr": "https://raw.githubusercontent.com/n00bcodr/jellyfin-plugins/main/manifest.json",
         "Neptune": "https://plugins.neptuneplayer.com/manifest.json",
         "Jellyfin Stable": "https://repo.jellyfin.org/files/plugin/manifest.json"}
PLUGINS = {"File Transformation": ("5e87cc92-571a-4d8d-8d98-d2d4147f9f90", "IAmParadox27"),
           "Plugin Pages": ("5b6550fa-a014-4f4c-8a2c-59a43680ac6d", "IAmParadox27"),
           "Home Screen Sections": ("b8298e01-2697-407a-b44d-aa8dc795e850", "IAmParadox27"),
           "Jellyfin Enhanced": ("f69e946a-4b3c-4e9a-8f0a-8d7c1b2c4d9b", "n00bcodr"),
           # Server side of the Neptune tvOS app; it installs these itself, they
           # are listed so a rebuilt server gets them back.
           "Neptune Indexers": ("91d87e32-ea5f-4d33-830c-b6eea8754064", "Neptune"),
           "Neptune MDM": ("f47b4d88-74a2-459a-a0d6-b211d773f89a", "Neptune"),
           "TMDb Box Sets": ("bc4aad2e-d3d0-4725-a5e2-fd07949e5b42", "Jellyfin Stable"),
           "Fanart": ("170a157f-ac6c-437a-abdd-ca9c25cebd39", "Jellyfin Stable"),
           "Trakt": ("4fe3201e-d6ae-4f2e-8917-e12bda571281", "Jellyfin Stable")}

SUBTITLE_CREDENTIALS = {"Username": ENV.get("OPENSUBTITLES_USER", ""),
                        "Password": ENV.get("OPENSUBTITLES_PASS", "")}

if all(SUBTITLE_CREDENTIALS.values()):
    PLUGINS["Open Subtitles"] = ("4b9ed42f-5185-48b5-9803-6ff2989014c4", "Jellyfin Stable")

UNWANTED = {"SeerrFin": "c8e4f2a19b3d4e7fa6c21d5e8f0a3b7c", "Intro Skipper": "c83d86bba1e04c35a113e2101cf4ee6b"}
UNWANTED_REPOS = {"https://raw.githubusercontent.com/varunaditya-plus/SeerrFin/main/manifest.json",
                  "https://intro-skipper.org/manifest.json"}

CSS = "@import url('https://cdn.jsdelivr.net/gh/AumGupta/abyss-jellyfin@main/abyss.css');"
EXTERNAL = ENV["TAILSCALE_IP"]
# Every address Jellyfin is opened on (from Homepage's allow-list), so links to
# Seerr point at the same host the browser already reached.
HOSTS = [h.split(":")[0] for h in ENV["HOMEPAGE_ALLOWED_HOSTS"].split(",")]
SEERR = {"url": "http://seerr:5055", "key": ENV["SEERR_API_KEY"]}

# (section id, max times it may appear, card shape), top to bottom. OrderIndex must have no gaps:
# HSS 3.0.2 returns an empty home screen if index 0 is followed by anything other than 1.
HOME_ROWS = [("ContinueWatching", 1, "Landscape"), ("NextUp", 1, "Landscape"), ("TopTen", 1, "Portrait"),
             ("BecauseYouWatched", 3, "Portrait"), ("Discover", 1, "Portrait"),
             ("RecentlyAddedMovies", 1, "Portrait"), ("RecentlyAddedShows", 1, "Portrait"),
             ("Genre", 2, "Portrait"), ("DiscoverMovies", 1, "Portrait"), ("DiscoverTV", 1, "Portrait"),
             ("UpcomingShows", 1, "Portrait"), ("UpcomingMovies", 1, "Portrait"), ("MyList", 1, "Portrait"),
             ("MyJellyseerrRequests", 1, "Portrait"), ("WatchAgain", 1, "Portrait")]

ARR = {name: {"url": f"http://{name.lower()}:{port}", "key": ENV.get(f"{name.upper()}_API_KEY", ""),
              "external": f"http://{EXTERNAL}:{port}"}
       for name, port in (("Sonarr", 8989), ("Radarr", 7878), ("Bazarr", 6767))}


def req(path, body=None, method=None):
    return http(BASE + path, body, method, AUTH)


def wait_for_server():
    for _ in range(60):
        try:
            urllib.request.urlopen(urllib.request.Request(BASE + "/System/Info", headers=AUTH), timeout=5)
            return
        except OSError:
            time.sleep(2)

    sys.exit("Jellyfin did not come back up")


wait_for_server()

repos = req("/Repositories")
missing = [name for name, url in REPOS.items() if all(r["Url"] != url for r in repos)]
kept = [r for r in repos if r["Url"] not in UNWANTED_REPOS]
if missing or len(kept) != len(repos):
    req("/Repositories", kept + [{"Name": n, "Url": REPOS[n], "Enabled": True} for n in missing])

for name in REPOS:
    print(f"  {'+ added' if name in missing else '= already added'} repo {name}")


def plugin_status():
    return {p["Id"]: p["Status"] for p in req("/Plugins")}


GUIDS = {name: guid.replace("-", "") for name, (guid, _) in PLUGINS.items()}
status = plugin_status()

for name, (guid, repo) in PLUGINS.items():
    if GUIDS[name] in status:
        print(f"  = {name} already installed")
        continue
    q = urllib.parse.urlencode({"assemblyGuid": guid, "repositoryUrl": REPOS[repo]})
    req(f"/Packages/Installed/{urllib.parse.quote(name)}?{q}", method="POST")
    print(f"  + installing {name}")

removed = [name for name, guid in UNWANTED.items() if status.get(guid) not in (None, "Deleted")]
for name in removed:
    req(f"/Plugins/{UNWANTED[name]}", method="DELETE")
    print(f"  - uninstalled {name}")

branding = req("/System/Configuration/branding")
if branding.get("CustomCss") == CSS:
    print("  = Abyss theme already set")
else:
    req("/System/Configuration/branding", {**branding, "CustomCss": CSS})
    print("  + set Abyss theme (Custom CSS)")

# Shown in apps and on the web header; Jellyfin defaults to the container's hostname.
server_name = ENV.get("JELLYFIN_SERVER_NAME", "Home Media")
system = req("/System/Configuration")
if system.get("ServerName") == server_name:
    print(f"  = server name '{server_name}'")
else:
    req("/System/Configuration", {**system, "ServerName": server_name})
    print(f"  + server name '{server_name}'")

for _ in range(90):
    status = plugin_status()
    if all(g in status for g in GUIDS.values()):
        break
    time.sleep(2)
else:
    sys.exit("plugins did not finish downloading")

if removed or any(status[g] != "Active" for g in GUIDS.values()):
    subprocess.run(["docker", "restart", "jellyfin"], check=True, capture_output=True)
    wait_for_server()
    print("  + restarted Jellyfin to load plugin changes")


def configure(name, overrides):
    path = f"/Plugins/{GUIDS[name]}/Configuration"
    cfg = req(path)
    wanted = {**cfg, **{k: {**cfg[k], **v} if isinstance(v, dict) else v for k, v in overrides.items()}}

    if name == "Open Subtitles" and any(cfg.get(credential_name) != credential_value
                                        for credential_name, credential_value in overrides.items()):
        wanted["CredentialsInvalid"] = False

    if wanted == cfg:
        print(f"  = {name} already configured")
    else:
        req(path, wanted)
        print(f"  + configured {name}")


if "Open Subtitles" in PLUGINS:
    configure("Open Subtitles", SUBTITLE_CREDENTIALS)

    for viewer_user in req("/Users"):
        viewer_policy = viewer_user["Policy"]

        if viewer_policy.get("IsAdministrator") or viewer_policy.get("IsDisabled"):
            continue

        if viewer_policy.get("EnableSubtitleManagement"):
            print(f"  = subtitle permissions for '{viewer_user['Name']}'")
        else:
            req(f"/Users/{viewer_user['Id']}/Policy", {**viewer_policy, "EnableSubtitleManagement": True})
            print(f"  + subtitle permissions for '{viewer_user['Name']}'")
else:
    print("  ~ Open Subtitles skipped (set OPENSUBTITLES_USER and OPENSUBTITLES_PASS in .env)")


libraries = {f["CollectionType"]: f["ItemId"] for f in req("/Library/VirtualFolders")}

configure("Home Screen Sections", {
    "Enabled": True,
    "JellyseerrUrl": SEERR["url"], "JellyseerrApiKey": SEERR["key"],
    "JellyseerrExternalUrl": f"http://{EXTERNAL}:5055",
    "DefaultMoviesLibraryId": libraries["movies"], "DefaultTVShowsLibraryId": libraries["tvshows"],
    "OverrideStreamyfinHome": True,
    "SectionSettings": [{"SectionId": sid, "Enabled": True, "AllowUserOverride": True, "LowerLimit": 1,
                         "UpperLimit": limit, "OrderIndex": i, "ViewMode": view,
                         "HideWatchedItems": False, "PluginConfigurations": []}
                        for i, (sid, limit, view) in enumerate(HOME_ROWS)],
    **{name: {"Url": ARR[name]["url"], "ApiKey": ARR[name]["key"]} for name in ("Sonarr", "Radarr")},
})

configure("Jellyfin Enhanced", {
    "JellyseerrEnabled": True, "JellyseerrUrls": SEERR["url"], "JellyseerrApiKey": SEERR["key"],
    "JellyseerrUrlMappings": "\n".join(f"http://{h}:8096|http://{h}:5055" for h in HOSTS),
    "JellyseerrShowRecommended": True, "JellyseerrShowSimilar": True, "JellyseerrExcludeLibraryItems": True,
    "ArrLinksEnabled": True,
    **{f"{name}Url": arr["url"] for name, arr in ARR.items()},
    **{f"{name}ApiKey": arr["key"] for name, arr in ARR.items() if name != "Bazarr"},
    **{f"{name}UrlMappings": f"{arr['url']}|{arr['external']}" for name, arr in ARR.items()},
    "AutoSkipIntro": False, "AutoSkipOutro": False,
    "QualityTagsEnabled": True, "RatingTagsEnabled": True,
    "TMDB_API_KEY": ENV.get("TMDB_API_KEY", ""),
    "MdblistApiKey": ENV.get("MDBLIST_API_KEY", ""),
    **{k: bool(ENV.get("MDBLIST_API_KEY")) for k in ("MdblistRatingsEnabled", "MdblistRatingsFetchEnabled")},
    **{f"{page}PageEnabled": True for page in ("Calendar", "Downloads", "Recommendations")},
    **{f"{page}UsePluginPages": True for page in ("Calendar", "Downloads", "Recommendations")},
})

hwaccel = ENV.get("HWACCEL")
if not hwaccel:
    print("  ~ hardware transcoding skipped (set HWACCEL in .env)")
else:
    encoding = req("/System/Configuration/encoding")

    # ponytail: h264, hevc and vp9 decode on any VAAPI/QSV GPU from about 2016 on; add av1 for newer ones.
    wanted_encoding = {**encoding, "HardwareAccelerationType": hwaccel, "VaapiDevice": "/dev/dri/renderD128",
                       "EnableHardwareEncoding": True, "EnableDecodingColorDepth10Hevc": True,
                       "HardwareDecodingCodecs": ["h264", "hevc", "vp9"]}

    if wanted_encoding == encoding:
        print(f"  = hardware transcoding ({hwaccel})")
    else:
        req("/System/Configuration/encoding", wanted_encoding)
        print(f"  + hardware transcoding ({hwaccel})")

# Box Sets only builds collections on its scheduled run; run it once on a fresh
# install so they appear straight away.
box_sets = next((t for t in req("/ScheduledTasks") if "box set" in t["Name"].lower()), None)
if box_sets is None:
    sys.exit("TMDb Box Sets task not found - is the plugin loaded?")

if box_sets.get("LastExecutionResult"):
    print("  = Box Sets scan has run before")
else:
    req(f"/ScheduledTasks/Running/{box_sets['Id']}", method="POST")
    print("  + started the Box Sets scan")

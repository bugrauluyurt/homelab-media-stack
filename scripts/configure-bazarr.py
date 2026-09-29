#!/usr/bin/env python3
"""Idempotently connect Bazarr to Radarr/Sonarr and enable subtitle providers.

Providers needing no account are enabled automatically. Those in ACCOUNTS
are enabled only when their .env keys are filled.
"""
import json
import re
import urllib.parse
import urllib.request

from stack_env import CONFIG as CFG, ENV, arr_key

BAZARR = "http://127.0.0.1:6767"
# name: (languages by preference, Sonarr tag that selects it). French shows get the tag from
# configure-arr.py's auto-tagging, since English subtitles for French TV rarely exist.
PROFILES = {"English": (["en"], None), "French audio": (["fr", "en"], "french")}


def bazarr_key():
    s = open(f"{CFG}/bazarr/config/config.yaml").read()
    m = re.search(r"^\s+apikey:\s*(\S+)", s, re.M)
    return m.group(1).strip("\"'")


KEY = bazarr_key()


def get(path):
    req = urllib.request.Request(BAZARR + path, headers={"X-API-KEY": KEY})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
        return json.loads(raw) if raw else None


def post_settings(pairs):
    """Bazarr's settings endpoint takes form-encoded data, repeating keys for lists."""
    body = urllib.parse.urlencode(pairs, doseq=True).encode()
    req = urllib.request.Request(BAZARR + "/api/system/settings", data=body,
                                 method="POST", headers={"X-API-KEY": KEY})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.status


# Don't re-add podnapisi (gone upstream), tvsubtitles (domain dead) or subf2m (HTTP 500 on
# every search): each cost every search a timeout.
providers = ["yifysubtitles", "subtitlecat"]
pairs = [
    ("settings-general-use_radarr", "true"),
    ("settings-radarr-ip", "radarr"),
    ("settings-radarr-port", "7878"),
    ("settings-radarr-apikey", arr_key("radarr")),
    ("settings-radarr-ssl", "false"),
    ("settings-radarr-base_url", "/"),
    ("settings-general-use_sonarr", "true"),
    ("settings-sonarr-ip", "sonarr"),
    ("settings-sonarr-port", "8989"),
    ("settings-sonarr-apikey", arr_key("sonarr")),
    ("settings-sonarr-ssl", "false"),
    ("settings-sonarr-base_url", "/"),
    # External SRT only: image subs force a transcode this Pi can't do, and embedded ones make
    # Jellyfin read the whole video before web players can use them.
    ("settings-general-use_embedded_subs", "false"),
    ("settings-general-subfolder", "current"),
    ("settings-general-upgrade_subs", "true"),
    ("settings-general-serie_default_enabled", "true"),
    ("settings-general-serie_default_profile", "1"),
    ("settings-general-movie_default_enabled", "true"),
    ("settings-general-movie_default_profile", "1"),
    ("settings-general-serie_tag_enabled", "true"),
]

# Addic7ed is left out: Bazarr can only log in to it through a paid anti-captcha service.
ACCOUNTS = {
    "opensubtitlescom": {"username": "OPENSUBTITLES_USER", "password": "OPENSUBTITLES_PASS"},
    "subsource": {"apikey": "SUBSOURCE_API_KEY"},
}
for provider, fields in ACCOUNTS.items():
    if all(ENV.get(v) for v in fields.values()):
        providers.append(provider)
        pairs += [(f"settings-{provider}-{k}", ENV[v]) for k, v in fields.items()]
    else:
        print(f"  ~ {provider} skipped (set {'/'.join(fields.values())} in .env to enable)")

pairs.append(("settings-opensubtitlescom-use_hash", "true"))
# Machine-made subtitles: the only English there usually is for foreign TV.
pairs.append(("settings-opensubtitlescom-include_ai_translated", "true"))
pairs.append(("settings-opensubtitlescom-include_machine_translated", "true"))

pairs += [("settings-general-enabled_providers", p) for p in providers]


def stored(settings, key):
    _, section, name = key.split("-", 2)
    v = settings.get(section, {}).get(name)
    return [str(x).lower() if isinstance(x, bool) else str(x).strip("/") for x in (v if isinstance(v, list) else [v])]


wanted = {}
for k, v in pairs:
    wanted.setdefault(k, []).append(v.strip("/"))

current = get("/api/system/settings")
if all(stored(current, k) == v for k, v in wanted.items()):
    print(f"  = settings already correct; providers: {', '.join(providers)}")
else:
    post_settings(pairs)
    print(f"  + settings updated; providers: {', '.join(providers)}")

wanted_profiles = [{
    "profileId": i, "name": name, "cutoff": None, "mustContain": [], "mustNotContain": [],
    "originalFormat": 0, "tag": tag,
    "items": [{"id": j, "language": language, "audio_exclude": "False", "hi": "False", "forced": "False",
               "audio_only_include": "False"} for j, language in enumerate(langs, 1)],
} for i, (name, (langs, tag)) in enumerate(PROFILES.items(), 1)]

def summary(profiles):
    return [(profile["name"], [item["language"] for item in profile["items"]], profile["tag"]) for profile in profiles]


if summary(get("/api/system/languages/profiles") or []) == summary(wanted_profiles):
    print(f"  = language profiles: {', '.join(PROFILES)}")
else:
    post_settings([("languages-profiles", json.dumps(wanted_profiles))])
    print(f"  + language profiles: {', '.join(PROFILES)}")

print("Done.")

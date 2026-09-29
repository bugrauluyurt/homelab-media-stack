#!/usr/bin/env python3
"""Apply Plex preferences that keep this Pi on Direct Play. Safe to re-run.

Plex rewrites Preferences.xml when it exits, so the container is stopped while the
file is written, and only when something needs changing.
"""
import subprocess
import sys
import xml.etree.ElementTree as ET

from stack_env import CONFIG, ENV, REPO, require_service

require_service("plex")

PREF = (f"{CONFIG}/plex/Library/Application Support/"
        "Plex Media Server/Preferences.xml")

PREFS = {
    # The tailnet counts as local too, else Plex caps tailnet bitrates and force-transcodes.
    "LanNetworksBandwidth": f"{ENV['LAN_CIDR']},100.64.0.0/10",
    "TranscoderTempDirectory": "/transcode",
    # The media drive is a spinning disk powered off by hand; inotify would keep waking it.
    "FSEventLibraryUpdatesEnabled": "0",
    "FSEventLibraryPartialScanEnabled": "0",
    "ScheduledLibraryUpdatesEnabled": "1",
    "ScheduledLibraryUpdateInterval": "86400",
    "autoEmptyTrash": "0",
    "GenerateBIFBehavior": "never",
    "GenerateChapterThumbBehavior": "never",
    "LoudnessAnalysisBehavior": "never",
}


def read():
    raw = subprocess.run(["sudo", "cat", PREF], capture_output=True, text=True).stdout

    if not raw.strip():
        sys.exit("could not read Preferences.xml")

    return ET.fromstring(raw)


def compose(action):
    subprocess.run(["docker", "compose", action, "plex"], check=True, capture_output=True, cwd=REPO)


def main():
    if all(read().get(k) == v for k, v in PREFS.items()):
        print("  = already correct")
        return

    compose("stop")

    root = read()
    changed = [k for k, v in PREFS.items() if root.get(k) != v]
    for k in changed:
        root.set(k, PREFS[k])

    out = ET.tostring(root, encoding="unicode")
    subprocess.run(["sudo", "tee", PREF], input=f"<?xml version=\"1.0\" encoding=\"utf-8\"?>\n{out}",
                   text=True, capture_output=True, check=True)

    compose("start")
    print(f"  + updated: {', '.join(changed)} (plex restarted)")


if __name__ == "__main__":
    main()

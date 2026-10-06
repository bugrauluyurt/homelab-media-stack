#!/usr/bin/env bash
# Runs: on every Jellyfin container start, before the server.
# Changes: Jellyfin's web loader and subtitle download script.
# Idempotent: yes.
set -euo pipefail

web_root=${1:-/usr/share/jellyfin/web}
index_file="$web_root/index.html"
script_directory=$(cd "$(dirname "$0")" && pwd)
subtitle_source="$script_directory/assets/subtitle-downloads.js"

if [ ! -f "$index_file" ] || ! grep -q '</body>' "$index_file"; then
    printf '! subtitle downloads skipped: Jellyfin web layout is unsupported\n'
    exit 0
fi

script_hash=$(sha256sum "$subtitle_source" | cut -d ' ' -f 1)
loader_tag="<script src=\"ui/subtitle-downloads.js?v=$script_hash\" type=\"module\" data-subtitle-downloads></script>"
index_html=$(sed -E 's#<script src="ui/subtitle-downloads\.js[^"]*" type="module" data-subtitle-downloads></script>##g' "$index_file")
index_html=${index_html/<\/body>/$loader_tag<\/body>}
subtitle_assets_changed=false

mkdir -p "$web_root/ui"

if ! cmp -s "$subtitle_source" "$web_root/ui/subtitle-downloads.js"; then
    cp "$subtitle_source" "$web_root/ui/subtitle-downloads.js.tmp"
    mv -f "$web_root/ui/subtitle-downloads.js.tmp" "$web_root/ui/subtitle-downloads.js"
    subtitle_assets_changed=true
fi

temporary_index="$index_file.subtitles.tmp"
cp -p "$index_file" "$temporary_index"
printf '%s\n' "$index_html" > "$temporary_index"

if cmp -s "$index_file" "$temporary_index"; then
    rm -f "$temporary_index"
else
    mv -f "$temporary_index" "$index_file"
    subtitle_assets_changed=true
fi

if "$subtitle_assets_changed"; then
    printf '+ subtitle download button loaded\n'
else
    printf '= subtitle download button already loaded\n'
fi

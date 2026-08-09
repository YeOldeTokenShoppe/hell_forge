#!/bin/zsh
# One-command web build. Run after editing scripts, scenes, or .blend files:
#   tools/build_web.sh
# If you changed a .blend, close the Godot editor first (import cache lock).
set -e
cd "$(dirname "$0")/.."
GODOT="/Applications/Godot.app/Contents/MacOS/Godot"
"$GODOT" --headless --path . --import 2>/dev/null | grep -i "error" | grep -vi "tangents" || true
"$GODOT" --headless --path . --export-release "Web" build/web/index.html >/dev/null 2>&1
echo "Build done → build/web"
echo "Phone: https://$(ipconfig getifaddr en0):8443/?debug=1"

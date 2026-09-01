#!/usr/bin/env bash
# Captures the lit `level photo --game` stills mp4.py composites into the pitch video.
# Replaces the earlier undocumented manual-screenshot step: every shot here is a named,
# reproducible camera pose against the level showcase-bar.sh just built.
set -euo pipefail
cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.."
: "${UEDCLI_LEVEL:?set UEDCLI_LEVEL to the built club level (see showcase-bar.sh)}"
: "${UEDCLI_HOME:?set UEDCLI_HOME to a clean config dir}"
OUT=demo/out/mp4src/club
mkdir -p "$OUT"

bin/uedcli level photo \
  "at:0,-300,140;look:-144,510,150;name:hero-bar" \
  "at:480,-380,120;look:256,-160,-10;name:lounge-pit" \
  "at:540,120,90;look:700,300,30;name:booths" \
  --out-dir "$OUT"

echo "wrote $OUT/{hero-bar,lounge-pit,booths}.png"

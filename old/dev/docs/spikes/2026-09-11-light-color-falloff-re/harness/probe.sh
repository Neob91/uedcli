#!/usr/bin/env bash
# probe.sh — set ProbeLight's properties, rebuild+photo, sample the center pixel, append a CSV row.
# Usage: probe.sh <tag> <brightness> <hue> <saturation> <z_light>
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../../../../.." && pwd)"  # repo root (uedcli/)
cd "$ROOT"
export UEDCLI_LEVEL=lightprobe
TAG="$1"; BRI="$2"; HUE="$3"; SAT="$4"; ZL="$5"
OUT="_scratch/lightprobe/shots/$TAG"
rm -rf "$OUT"
bin/uedcli --project _scratch/lightprobe actor prop set ProbeLight_w85nba \
  LightBrightness="$BRI" LightHue="$HUE" LightSaturation="$SAT" Location="(X=0,Y=0,Z=$ZL)" >/dev/null
bin/uedcli --project _scratch/lightprobe level photo --game --rebuild --out-dir "$OUT" --size 320x240 \
  'at:0,0,180;look:0,0,-224;name:center' >"$OUT.log" 2>&1
LINE=$(python3 "$HERE/sample.py" "$OUT/center.png")
RGB=$(echo "$LINE" | sed -E 's/.*R=([0-9.]+) G=([0-9.]+) B=([0-9.]+)/\1,\2,\3/')
echo "$TAG,$BRI,$HUE,$SAT,$ZL,$RGB"

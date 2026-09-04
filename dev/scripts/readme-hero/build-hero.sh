#!/usr/bin/env bash
# Regenerate the animated README hero: docs/images/readme/build-synced.svg
#
# Runs the REAL uedcli pipeline against a throwaway scratch level, renders an
# `actor diagram` frame after each step, then assembles the synced
# terminal + diagram SVG. The commands shown in the SVG are exactly the ones run
# here, so the animation always reflects real output.
#
# Requires the dev/games sample project (not shipped publicly) and a built
# uedcli (bin/uedcli). Usage:  dev/scripts/readme-hero/build-hero.sh [OUT.svg]
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"
UED="$REPO/bin/uedcli"
P=(--project "$REPO/dev/games")
L=readme_hero_scratch
FR="-380,-360,-40,1950,360,360"
FRAMES="$(mktemp -d)"
OUT="${1:-$REPO/docs/images/readme/build-synced.svg}"
trap 'rm -rf "$FRAMES" "$REPO/dev/games/trunks/$L"' EXIT

rm -rf "$REPO/dev/games/trunks/$L"
"$UED" "${P[@]}" level create "$L" >/dev/null 2>&1
export UEDCLI_LEVEL="$L"

render(){ "$UED" "${P[@]}" actor find --exact-class Brush 2>/dev/null \
  | "$UED" "${P[@]}" actor diagram - --layout single --view iso --annotate none \
      --brush-colors csg --frame "$FR" --size 620 --out "$1" 2>/dev/null; }

# 1) room (centre z=160 so the floor sits at z=0, matching corridor + columns)
ROOM=$("$UED" "${P[@]}" brush build cube --width 640 --breadth 640 --height 320 --csg subtract --at 0,0,160 --base-name Room 2>/dev/null | "$UED" "${P[@]}" actor add - 2>/dev/null | tail -1)
render "$FRAMES/x1.png"

# 2-5) four 45-degree corner clips, each in place, each rendered
i=2
for plane in "160,320,160 1,1,0" "-160,320,160 -1,1,0" "160,-320,160 1,-1,0" "-160,-320,160 -1,-1,0"; do
  # shellcheck disable=SC2086
  "$UED" "${P[@]}" actor show "$ROOM" 2>/dev/null | "$UED" "${P[@]}" brush clip - --plane $plane --keep below 2>/dev/null | "$UED" "${P[@]}" brush replace "$ROOM" - 2>/dev/null
  render "$FRAMES/x$i.png"; i=$((i+1))
done

# 6) corridor, flush with the room walls
"$UED" "${P[@]}" brush build cube --width 640 --breadth 200 --height 320 --csg subtract --at 640,0,160 --base-name Corr 2>/dev/null | "$UED" "${P[@]}" actor add - >/dev/null 2>&1
render "$FRAMES/x6.png"

# 7) duplicate the chamfered room to the far end
"$UED" "${P[@]}" actor duplicate "$ROOM" --by 1280,0,0 >/dev/null 2>&1
render "$FRAMES/x7.png"

# 8-9) a semisolid cube column in the centre of each room
COL1=$("$UED" "${P[@]}" brush build cube --width 120 --breadth 120 --height 320 --solidity semisolid --at 0,0,160 --base-name Col 2>/dev/null | "$UED" "${P[@]}" actor add - 2>/dev/null | tail -1)
render "$FRAMES/x8.png"
COL2=$("$UED" "${P[@]}" brush build cube --width 120 --breadth 120 --height 320 --solidity semisolid --at 1280,0,160 --base-name Col 2>/dev/null | "$UED" "${P[@]}" actor add - 2>/dev/null | tail -1)
render "$FRAMES/x9.png"

# 10-11) rotate each column 45 deg IN PLACE via its Rotation prop (8192 = 45 deg)
"$UED" "${P[@]}" actor prop set "$COL1" Rotation.Yaw=8192 >/dev/null 2>&1; render "$FRAMES/x10.png"
"$UED" "${P[@]}" actor prop set "$COL2" Rotation.Yaw=8192 >/dev/null 2>&1; render "$FRAMES/x11.png"

# 12) a corridor bend off the far room's outer wall, swept 45 degrees with revolve
BEND=$("$UED" "${P[@]}" brush build revolve --point 200,0 --point 400,0 --point 400,320 --point 200,320 --angle 8192 --segments 6 --axis x --csg subtract --at 1600,-300,0 --base-name Bend 2>/dev/null | "$UED" "${P[@]}" actor add - 2>/dev/null | tail -1)
render "$FRAMES/x12.png"

python3 "$HERE/render-synced-svg.py" "$FRAMES" "$ROOM" "$COL1" "$COL2" "$BEND" "$OUT"
echo "wrote $OUT"

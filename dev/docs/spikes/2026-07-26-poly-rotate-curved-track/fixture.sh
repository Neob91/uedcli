#!/usr/bin/env bash
# Rebuild the throwaway curved-track fixture for the 2026-07-26 poly-rotate spike.
#
#   dev/docs/spikes/2026-07-26-poly-rotate-curved-track/fixture.sh
#
# Creates <repo>/_scratch/trackspike/ (gitignored) with a level `track` containing:
#   Room       - 2048^3 subtracted box, so there is somewhere to stand and something to light
#   TrackBed   - the SUBJECT: a 90 degrees revolved curved track bed, 128 uu wide, 16 thick,
#                bend centre at the world origin, its 8 top faces textured with a railway texture
#   PlayerStart + 4 Lights - required by the --game backend (no PlayerStart = refuses to render;
#                no lights = renders solid black)
#
# NOTE: `level preview --native` does NOT render a revolve at all (see README.md finding 2), so the
# only backend that shows this brush is `--game`.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
PROJ="$REPO/_scratch/trackspike"
U="$REPO/bin/uedcli"

export UEDCLI_LEVEL=track

rm -rf "$PROJ"
mkdir -p "$PROJ"
printf 'game = "deusex"\n' > "$PROJ/uedcli.toml"

P=(--project "$PROJ")
"$U" "${P[@]}" level create track

# The room: big enough that the --game camera poses below sit inside it.
"$U" "${P[@]}" brush build cube --width 2048 --breadth 2048 --height 512 --at 448,448,64 \
     --csg subtract --base-name Room | "$U" "${P[@]}" actor add -

# THE SUBJECT. --axis x puts the profile's V axis on world Z, so the sweep revolves about Z and the
# bed comes out horizontal. Profile is (radius, height): radii 512..640, height 0..16.
"$U" "${P[@]}" brush build revolve --axis x \
     --point 512,0 --point 640,0 --point 640,16 --point 512,16 \
     --angle 16384 --segments 8 --base-name TrackBed | "$U" "${P[@]}" actor add -

BED="$("$U" "${P[@]}" actor find --class Engine.Brush 2>/dev/null | grep '^TrackBed')"

# Texture the 8 top faces. Railwaytrack01 has strong directional banding, so a facet whose texture
# does not follow the bend is obvious by eye.
"$U" "${P[@]}" brush poly find "$BED" --facing +Z \
  | "$U" "${P[@]}" brush poly set - --texture CoreTexMisc.Railwaytrack01

# --game prerequisites.
"$U" "${P[@]}" actor build Engine.PlayerStart --at 900,900,-150 | "$U" "${P[@]}" actor add -
for xy in 200,600 450,450 600,200 900,900; do
  "$U" "${P[@]}" actor build Engine.Light --at "${xy},200" \
       --prop LightBrightness=110 --prop LightRadius=32 | "$U" "${P[@]}" actor add -
done

echo "fixture ready: $PROJ (level 'track', brush $BED)"

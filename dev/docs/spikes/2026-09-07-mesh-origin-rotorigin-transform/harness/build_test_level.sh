#!/usr/bin/env bash
# Reproduces the spike's live-render test level: an enclosing room, a light, two
# DeusEx.ComputerPublic actors (one identity Rotation, one counter-rotated to cancel the mesh's
# RotOrigin), and a DeusEx.CrateUnbreakableMed control. Then materializes it and shoots it with
# `level photo --game` (the faithful in-game backend — `--native` does not render meshes).
#
# Usage: harness/build_test_level.sh <repo-root> <scratch-dir> <shots-out-dir>
# e.g.:  harness/build_test_level.sh /workspace/uedcli/.claude/worktrees/<this-worktree> \
#            /tmp/mesh-xform-scratch /tmp/mesh-xform-shots
set -euo pipefail

REPO="${1:?repo root}"
SCRATCH="${2:?scratch dir}"
SHOTS="${3:?shots out dir}"
CLI="$REPO/bin/uedcli"
PROJ="$SCRATCH/proj"

mkdir -p "$PROJ/maps" "$SHOTS"
cat > "$PROJ/uedcli.toml" <<'EOF'
game = "deusex"
maps = "maps"
EOF

export UEDCLI_LEVEL=meshxform
"$CLI" --project "$PROJ" level create meshxform

# Enclosing room: 1024x1024x512 box, subtracted, centered at the origin.
"$CLI" --project "$PROJ" brush build cube --width 1024 --breadth 1024 --height 512 \
    --at 0,0,0 --csg subtract --base-name Room > "$SCRATCH/room.t3d"
"$CLI" --project "$PROJ" actor add - < "$SCRATCH/room.t3d"

# Light + the three test actors. Floor sits at Z=-256 (half the room height); each actor's Z
# places it resting on the floor (Location.Z = -256 + its mesh-local half-height).
{
  "$CLI" --project "$PROJ" actor build Engine.Light --at 0,0,150 \
      --prop LightBrightness=200 --prop LightRadius=64 --base-name SunLamp
  "$CLI" --project "$PROJ" actor build DeusEx.ComputerPublic --at -250,-200,-207 \
      --base-name CompA                                        # identity Rotation
  "$CLI" --project "$PROJ" actor build DeusEx.ComputerPublic --at -250,200,-207 \
      --rotate 0,-16384,0 --base-name CompB                     # cancels RotOrigin=(0,16384,0)
  "$CLI" --project "$PROJ" actor build DeusEx.CrateUnbreakableMed --at 200,0,-224 \
      --base-name Crate                                          # identity Origin/RotOrigin control
} > "$SCRATCH/actors.t3d"
"$CLI" --project "$PROJ" actor add - < "$SCRATCH/actors.t3d"

"$CLI" --project "$PROJ" level materialize --out "$SCRATCH/meshxform.dx" --overwrite

# Top-down over the two computers, plus a side view of each.
"$CLI" --project "$PROJ" level photo --out-dir "$SHOTS" --map "$SCRATCH/meshxform.dx" \
    --size 1024x1024 \
    'at:-250,0,120;rot:-11000,16384;name:topdown' \
    'at:-600,-200,-80;rot:0,0;name:sideA' \
    'at:-600,200,-80;rot:0,0;name:sideB'

echo "shots written to $SHOTS"

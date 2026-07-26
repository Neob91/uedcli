#!/usr/bin/env bash
# Spike driver: does plain `git merge` work as uedcli's session-merge mechanism
# for T3D trees? Builds a trunk, two disjoint-work branches, merges; then forces
# a same-actor conflict; then tests whether property reordering (non-canonical
# emit) causes a spurious conflict.
#
# All git repos/output land under _scratch (gitignored). Re-runnable: nukes WORK.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK="${1:-/home/human/src/dx_lum/_scratch/git-merge-spike}"
rm -rf "$WORK"
mkdir -p "$WORK"

git_q() { git -C "$REPO" "$@"; }

banner() { printf '\n========== %s ==========\n' "$*"; }

# ---------------------------------------------------------------------------
# Scenario 1+2+3+4: disjoint work on two branches, then merge.
# ---------------------------------------------------------------------------
REPO="$WORK/disjoint"
mkdir -p "$REPO"
git_q init -q
git_q config user.email spike@local
git_q config user.name spike
git_q config merge.conflictStyle merge   # plain <<<< ==== >>>> markers

bash "$HERE/build_tree.sh" "$REPO"
git_q add -A
git_q commit -q -m "trunk: initial T3D tree"
git_q branch trunk

banner "TRUNK actor set"
ls "$REPO/actors"

# --- Branch A: edit X=Light0 and Y=Computer0, ADD Z=Datacube0, touch order --
git_q checkout -q -b branchA trunk
# edit X: bump Light0 brightness + hue
sed -i 's/LightBrightness=180/LightBrightness=220/; s/LightHue=40/LightHue=60/' "$REPO/actors/Light0.t3d"
# edit Y: change Computer0 userName + move it
sed -i 's/userName0=admin/userName0=operator/; s/X=800.000000/X=850.000000/' "$REPO/actors/Computer0.t3d"
# ADD Z
cat > "$REPO/actors/Datacube0.t3d" <<'EOF'
Begin Actor Class=DataCube Name=Datacube0
    Location=(X=900.000000,Y=100.000000,Z=48.000000)
    Tag=Intel
    Name=Datacube0
End Actor
EOF
# append Z to order
printf 'Datacube0\n' >> "$REPO/order"
git_q add -A
git_q commit -q -m "branchA: edit Light0+Computer0, add Datacube0"

# --- Branch B: edit W=Light1, ADD V=Barrel0, touch order --------------------
git_q checkout -q -b branchB trunk
sed -i 's/LightBrightness=140/LightBrightness=90/' "$REPO/actors/Light1.t3d"
cat > "$REPO/actors/Barrel0.t3d" <<'EOF'
Begin Actor Class=Barrel Name=Barrel0
    Location=(X=-300.000000,Y=-300.000000,Z=16.000000)
    Tag=Cover
    Name=Barrel0
End Actor
EOF
printf 'Barrel0\n' >> "$REPO/order"
git_q add -A
git_q commit -q -m "branchB: edit Light1, add Barrel0"

banner "MERGE branchB into branchA (disjoint work)"
git_q checkout -q branchA
set +e
git_q merge --no-edit branchB
MERGE_RC=$?
set -e
echo "merge exit code: $MERGE_RC"

banner "git status after disjoint merge"
git_q status -s

banner "conflicted files (if any)"
git_q diff --name-only --diff-filter=U || true

banner "resulting actor set"
ls "$REPO/actors"

banner "resulting order file"
cat "$REPO/order" || true

# ---------------------------------------------------------------------------
# Scenario 5: force a SAME-actor conflict on Light0.
# ---------------------------------------------------------------------------
REPO="$WORK/same_actor"
mkdir -p "$REPO"
git_q init -q
git_q config user.email spike@local
git_q config user.name spike
git_q config merge.conflictStyle merge

bash "$HERE/build_tree.sh" "$REPO"
git_q add -A
git_q commit -q -m "trunk"
git_q branch trunk

git_q checkout -q -b editA trunk
sed -i 's/LightBrightness=180/LightBrightness=255/' "$REPO/actors/Light0.t3d"
git_q add -A; git_q commit -q -m "editA: Light0 brightness 255"

git_q checkout -q -b editB trunk
sed -i 's/LightBrightness=180/LightBrightness=64/' "$REPO/actors/Light0.t3d"
git_q add -A; git_q commit -q -m "editB: Light0 brightness 64"

banner "MERGE editB into editA (same-actor conflict expected)"
git_q checkout -q editA
set +e
git_q merge --no-edit editB
SAME_RC=$?
set -e
echo "merge exit code: $SAME_RC"

banner "conflict markers in actors/Light0.t3d"
cat "$REPO/actors/Light0.t3d"

# ---------------------------------------------------------------------------
# Scenario 6: property reordering (non-canonical emit) => spurious conflict?
# One branch reorders lines within Light1 (semantically identical); another
# makes a real edit elsewhere in the SAME file. Canonical emit would keep line
# order stable and avoid the collision.
# ---------------------------------------------------------------------------
REPO="$WORK/reorder"
mkdir -p "$REPO"
git_q init -q
git_q config user.email spike@local
git_q config user.name spike
git_q config merge.conflictStyle merge

bash "$HERE/build_tree.sh" "$REPO"
git_q add -A
git_q commit -q -m "trunk"
git_q branch trunk

# Branch reorderA: reorder properties of Light1 (Hue before Brightness), no
# semantic change. This is what a NON-canonical emitter might produce.
git_q checkout -q -b reorderA trunk
cat > "$REPO/actors/Light1.t3d" <<'EOF'
Begin Actor Class=Light Name=Light1
    Location=(X=-512.000000,Y=512.000000,Z=256.000000)
    LightHue=120
    LightBrightness=140
    Tag=CornerLight
    Name=Light1
End Actor
EOF
git_q add -A; git_q commit -q -m "reorderA: shuffle Light1 property order (no semantic change)"

# Branch editHue: a REAL edit to Light1 hue, canonical order preserved.
git_q checkout -q -b editHue trunk
sed -i 's/LightHue=120/LightHue=200/' "$REPO/actors/Light1.t3d"
git_q add -A; git_q commit -q -m "editHue: Light1 hue 120->200 (canonical order)"

banner "MERGE editHue into reorderA (semantic-noop reorder vs real edit)"
git_q checkout -q reorderA
set +e
git_q merge --no-edit editHue
REORDER_RC=$?
set -e
echo "merge exit code: $REORDER_RC"
banner "actors/Light1.t3d after reorder-vs-edit merge"
cat "$REPO/actors/Light1.t3d"

banner "SPIKE COMPLETE"
echo "disjoint merge rc=$MERGE_RC  same-actor rc=$SAME_RC  reorder rc=$REORDER_RC"

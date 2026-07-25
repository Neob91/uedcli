#!/usr/bin/env bash
# Probe: is the `order`-file conflict inherent to appends, or just tail-adjacency?
# Test A: both branches append to the tail (as in a real "add actor" flow).
# Test B: branches insert at well-separated, non-adjacent lines.
# Test C: a per-actor ordering-key model -- store order as a sortable key inside
#         each actor file instead of a shared `order` list, and merge that way.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK="${1:-/home/human/src/dx_lum/_scratch/git-merge-spike}"
mkdir -p "$WORK"

banner() { printf '\n========== %s ==========\n' "$*"; }
mkrepo() {
  REPO="$WORK/$1"; rm -rf "$REPO"; mkdir -p "$REPO"
  git -C "$REPO" init -q
  git -C "$REPO" config user.email spike@local
  git -C "$REPO" config user.name spike
  git -C "$REPO" config merge.conflictStyle merge
}
gq() { git -C "$REPO" "$@"; }

# ---- Test A: tail append vs tail append (the real "add actor" case) ---------
mkrepo order_tail
bash "$HERE/build_tree.sh" "$REPO"
gq add -A; gq commit -q -m trunk; gq branch trunk
gq checkout -q -b a1 trunk; printf 'Datacube0\n' >> "$REPO/order"; gq add -A; gq commit -q -m a1
gq checkout -q -b a2 trunk; printf 'Barrel0\n'   >> "$REPO/order"; gq add -A; gq commit -q -m a2
gq checkout -q a1
banner "Test A: tail-append vs tail-append"
set +e; gq merge --no-edit a2; echo "rc=$?"; set -e

# ---- Test B: insertions at well-separated, non-adjacent lines ---------------
mkrepo order_sep
bash "$HERE/build_tree.sh" "$REPO"
gq add -A; gq commit -q -m trunk; gq branch trunk
# b1 inserts after line 2 (top region)
gq checkout -q -b b1 trunk
sed -i '2a Datacube0' "$REPO/order"; gq add -A; gq commit -q -m b1
# b2 inserts before last line (bottom region, far from line 2)
gq checkout -q -b b2 trunk
sed -i '7a Barrel0' "$REPO/order"; gq add -A; gq commit -q -m b2
gq checkout -q b1
banner "Test B: separated insertions"
set +e; gq merge --no-edit b2; echo "rc=$?"; set -e
banner "Test B resulting order (if clean)"
cat "$REPO/order"

# ---- Test C: per-actor ordering key (no shared order file) ------------------
# Model: each actor file carries an OrderKey; there is NO `order` file. Adding an
# actor writes only its own file -> disjoint files -> no shared merge surface.
mkrepo order_key
mkdir -p "$REPO/actors"
for i in 010:Brush_Room 020:Brush_Door 030:PlayerStart0 040:Light0 050:Light1; do
  key="${i%%:*}"; nm="${i##*:}"
  printf 'Begin Actor Class=X Name=%s\n    OrderKey=%s\n    Name=%s\nEnd Actor\n' "$nm" "$key" "$nm" > "$REPO/actors/$nm.t3d"
done
printf 'DeusEx\n' > "$REPO/packages"
gq add -A; gq commit -q -m trunk; gq branch trunk
# c1 adds actor with key 045 (its own file only)
gq checkout -q -b c1 trunk
printf 'Begin Actor Class=X Name=Datacube0\n    OrderKey=045\n    Name=Datacube0\nEnd Actor\n' > "$REPO/actors/Datacube0.t3d"
gq add -A; gq commit -q -m c1
# c2 adds actor with key 055 (its own file only)
gq checkout -q -b c2 trunk
printf 'Begin Actor Class=X Name=Barrel0\n    OrderKey=055\n    Name=Barrel0\nEnd Actor\n' > "$REPO/actors/Barrel0.t3d"
gq add -A; gq commit -q -m c2
gq checkout -q c1
banner "Test C: per-actor OrderKey (no shared order file)"
set +e; gq merge --no-edit c2; echo "rc=$?"; set -e
banner "Test C actor files after merge (order = sort by OrderKey)"
grep -H OrderKey "$REPO"/actors/*.t3d | sort -t= -k2

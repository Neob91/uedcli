#!/usr/bin/env bash
# De-risk spike for the git-native model (direction/trunk-and-editor.md 2026-07-05; spec 2026-07-05-uedcli-git-native-model-design).
# Validates `git merge` on the EXACT trunk layout:  uedcli/maps/<lvl>/actors/<name>/{actor.t3d, order_value}
# across the scenarios the two cold reviewers flagged. Pure git — no editor, no uedcli code.
# Creates a throwaway repo in a mktemp dir (nothing touches the real tree). Prints PASS/FAIL vs expectation.
set -uo pipefail

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
cd "$WORK"
git init -q
git config user.email spike@x ; git config user.name spike
git config merge.conflictstyle merge >/dev/null 2>&1 || true

L=uedcli/maps/lvl/actors
FAILS=0

mk() { # <name> <order_value> <body-line>
  mkdir -p "$L/$1"
  printf '%s\n' "$3" > "$L/$1/actor.t3d"
  printf '%s\n' "$2" > "$L/$1/order_value"
}

# Deterministic total order = sort by (order_value, name); LC_ALL=C for byte-stable sort.
sortorder() {
  for d in "$L"/*/ ; do
    [ -e "$d/order_value" ] || continue
    printf '%s\t%s\n' "$(cat "$d/order_value")" "$(basename "$d")"
  done | LC_ALL=C sort
}

# --- base: two actors P(order m) Q(order t) + a multi-line LevelInfo singleton ---
mk P_p00001 m "brush P"
mk Q_q00002 t "brush Q"
mkdir -p "$L/LevelInfo_000000"
printf 'Begin Actor Class=LevelInfo\n  Title=Test\n  Author=me\n  Song=None\nEnd Actor\n' > "$L/LevelInfo_000000/actor.t3d"
printf 'a\n' > "$L/LevelInfo_000000/order_value"
git add -A ; git commit -qm base
BASE=$(git rev-parse HEAD)

# merge helper: checkout fresh A off BASE, run "$1" (A edits), commit; fresh B, run "$2", commit; merge B into A.
# echoes CLEAN or CONFLICT.
merge_scenario() {
  local tag=$1 a_cmds=$2 b_cmds=$3
  git checkout -q -B "${tag}a" "$BASE"
  eval "$a_cmds" ; git add -A ; git commit -qm "${tag}-A" >/dev/null
  git checkout -q -B "${tag}b" "$BASE"
  eval "$b_cmds" ; git add -A ; git commit -qm "${tag}-B" >/dev/null
  git checkout -q "${tag}a"
  if git merge -q --no-edit "${tag}b" >/dev/null 2>&1 ; then echo CLEAN ; else echo CONFLICT ; git merge --abort 2>/dev/null ; fi
}

check() { # <scenario> <expected> <observed>
  local s=$1 exp=$2 obs=$3
  if [ "$exp" = "$obs" ]; then printf '  PASS  %-42s expect=%-8s got=%s\n' "$s" "$exp" "$obs"
  else printf '  FAIL  %-42s expect=%-8s got=%s\n' "$s" "$exp" "$obs"; FAILS=$((FAILS+1)); fi
}

echo "== git merge scenarios on the per-actor-dir layout =="

# 1. disjoint adds (two new differently-named random dirs)
o=$(merge_scenario s1 'mk Wall_a1b2c3 p "brush wall"' 'mk Floor_d4e5f6 r "brush floor"')
check "1 disjoint adds" CLEAN "$o"

# 2. concurrent SAME-GAP adds: both pick order_value 'p' (between m and t), different names
git checkout -q -B s2a "$BASE"; mk X_aaa111 p "brush X"; git add -A; git commit -qm s2A >/dev/null
git checkout -q -B s2b "$BASE"; mk Y_bbb222 p "brush Y"; git add -A; git commit -qm s2B >/dev/null
git checkout -q s2a
if git merge -q --no-edit s2b >/dev/null 2>&1; then o2=CLEAN; else o2=CONFLICT; fi
check "2 same-gap adds (equal order_value)" CLEAN "$o2"
# determinism: the (order_value,name) sort is total + stable; the two 'p' actors order by name
ord1=$(sortorder); ord2=$(sortorder)
[ "$ord1" = "$ord2" ] && dcheck=PASS || dcheck=FAIL
dupkeys=$(sortorder | awk '{print $1"\t"$2}' | sort | uniq -d | wc -l)   # duplicate (order_value,name) pairs
printf '  %s  2 sort is total+deterministic (dup (order_value,name) pairs=%s)\n' "$([ "$dcheck" = PASS ] && [ "$dupkeys" -eq 0 ] && echo PASS || echo FAIL)" "$dupkeys"
[ "$dcheck" = PASS ] && [ "$dupkeys" -eq 0 ] || FAILS=$((FAILS+1))
echo "     resulting order (order_value <TAB> name):"; sortorder | sed 's/^/       /'
git merge --abort 2>/dev/null; git checkout -q "$BASE" 2>/dev/null

# 3. reorder the SAME actor (both rewrite P's order_value) -> real conflict
o=$(merge_scenario s3 'printf "%s\n" k > "$L/P_p00001/order_value"' 'printf "%s\n" x > "$L/P_p00001/order_value"')
check "3 reorder same actor" CONFLICT "$o"

# 4. reorder DIFFERENT actors (A moves P, B moves Q) -> clean
o=$(merge_scenario s4 'printf "%s\n" z > "$L/P_p00001/order_value"' 'printf "%s\n" b > "$L/Q_q00002/order_value"')
check "4 reorder different actors" CLEAN "$o"

# 5. modify/delete: A deletes P's dir, B edits P's actor.t3d
o=$(merge_scenario s5 'git rm -q -r "$L/P_p00001"' 'printf "%s\n" "brush P edited" > "$L/P_p00001/actor.t3d"')
check "5 modify/delete same actor" CONFLICT "$o"

# 6a. LevelInfo singleton, ADJACENT lines edited (Title line2 + Author line3) -> git conflicts:
#     no unchanged context line between the two changed lines, so git treats them as one hunk.
o=$(merge_scenario s6a 'sed -i "s/Title=Test/Title=Nano/" "$L/LevelInfo_000000/actor.t3d"' 'sed -i "s/Author=me/Author=you/" "$L/LevelInfo_000000/actor.t3d"')
check "6a LevelInfo ADJACENT-line edits" CONFLICT "$o"

# 6b. LevelInfo singleton, SAME line edited -> conflict
o=$(merge_scenario s6b 'sed -i "s/Title=Test/Title=Nano/" "$L/LevelInfo_000000/actor.t3d"' 'sed -i "s/Title=Test/Title=Zero/" "$L/LevelInfo_000000/actor.t3d"')
check "6b LevelInfo same-line edits" CONFLICT "$o"

# 6c. LevelInfo singleton, NON-adjacent lines (Title line2 + Song line4; Author line3 unchanged between)
#     -> git auto-merges cleanly. Pins the mechanism: adjacency, not same-file, is what conflicts.
o=$(merge_scenario s6c 'sed -i "s/Title=Test/Title=Nano/" "$L/LevelInfo_000000/actor.t3d"' 'sed -i "s/Song=None/Song=Intro/" "$L/LevelInfo_000000/actor.t3d"')
check "6c LevelInfo NON-adjacent-line edits" CLEAN "$o"

# 7. the 'name' file question. 7a: a shared name file both branches change -> conflict.
git checkout -q -B s7base "$BASE"; printf 'lvl.dx\n' > uedcli/maps/lvl/name; git add -A; git commit -qm s7base >/dev/null
B7=$(git rev-parse HEAD)
git checkout -q -B s7a "$B7"; printf 'aa.dx\n' > uedcli/maps/lvl/name; git add -A; git commit -qm s7A >/dev/null
git checkout -q -B s7b "$B7"; printf 'bb.dx\n' > uedcli/maps/lvl/name; git add -A; git commit -qm s7B >/dev/null
git checkout -q s7a
if git merge -q --no-edit s7b >/dev/null 2>&1; then o7=CLEAN; else o7=CONFLICT; git merge --abort 2>/dev/null; fi
check "7a shared 'name' file both changed" CONFLICT "$o7"
echo "     -> recommendation: derive level name from the maps/<lvl>/ dir name (no file, no conflict)"

echo
echo "== FAILS: $FAILS =="
exit $FAILS

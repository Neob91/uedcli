#!/usr/bin/env bash
# Survey a set of T3D trunks for `Class=...Brush` actors with no `CsgOper=` line, and report each
# one's rank position (0-based, by LexoRank `order_value`) relative to `LevelInfo0` and the
# trunk's ordinary (CsgOper-bearing) brushes.
#
# Part of this spike: confirming UED22 identifies the live/current builder brush by ARRAY
# POSITION (`ULevel.Actors[1]`), not by any content heuristic (`Class=Brush` + inner model name
# `Brush` + no `CsgOper` -- the predicate `uedcli/normalize.py:is_builder_brush` currently uses).
#
# Usage: survey_csgoper_less_brushes.sh <trunk-dir> [<trunk-dir> ...]
#
# A plain bash loop (one `cat`/`sed`/`grep` per actor), not a single Python process: on this host a
# python3 interpreter's own startup (`sys.path` directory scan) intermittently hit a transient
# EMFILE ("Too many open files") under concurrent load from other sessions on the shared host, while
# this per-file-subprocess form did not. If a run shows "Too many open files" in its output, just
# re-run it (or re-run the printed offending names alone) -- it is host contention, not a bug in the
# read logic, and it was reproducibly transient during this spike.
set -u
for trunk in "$@"; do
  dir="$trunk/actors"
  if [ ! -d "$dir" ]; then
    echo "=== $trunk: no actors/ dir, skipping ==="
    continue
  fi
  name=$(basename "$trunk")
  tsv="/tmp/${name}_ov.tsv"
  ( cd "$dir" && for a in */; do
      n="${a%/}"
      ov=$(cat "$a/order_value" 2>&1)
      cls_line=$(sed -n '1p' "$a/actor.t3d" 2>&1)
      has_csg=$(grep -c "CsgOper=" "$a/actor.t3d" 2>/dev/null)
      printf '%s\t%s\t%s\t%s\n' "$n" "$ov" "$cls_line" "$has_csg"
    done ) > "$tsv"

  total=$(wc -l < "$tsv")
  errors=$(grep -c 'Too many' "$tsv" || true)
  echo "=== $name: $total actors (from $tsv), read-errors: $errors ==="

  echo "  lowest-ranked 5 actors:"
  sort -t$'\t' -k2,2 "$tsv" | head -5 | sed 's/^/    /'

  echo "  CsgOper-less Class=...Brush actors:"
  awk -F'\t' '{
    split($3,a," "); cls="";
    for (i=1;i<=length(a);i++) if (a[i] ~ /^Class=/) cls=a[i];
    split(cls,b,"="); n=split(b[2],c,"."); bare=c[n];
    if (bare=="Brush" && $4==0) print "    " $1 "  order_value=" $2
  }' "$tsv"
  echo
done

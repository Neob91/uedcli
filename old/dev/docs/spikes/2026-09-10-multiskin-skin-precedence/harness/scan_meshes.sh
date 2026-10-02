#!/usr/bin/env bash
# Which baked UED22 packages carry mesh objects (probe-usable without a missing native DLL)?
set -u
here="$(cd "$(dirname "$0")" && pwd)"
for f in "$here"/../../../../../uned/UED22/*.u; do
  for k in LodMesh Mesh SkeletalMesh; do
    n=$(python3 "$here/list_exports.py" "$f" "$k" 3 2>/dev/null | tail -1)
    case "$n" in "-- 0 shown"|"") ;; *) echo "$(basename "$f") $k $n";; esac
  done
done

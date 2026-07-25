"""Actor-ORDER spike for `level import` (spec 2026-07-24 §9 / plan Slice 0).

FINDING (see ../findings.md): `Engine.Level`'s Actors array lives in the object's
native tail, AFTER its None-terminated property list, serialized as:

    [i32 Num][i32 Max]  (raw INT32, NOT a compact count; Num==Max on disk)
    Num * <compact-index object ref>   (ref 0 == null/deleted slot)

Actors[0] == LevelInfo0 (UE1 invariant), Actors[1] == the default/builder brush.
This matches the native WRITE side already in `uedctl/native/level_write.py`
(`write_level_body`: `struct.pack("<ii", Num, Max)` then `ci(ref)` per actor).

Q1 decodable: YES.  Q2 nulls: YES (interspersed + trailing; must drop).  Q3 does raw
export-table order == Actors-array order (a shortcut)? NO — they differ, so import MUST
decode the Actors array for authoritative order.

Host-native via the production `upackage`. Usage: order_probe.py <map.dx> [<map.dx> ...]
"""
from __future__ import annotations
import struct
import sys

from uedctl import upackage


def decode_level_actors(path: str) -> dict:
    pkg = upackage.load_package(path)
    level_idxs = [i for i, _e in enumerate(pkg.exports)
                  if pkg.object_class_name(i + 1) == "Level"]
    if len(level_idxs) != 1:
        return {"path": path, "error": f"expected 1 Level export, got {level_idxs}"}
    li = level_idxs[0]
    e = pkg.exports[li]
    soff, end = e["soff"], e["soff"] + e["ssize"]
    _tags, pos = upackage.read_property_tags(pkg, soff, end)   # Level has no StateFrame
    num = struct.unpack_from("<i", pkg.buf, pos)[0]; pos += 4
    mx = struct.unpack_from("<i", pkg.buf, pos)[0]; pos += 4
    refs = []
    for _ in range(num):
        r, pos = upackage.read_compact_index(pkg.buf, pos)
        refs.append(r)
    nonnull = [r for r in refs if r > 0]
    order = [r - 1 for r in nonnull]                          # 0-based export indices, nulls dropped
    a0 = pkg.name_of_ref(nonnull[0]) if nonnull else None
    return {
        "path": path.rsplit("/", 1)[-1],
        "num": num, "max": mx, "num_eq_max": num == mx,
        "nulls": refs.count(0),
        "import_refs_bad": sum(1 for r in refs if r < 0),
        "nonnull_distinct": len(set(nonnull)) == len(nonnull),
        "actors0": f"{a0} ({pkg.object_class_name(nonnull[0]) if nonnull else None})",
        "n_actors": len(nonnull),
        "array_eq_export_table_order": order == sorted(order),
        "tail_after_actors_bytes": end - pos,                 # URL + Model + reachspecs + trailing
    }


if __name__ == "__main__":
    import json
    for p in sys.argv[1:]:
        print(json.dumps(decode_level_actors(p), indent=2))

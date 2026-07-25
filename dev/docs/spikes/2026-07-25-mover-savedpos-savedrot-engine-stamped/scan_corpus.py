#!/usr/bin/env python3
"""Corpus evidence for the mover `Saved*` question: are `SavedPos`/`SavedRot`/`SavedTrigger` ever
AUTHORED content, or always the same engine-stamped sentinel?

Two independent sweeps, no uedctl imports (runs on a bare Python 3):

1. `--t3d <dir>` — walk every `*.t3d` under a directory, split it into `Begin Actor … End Actor`
   blocks, and report per file: how many Mover-derived actors it holds, how many carry each
   `Saved*` field, and the DISTINCT values seen. A field that is authored content varies between
   actors; a field that is engine-stamped is byte-identical everywhere.

2. `--maps <dir>` — count the raw little-endian byte patterns of the sentinel in binary map files
   (`.dx`/`.unr`): `float32(-12345.0)` and the `int32` triple `(123, 456, 789)`. Three floats per
   rotator triple means one `SavedPos` + one `SavedRot` per mover, i.e. every mover in the shipped
   game carries it.

Usage:
    python3 scan_corpus.py --t3d /path/to/repo --maps /path/to/DX/Maps
"""
from __future__ import annotations

import argparse
import collections
import os
import re
import struct

FIELDS = ("SavedPos", "SavedRot", "SavedTrigger", "BasePos")
ACTOR_RE = re.compile(r"^\s*Begin Actor Class=([A-Za-z0-9_.]+)(.*?)^\s*End Actor", re.M | re.S)
VALUE_RE = {f: re.compile(rf"\b{f}=(\S+)") for f in FIELDS}


def scan_t3d(root: str) -> None:
    per_file = []
    values: dict[str, collections.Counter] = {f: collections.Counter() for f in FIELDS}
    classes: dict[str, collections.Counter] = {f: collections.Counter() for f in FIELDS}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != ".git"]
        for name in filenames:
            if not name.endswith(".t3d"):
                continue
            path = os.path.join(dirpath, name)
            try:
                text = open(path, encoding="latin-1").read()
            except OSError:
                continue
            counts = collections.Counter()
            for cls, body in ACTOR_RE.findall(text):
                # "mover-derived" = the class bare-name ends in Mover, OR the block carries a field
                # only Engine.Mover declares (so DeusEx.BreakableGlass/BreakableWall are caught too).
                if not (cls.rsplit(".", 1)[-1].endswith("Mover")
                        or "BasePos" in body or "SavedPos" in body):
                    continue
                counts["movers"] += 1
                for f in FIELDS:
                    m = VALUE_RE[f].search(body)
                    if m:
                        counts[f] += 1
                        values[f][m.group(1)] += 1
                        classes[f][cls] += 1
            if counts["movers"]:
                per_file.append((os.path.relpath(path, root), counts))

    per_file.sort(key=lambda r: -r[1]["movers"])
    head = f"{'file':64s} {'movers':>6s} " + " ".join(f"{f:>12s}" for f in FIELDS)
    print(head)
    for rel, c in per_file:
        print(f"{rel:64.64s} {c['movers']:6d} " + " ".join(f"{c[f]:12d}" for f in FIELDS))
    print(f"\nfiles with movers: {len(per_file)}")
    for f in FIELDS:
        print(f"\n{f}: {sum(values[f].values())} occurrences, "
              f"{len(values[f])} DISTINCT value(s)")
        for v, n in values[f].most_common(8):
            print(f"    {n:6d}  {v}")
        print(f"  on classes: {dict(classes[f])}")


def scan_maps(root: str) -> None:
    sentinel_pos = struct.pack("<f", -12345.0)
    sentinel_rot = struct.pack("<iii", 123, 456, 789)
    print(f"{'map':44s} {'-12345f':>9s} {'(123,456,789)':>14s}  ratio")
    total_p = total_r = 0
    for name in sorted(os.listdir(root)):
        path = os.path.join(root, name)
        if not os.path.isfile(path) or not name.lower().endswith((".dx", ".unr")):
            continue
        data = open(path, "rb").read()
        p, r = data.count(sentinel_pos), data.count(sentinel_rot)
        if not (p or r):
            continue
        total_p += p
        total_r += r
        print(f"{name:44s} {p:9d} {r:14d}  {p / r if r else float('nan'):.2f}")
    print(f"\ntotal: {total_p} floats / {total_r} rotators "
          f"(3.00 == exactly one SavedPos + one SavedRot per mover)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--t3d", help="root dir to walk for *.t3d editor exports")
    ap.add_argument("--maps", help="dir of binary .dx/.unr map files")
    args = ap.parse_args()
    if args.t3d:
        scan_t3d(args.t3d)
    if args.maps:
        print()
        scan_maps(args.maps)
    if not (args.t3d or args.maps):
        ap.error("give --t3d and/or --maps")


if __name__ == "__main__":
    main()

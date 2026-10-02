#!/usr/bin/env python3
"""Diff the two halves of the per-brush Pass-1 tree-shape trace.

Inputs:
  --editor-log  pass1-brush-trace-unatco.log   (CSGENTRY per call + P1END, from
                pass1_brush_trace_unatco.py; CSGENTRY k holds the state AFTER call k-1)
  --native-log  native stderr                  (BRUSHSTATE k holds the state AFTER brush k, from
                pass1_native_states.py; P1NODE lines when FULL mode was on)
  --bins        editor p1nodes/ dir            (n%%04d.bin raw FBspNode arrays, n<k>.bin = state
                after call k-1; nfinal.bin = after the last call)

Phase 1 (always): align the two per-brush count sequences, print the FIRST k where any of
nodes/surfs diverges (verts/points/vectors reported but not used for "first divergence" — the
points pool is a known separate residual axis).
Phase 2 (with --bins + a FULL native log): for the first divergent k (or --at K), bit-compare the
editor's node array after brush k-1 (the last agreeing state) and after brush k against native's
P1NODE dumps — first differing node index, per-field.
"""
import argparse
import re
import struct
import sys
from pathlib import Path

FIELDS = ("nodes", "surfs", "verts", "points", "vectors")


def parse_editor(log: Path) -> tuple[list[dict], dict | None]:
    states, end = [], None
    for line in log.read_text(errors="replace").splitlines():
        if line.startswith("CSGENTRY "):
            d = dict(kv.split("=") for kv in line.split()[1:])
            states.append({f: int(d[f]) for f in FIELDS} | {"k": int(d["k"])})
        elif line.startswith("P1END "):
            d = dict(kv.split("=") for kv in line.split()[1:])
            end = {f: int(d[f]) for f in FIELDS} | {"calls": int(d["calls"])}
    return states, end


def parse_native(log: Path) -> tuple[list[dict], dict[int, list[tuple]]]:
    states: list[dict] = []
    nodes: dict[int, list[tuple]] = {}
    for line in log.read_text(errors="replace").splitlines():
        if line.startswith("BRUSHSTATE "):
            d = dict(kv.split("=") for kv in line.split()[1:])
            states.append({f: int(d[f]) for f in FIELDS} | {"k": int(d["k"]), "bi": int(d["bi"])})
        elif line.startswith("P1NODE "):
            m = re.match(r"P1NODE k=(\d+) i=(\d+) pb=(\w+),(\w+),(\w+),(\w+) iF=(-?\d+) "
                         r"iB=(-?\d+) iP=(-?\d+) isurf=(-?\d+) nv=(\d+)", line)
            k = int(m.group(1))
            nodes.setdefault(k, []).append((
                int(m.group(3), 16), int(m.group(4), 16), int(m.group(5), 16), int(m.group(6), 16),
                int(m.group(7)), int(m.group(8)), int(m.group(9)), int(m.group(10)),
                int(m.group(11))))
    return states, nodes


def read_bin(path: Path) -> list[tuple]:
    buf = path.read_bytes()
    out = []
    for off in range(0, len(buf), 0x40):
        n = buf[off:off + 0x40]
        px, py, pz, pw = struct.unpack_from("<4I", n, 0)
        i_back, i_front, i_plane = struct.unpack_from("<3i", n, 0x20)
        (i_surf,) = struct.unpack_from("<i", n, 0x1c)
        nv = n[0x36]
        out.append((px, py, pz, pw, i_front, i_back, i_plane, i_surf, nv))
    return out


def diff_nodes(label: str, ed: list[tuple], na: list[tuple]) -> bool:
    if len(ed) != len(na):
        print(f"  {label}: editor {len(ed)} nodes vs native {len(na)}")
    same = True
    for i, (e, n) in enumerate(zip(ed, na)):
        if e != n:
            same = False
            print(f"  {label}: first differing node i={i}")
            names = ("plx", "ply", "plz", "plw", "iF", "iB", "iP", "isurf", "nv")
            for nm, ev, nv_ in zip(names, e, n):
                mark = "" if ev == nv_ else "   <-- DIFF"
                if nm.startswith("pl"):
                    print(f"    {nm}: editor {ev:08x} ({struct.unpack('<f', struct.pack('<I', ev))[0]:.6f})"
                          f" native {nv_:08x} ({struct.unpack('<f', struct.pack('<I', nv_))[0]:.6f}){mark}")
                else:
                    print(f"    {nm}: editor {ev} native {nv_}{mark}")
            break
    if same and len(ed) == len(na):
        print(f"  {label}: IDENTICAL ({len(ed)} nodes, all 9 compared fields bit-equal)")
    return same and len(ed) == len(na)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--editor-log", required=True, type=Path)
    ap.add_argument("--native-log", required=True, type=Path)
    ap.add_argument("--bins", type=Path)
    ap.add_argument("--at", type=int, help="force phase-2 node compare at this k")
    args = ap.parse_args()

    ed_states, ed_end = parse_editor(args.editor_log)
    na_states, na_nodes = parse_native(args.native_log)
    ncalls = len(ed_states)
    print(f"editor: {ncalls} bspBrushCSG calls captured, P1END={ed_end}")
    print(f"native: {len(na_states)} Pass-1 brushes")
    if ed_end and ed_end["calls"] != len(na_states):
        print(f"CALL-COUNT MISMATCH: editor {ed_end['calls']} vs native {len(na_states)}")

    # editor state AFTER brush j = CSGENTRY[j+1] (entry of the next call), or P1END for the last.
    first_div = None
    limit = min(len(na_states), ncalls - 1 if ed_end is None else len(na_states))
    for j in range(limit):
        if j + 1 < ncalls:
            ed = ed_states[j + 1]
        elif ed_end is not None:
            ed = ed_end
        else:
            break
        na = na_states[j]
        assert na["k"] == j
        diffs = {f: (ed[f], na[f]) for f in FIELDS if ed[f] != na[f]}
        hard = {f: v for f, v in diffs.items() if f in ("nodes", "surfs")}
        if diffs and first_div is None:
            print(f"k={j} (bi={na['bi']}): first ANY-field divergence: "
                  + " ".join(f"{f} editor={a} native={b}" for f, (a, b) in diffs.items()))
            first_div = j
        if hard:
            print(f"k={j} (bi={na['bi']}): FIRST NODES/SURFS DIVERGENCE: "
                  + " ".join(f"{f} editor={a} native={b}" for f, (a, b) in hard.items()))
            first_div = j
            break
    else:
        print("counts: no nodes/surfs divergence across all aligned brushes")

    target = args.at if args.at is not None else first_div
    if args.bins and target is not None and na_nodes:
        print(f"phase 2: node-array bit compare around k={target}")
        for k in (target - 1, target):
            if k < 0 or k not in na_nodes:
                continue
            binp = (args.bins / "nfinal.bin") if k + 1 >= ncalls else (args.bins / f"n{k + 1:04d}.bin")
            if not binp.exists():
                print(f"  k={k}: editor bin {binp.name} missing")
                continue
            diff_nodes(f"after brush k={k}", read_bin(binp), na_nodes[k])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

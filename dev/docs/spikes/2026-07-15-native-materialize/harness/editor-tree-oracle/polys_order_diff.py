#!/usr/bin/env python3
r"""Diff the repartition-input face ORDER: native post-merge soup vs the editor's bspBuild-entry.

Inputs:
  * EDITOR — `logs/editor-polys-N.log` from `editor_polys_oracle.py N` (the `Model->Polys->Element`
    array at the `bspBuild` call inside `bspRepartition`, i.e. the true SplitPolyList input order).
  * NATIVE — captured in-process via the `UEDCLI_BSPCSG_SOUP_ORDER` env hook in `bspcsg.rs`
    (one `POLY` line per merged-soup face, in the order `bsp_build` consumes it).

Each face keys on `(normal, base, vert0, nv)` rounded.  Content is byte-exact as a multiset
(`soup_cmp.py` 0/0), so any mismatch is pure ORDER.  Reports:
  * the longest matching prefix (first index where the key sequences differ),
  * a compact list of the first K positional disagreements,
  * an LCS-based "moved" summary: which faces the editor has earlier/later than native.

Usage:  polys_order_diff.py [N=33] [--ndp 1] [--first 20]
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path("/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedcli")
HARNESS = ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"
HERE = HARNESS / "editor-tree-oracle"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(HERE))

_LINE = re.compile(
    r"POLY (\d+) nv=(-?\d+) ilink=(-?\d+) "
    r"N=([-0-9.,]+) B=([-0-9.,]+)")
_VERT = re.compile(r"VERT ([-0-9.,]+)")


def _rvec(s, ndp):
    return tuple(round(float(x), ndp) for x in s.split(","))


def parse_log(path: Path, ndp: int):
    """Rotation-invariant face keys in file order: (normal, w, sorted rounded vertex set).

    Base/first-vertex are NOT stable across the two models (base is the texture-mapping point;
    the vertex list can be rotated), so we key exactly like `soup_cmp.py`: the plane (normal, w
    where w = normal.V0) plus the ORDER-INDEPENDENT vertex set.  This makes the multiset match
    (proven 0/0) so any sequence mismatch is pure ORDER.
    """
    keys = []
    cur_n = None
    cur_verts = None
    lines = path.read_text(errors="replace").splitlines()

    def flush():
        if cur_n is not None and cur_verts:
            w = round(sum(a * b for a, b in zip(cur_n, cur_verts[0])), ndp)
            vk = tuple(sorted(cur_verts))
            keys.append((cur_n, w, vk))

    for ln in lines:
        m = _LINE.match(ln)
        if m:
            flush()
            cur_n = _rvec(m[4], ndp)
            cur_verts = []
            continue
        mv = _VERT.match(ln)
        if mv and cur_verts is not None:
            cur_verts.append(_rvec(mv[1], ndp))
    flush()
    return keys


def native_order(n: int, ndp: int):
    from uedcli import trunk
    from uedcli.native import materialize as M
    import castle_build
    import uedcli_native

    level, _ = trunk.read_level(Path(castle_build.TRUNK))
    names = [nm for nm in level.order if level.actors[nm].brush is not None]
    if n is not None:
        names = names[:n]
    inputs = [M._build_brush_input(nm, level.actors[nm]) for nm in names]

    raw = HERE / "logs" / f"native-polys-{n}.raw"
    raw.parent.mkdir(parents=True, exist_ok=True)
    saved = os.dup(2)
    fd = os.open(str(raw), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    # The dump lives INSIDE the repartition block (right after bsp_merge_coplanars), so do NOT
    # set NOREPART (which would skip the whole block); a full build is fine.
    os.environ["UEDCLI_BSPCSG_SOUP_ORDER"] = "1"
    try:
        os.dup2(fd, 2)
        uedcli_native.build_geometry_bspcsg(inputs)
    finally:
        os.dup2(saved, 2)
        os.close(fd)
        os.close(saved)
        os.environ.pop("UEDCLI_BSPCSG_SOUP_ORDER", None)
    keys = parse_log(raw, ndp)
    raw.unlink(missing_ok=True)
    return keys


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("n", type=int, nargs="?", default=33)
    ap.add_argument("--ndp", type=int, default=1, help="rounding decimals for the face key")
    ap.add_argument("--first", type=int, default=20, help="how many positional disagreements to show")
    args = ap.parse_args()

    ed_log = HERE / "logs" / f"editor-polys-{args.n}.log"
    if not ed_log.exists():
        raise SystemExit(f"missing {ed_log}; run editor_polys_oracle.py {args.n} first")
    ed = parse_log(ed_log, args.ndp)
    na = native_order(args.n, args.ndp)

    print(f"editor polys={len(ed)}  native polys={len(na)}")
    from collections import Counter
    ce, cn = Counter(ed), Counter(na)
    print(f"multiset shared={sum((ce & cn).values())} onlyE={sum((ce - cn).values())} "
          f"onlyN={sum((cn - ce).values())}")

    # matching prefix
    pref = 0
    for a, b in zip(ed, na):
        if a != b:
            break
        pref += 1
    print(f"matching PREFIX: {pref} / {min(len(ed), len(na))}")

    # first positional disagreements
    shown = 0
    for i in range(min(len(ed), len(na))):
        if ed[i] != na[i]:
            print(f"  [{i}] ED N{ed[i][0]} w={ed[i][1]} nv{len(ed[i][2])} v0{ed[i][2][0]}")
            print(f"       NA N{na[i][0]} w={na[i][1]} nv{len(na[i][2])} v0{na[i][2][0]}")
            shown += 1
            if shown >= args.first:
                break

    # LCS alignment summary
    sm = SequenceMatcher(a=ed, b=na, autojunk=False)
    blocks = sm.get_matching_blocks()
    lcs = sum(b.size for b in blocks)
    print(f"LCS(ed,na) = {lcs}  ({100.0*lcs/max(1,len(ed)):.1f}% of editor)")
    # show first few non-matching opcodes
    ops = [op for op in sm.get_opcodes() if op[0] != "equal"]
    print(f"non-equal opcode groups: {len(ops)}; first {min(args.first, len(ops))}:")
    for tag, i1, i2, j1, j2 in ops[:args.first]:
        print(f"  {tag:9s} ed[{i1}:{i2}] na[{j1}:{j2}]")


if __name__ == "__main__":
    main()

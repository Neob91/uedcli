#!/usr/bin/env python3
r"""Stage 2b — the tree-DIFF result: the divergence is DESCENT-PRUNING, not tree wiring.

Runs the faithful R-pruned `UModel::FindNearestVertex` descent (decoded from Engine.dll 0x1adb60)
over BOTH the editor's and native's live `Model` trees, captured at the SAME moment (the actor-6 `-X`
face surf-base add, query (447.999847, 64.000107, 0), R = the surf-base threshold 0.002), and shows
both return MISS.

THE FINDING (overturns the Stage-2b "expensive tree-wiring" reading):
  - The editor's tree at the divergent add HAS nodes 48/49/50 (surf iSurf=32, pBase point
    (448.00006, 64.00011, 0.00003) = the corner), ALIVE (nv=4) and linkage-reachable from root 0 --
    IDENTICAL to native (native tree dump: same nodes 48/49/50, same corner surf-base).
  - So the corner is NOT "unreachable" and there is NO topology difference that hides it. Both trees
    are structurally equivalent at this add.
  - `FindNearestVertex` MISSES anyway because its descent PRUNES by the current radius R=0.002:
    from root 0 it follows a pd-directed path (iBack when pd>=-R, iFront when pd<=R; a node's
    surf-base/verts tested only inside the |pd|<R slab), and the query (448,64,0) is FAR (416, 4.0,
    1552, ...) from the splitting planes on the way to node 48, so node 48's subtree is pruned and
    never tested. pd at node 48 itself is ~0 (query on its plane) -- it WOULD hit if reached.
  - Native's bug is that `bsp_add_point` uses a LINEAR SCAN over all Model.Points, which finds
    448.00006 (d=2.158e-4 < 0.002) regardless of the tree, and SNAPS. The editor's pruned descent
    does not. Same tree, different dedup -> the whole divergence class.

CONSEQUENCE FOR STAGE 3 (cost re-estimate): the primary fix is to REPLACE the linear scan with the
faithful R-pruned FindNearestVertex descent over native's live tree -- native's tree is already
correct at the divergent add (proven here: descent -> MISS on native's own tree). This is NOT a
multi-week incremental-CSG rewrite. The residual risk is the 76->81 point-table blow-up the earlier
port saw (`ba23319`): switching to the descent changes dedup at EVERY add, and at a handful of OTHER
adds native's tree may differ from the editor's (or the earlier port's descent was non-faithful),
making the descent MISS where the editor HIT (spurious new points). That is a bounded verify/fix on a
few adds, decided by measuring the N8 table after implementing the faithful descent -- not a
foregone rewrite. See stage3-plan.md.

Run: `python3 descent_sim.py` (asserts both trees -> MISS at the divergent add).
Inputs: traces/n8_editor_tree_dump.out (winedbg Model dump), traces/n8_native_tree_dump.txt (native
RN dump from UEDCLI_BSPCSG_POINT_TRACE_TREE).
"""
from __future__ import annotations

import re
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
Q = (447.999847, 64.000107, 0.0)
R = 0.002  # the surf-base FindNearestVertex threshold (arg_2=1)


def _pdot(pl, x):
    return pl[0] * x[0] + pl[1] * x[1] + pl[2] * x[2] - pl[3]


def _dist(a, b):
    return sum((a[i] - b[i]) ** 2 for i in range(3)) ** 0.5


def _descend(tree: dict[int, dict]) -> tuple[bool, float]:
    """Faithful FindNearestVertex: returns (node48_tested, min_surf_base_distance)."""
    tested, best = [], [1e9]
    sys.setrecursionlimit(10000)

    def rec(i):
        while i != -1 and i in tree:
            n = tree[i]
            pd = _pdot(n["plane"], Q)
            if pd >= -R and n["iB"] != -1:
                rec(n["iB"])
            if -R < pd <= R:   # slab test bound per the 0x1adb60 disasm (matches the Rust port)
                tested.append(i)
                best[0] = min(best[0], _dist(n["pbpt"], Q))
                ip = n["iP"]
                while ip != -1 and ip in tree:
                    tested.append(ip)
                    best[0] = min(best[0], _dist(tree[ip]["pbpt"], Q))
                    ip = tree[ip]["iP"]
            if pd <= R:
                i = n["iF"]
            else:
                break

    rec(0)
    return (48 in tested), best[0]


def load_native(path: Path) -> dict[int, dict]:
    tree = {}
    pat = re.compile(
        r"RN (\d+) N=\(([-\d.]+),([-\d.]+),([-\d.]+)\) W=([-\d.]+) iSurf=(-?\d+) pBase=(-?\d+) "
        r"pt=\(([-\d.]+),([-\d.]+),([-\d.]+)\).* iF=(-?\d+) iB=(-?\d+) iP=(-?\d+)")
    for l in path.read_text().splitlines():
        m = pat.search(l)
        if m:
            g = m.groups()
            tree[int(g[0])] = dict(
                plane=(float(g[1]), float(g[2]), float(g[3]), float(g[4])),
                pbpt=(float(g[7]), float(g[8]), float(g[9])),
                iF=int(g[10]), iB=int(g[11]), iP=int(g[12]))
    return tree


def load_editor(path: Path) -> dict[int, dict]:
    txt = path.read_text().splitlines()

    def sect(a, b):
        ws, grab = [], False
        for l in txt:
            if a in l:
                grab = True
                continue
            if b and b in l:
                break
            if grab:
                mm = re.search(r":\s+(.*)$", l.replace("Wine-dbg>", ""))
                if mm:
                    ws += [int(t, 16) for t in mm.group(1).split() if re.fullmatch(r"[0-9a-fA-F]{8}", t)]
        return ws

    NW = sect("=== NODES ===", "=== POINTS ===")
    PW = sect("=== POINTS ===", "=== SURFS ===")
    SW = sect("=== SURFS ===", None)
    f = lambda u: struct.unpack("<f", struct.pack("<I", u))[0]
    si = lambda u: u - (1 << 32) if u >= 0x80000000 else u
    NN, NP, NS = 62, 99, 39

    def pbpt(isurf):
        pb = si(SW[isurf * 16 + 2]) if 0 <= isurf < NS else -1
        return (f(PW[pb * 3]), f(PW[pb * 3 + 1]), f(PW[pb * 3 + 2])) if 0 <= pb < NP else (1e9, 1e9, 1e9)

    tree = {}
    for k in range(NN):
        w = NW[k * 16:k * 16 + 16]
        tree[k] = dict(plane=(f(w[0]), f(w[1]), f(w[2]), f(w[3])),
                       iF=si(w[8]), iB=si(w[9]), iP=si(w[10]), pbpt=pbpt(si(w[7])))
    return tree


def main() -> int:
    ed = load_editor(HERE / "traces" / "n8_editor_tree_dump.out")
    nat = load_native(HERE / "traces" / "n8_native_tree_dump.txt")
    ok = True
    for name, tree in (("editor", ed), ("native", nat)):
        hit48, d = _descend(tree)
        miss = d >= R
        ok = ok and miss
        print(f"{name:>7} tree ({len(tree)} nodes): faithful R=0.002 descent -> "
              f"{'MISS' if miss else f'HIT d={d:.3e}'}  (node48 visited: {hit48})")
    print("\nBoth trees MISS under the faithful descent -> the divergence is the DEDUP ALGORITHM "
          "(native's linear scan HITS 448.00006), not tree wiring. Fix = port the pruned descent."
          if ok else "\nUNEXPECTED: a tree HIT -- re-examine.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

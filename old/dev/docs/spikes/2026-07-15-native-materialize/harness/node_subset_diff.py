#!/usr/bin/env python3
"""Node-partition differential — the §92 stage-2 analog of unatco_subset.py, but on the BSP NODE
set (splitter planes) rather than the final surf set.

The surf method (unatco_subset.py) pins the first brush where native's FINAL surf multiset diverges
from the editor's.  This tool does the same on the NODE-PLANE multiset — the actual BSP partition —
because Verts/Points/Vectors all serialize in node-emit order, so the node partition is the root
byte-parity lever (SUMMARY.md: Nodes 17.3% / Verts 6.9% positional match).

Node-plane key: (normal @1e-3, offset @1e-2).  We compare the ORDER-INDEPENDENT multiset first (does
native build the same SET of splitter planes?), and separately the EMIT-ORDER sequence (does native
emit them in the same order?).  Both matter: byte-parity needs set AND order.

  * NATIVE  — uedcli_native.build_geometry_bspcsg over the first N MOVER-CLEAN brush inputs
              (materialize._in_world_csg), serialize_model -> parse -> m.nodes.  (Mirrors
              unatco_subset.native_surfs exactly; movers dropped per cd56c1ae2.)
  * EDITOR  — cached golden{N}.dx (bare world-only MAP REBUILD), largest Model -> m.nodes.

Cached goldens live at unatco_subset.SUBSET_ROOT (LUM-level _scratch/unatco-subset), N in
{1,8,15,30,75,98,103,104,105,106,109,121,213,396,762}.

CAVEAT (Leaves/Verts under-build): a bare `MAP REBUILD` golden may skip AssignLeaves, so the golden's
Leaves/Verts arrays can be under-built vs a full ZONES rebuild.  The NODE set + node planes are built
by bspBuild proper and ARE trustworthy in a bare REBUILD.  We report leaf/vert counts but trust nodes.

Usage:
  node_subset_diff.py counts <native.dx> <golden.dx>   # node/leaf/vert counts + node-plane set diff
  node_subset_diff.py diff N [--top K]                 # native N-brush nodes vs cached golden{N}
  node_subset_diff.py scan                             # all cached N: set-diff + order-diff table
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

ROOT = Path("/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedcli")
HARNESS = ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HARNESS))

from spike_classindex import class_index  # noqa: E402  (schema-aware mover gate's index)
from uedcli.native import umodel as UM  # noqa: E402
import unatco_subset as US  # noqa: E402
import surf_class_diff as SCD  # noqa: E402

CACHED_N = [1, 8, 15, 30, 75, 98, 103, 104, 105, 106, 109, 121, 213, 396, 762]


def node_plane_key(plane, ndn=3, ndp=2):
    """(rounded unit normal, rounded plane offset W).  Node.plane = (X,Y,Z,W)."""
    return (tuple(round(c, ndn) for c in plane[:3]), round(plane[3], ndp))


def node_keys(m):
    return [node_plane_key(n.plane) for n in m.nodes]


def counts(m):
    return dict(nodes=len(m.nodes), leaves=len(m.leaves), verts=len(m.verts),
                points=len(m.points), vectors=len(m.vectors), surfs=len(m.surfs))


def set_diff(nat_keys, gold_keys):
    kn, kg = Counter(nat_keys), Counter(gold_keys)
    onlyN, onlyE = kn - kg, kg - kn
    return dict(shared=sum((kn & kg).values()),
                onlyN=sum(onlyN.values()), onlyE=sum(onlyE.values()),
                onlyN_set=onlyN, onlyE_set=onlyE)


def order_diff(nat_keys, gold_keys):
    """First index where the emit SEQUENCE of node-plane keys diverges (only meaningful once the
    SET matches; reported regardless)."""
    n = min(len(nat_keys), len(gold_keys))
    for i in range(n):
        if nat_keys[i] != gold_keys[i]:
            return i
    if len(nat_keys) != len(gold_keys):
        return n
    return None


def native_model(n):
    """Native mover-clean N-brush build -> parsed Model (mirrors unatco_subset.native_surfs)."""
    import uedcli_native
    from uedcli.native import materialize as M
    level, _ = US.trunk.read_level(US.FULL_TRUNK)
    brushes = [nm for nm in US._brush_order(level)[:n] if M._in_world_csg(level.actors[nm], class_index())]
    bs = [M._build_brush_input(nm, level.actors[nm]) for nm in brushes]
    mdl = uedcli_native.build_geometry_bspcsg(bs)
    body = uedcli_native.serialize_model(mdl)
    return UM.parse_model_body(body, 0, len(body))


def n_world_brushes(n):
    from uedcli.native import materialize as M
    level, _ = US.trunk.read_level(US.FULL_TRUNK)
    return sum(1 for nm in US._brush_order(level)[:n] if M._in_world_csg(level.actors[nm], class_index()))


def golden_model(n):
    return SCD.load_model(str(US.golden_path(n)))


def _print_counts(label, c):
    print(f"  {label:<8} nodes={c['nodes']:>6} leaves={c['leaves']:>6} verts={c['verts']:>7} "
          f"points={c['points']:>6} vectors={c['vectors']:>5} surfs={c['surfs']:>5}")


def cmd_counts(nat_path, gold_path):
    nm = SCD.load_model(nat_path)
    gm = SCD.load_model(gold_path)
    print(f"NATIVE: {nat_path}\nEDITOR: {gold_path}\n")
    cn, cg = counts(nm), counts(gm)
    _print_counts("native", cn)
    _print_counts("editor", cg)
    print("  delta   ", {k: cn[k] - cg[k] for k in cn})
    d = set_diff(node_keys(nm), node_keys(gm))
    print(f"\n  node-plane multiset (normal@1e-3, offset@1e-2):")
    print(f"    shared={d['shared']}  only-native={d['onlyN']}  only-editor={d['onlyE']}")
    print("  top only-native node planes:")
    for k, c in d['onlyN_set'].most_common(15):
        print(f"    {k}  x{c}")
    print("  top only-editor node planes:")
    for k, c in d['onlyE_set'].most_common(15):
        print(f"    {k}  x{c}")


def cmd_diff(n, top=15):
    nm = native_model(n)
    gm = golden_model(n)
    nk, gk = node_keys(nm), node_keys(gm)
    d = set_diff(nk, gk)
    od = order_diff(nk, gk)
    wb = n_world_brushes(n)
    print(f"N={n} (world-brushes={wb})")
    _print_counts("native", counts(nm))
    _print_counts("editor", counts(gm))
    print(f"  node-plane set: shared={d['shared']} only-native={d['onlyN']} only-editor={d['onlyE']}"
          f"  {'SET-MATCH' if not (d['onlyN'] or d['onlyE']) else 'SET-DIVERGES'}")
    print(f"  emit-order first-divergence index: {od}"
          + (f"  (native={nk[od] if od < len(nk) else 'END'} editor={gk[od] if od < len(gk) else 'END'})"
             if od is not None else "  (ORDER IDENTICAL)"))
    if d['onlyN']:
        print("  top only-native node planes:")
        for k, c in d['onlyN_set'].most_common(top):
            print(f"    {k}  x{c}")
    if d['onlyE']:
        print("  top only-editor node planes:")
        for k, c in d['onlyE_set'].most_common(top):
            print(f"    {k}  x{c}")
    return dict(n=n, wb=wb, cn=counts(nm), cg=counts(gm), setdiff=d, order=od)


def cmd_scan():
    print(f"  {'N':>4} {'wbr':>4} {'natNodes':>8} {'edNodes':>8} {'dNodes':>7} "
          f"{'shared':>7} {'onlyN':>6} {'onlyE':>6} {'setMatch':>9} {'ord1st':>7}")
    print(f"  {'-'*4} {'-'*4} {'-'*8} {'-'*8} {'-'*7} {'-'*7} {'-'*6} {'-'*6} {'-'*9} {'-'*7}")
    rows = []
    for n in CACHED_N:
        gp = US.golden_path(n)
        if not gp.exists():
            print(f"  {n:>4}  (no cached golden)")
            continue
        nm = native_model(n)
        gm = golden_model(n)
        nk, gk = node_keys(nm), node_keys(gm)
        d = set_diff(nk, gk)
        od = order_diff(nk, gk)
        wb = n_world_brushes(n)
        setmatch = not (d['onlyN'] or d['onlyE'])
        dn = len(nm.nodes) - len(gm.nodes)
        print(f"  {n:>4} {wb:>4} {len(nm.nodes):>8} {len(gm.nodes):>8} {dn:>+7} "
              f"{d['shared']:>7} {d['onlyN']:>6} {d['onlyE']:>6} {str(setmatch):>9} "
              f"{str(od):>7}")
        rows.append((n, wb, len(nm.nodes), len(gm.nodes), d, od, setmatch))
    # first N with set divergence
    first_set = next((r[0] for r in rows if not r[6]), None)
    first_ord = next((r[0] for r in rows if r[5] is not None), None)
    print(f"\n  first N with node-SET divergence : {first_set}")
    print(f"  first N with node-ORDER divergence: {first_ord}")
    return rows


def main():
    if len(sys.argv) < 2:
        print(__doc__); return
    cmd = sys.argv[1]
    if cmd == "counts":
        cmd_counts(sys.argv[2], sys.argv[3])
    elif cmd == "diff":
        top = 15
        if "--top" in sys.argv:
            top = int(sys.argv[sys.argv.index("--top") + 1])
        cmd_diff(int(sys.argv[2]), top=top)
    elif cmd == "scan":
        cmd_scan()
    else:
        print(f"unknown cmd {cmd}"); print(__doc__)


if __name__ == "__main__":
    main()

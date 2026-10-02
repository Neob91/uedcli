#!/usr/bin/env python3
"""Binary-search the freeclinic08 structural-only (141-brush) world-CSG order to localize the
FIRST brush whose incremental CSG add makes native's Pass-1 tree diverge from the real editor's.

WHY. `freeclinic08-nsfhq04-1-surf-under-build-root`'s 3rd continuation confirmed the world-level
node/leaf deficit (-38/-23 on the structural-only set) is inherited from Pass 1's own incrementally
-built tree (PREMERGE poly-fragment count: 1333 editor vs 1263 native for the SAME 141-brush set,
~70-poly gap) -- present before bspBuildFPolys/bspMergeCoplanars/bspBuild ever run. The concrete
next step it named: attribute this to specific brush(es) via a per-brush Pass-1 trace.

TECHNIQUE (cheaper than new GDB instrumentation): bspBrushCSG's Pass-1 loop is a pure sequential
fold -- brush i's CSG add depends only on the model state after brushes 1..i-1, and NO repartition
happens until the ONE world-level bspRepartition call at the very end. So truncating the brush list
to its first N (in CSG order) and building BOTH sides (native in-process, editor via a fresh
`MAP REBUILD`) reproduces exactly the Pass-1-then-repartition state after N incremental brush adds,
with no dependency on brushes N+1..141. Binary-searching N by comparing FINAL node counts (no new
disassembly, reusing `build_ued_golden.py`) localizes the first diverging brush directly.

Usage: .venv/bin/python fc08_prefix_search.py [N ...]   -- build+compare specific prefix sizes
       .venv/bin/python fc08_prefix_search.py --search   -- binary search 1..141
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path("/workspace/uedcli")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness/editor-tree-oracle"))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-06-27-decontainerize-uedcli/harness"))

WORKTREE = ROOT / ".claude/worktrees/nsfhq04-residual-investigation"
BUILD_SCRIPT = ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness/build_ued_golden.py"
PYEXE = str(WORKTREE / ".venv/bin/python")

from uedcli import trunk                          # noqa: E402
from uedcli.native import brush_marshal as BM      # noqa: E402
from uedcli.native import umodel as UM             # noqa: E402
import uedcli_native                               # noqa: E402
import utexture_decode as UT                       # noqa: E402
from spike_classindex import class_index           # noqa: E402

SRC_TRUNK = ROOT / "_scratch/fc08-structural-only/maps/freeclinic08"
PREFIX_ROOT = ROOT / "_scratch/fc08-prefix"
os.environ.setdefault("UEDCLI_PROJECT", str(ROOT / "_scratch/fc08-structural-only"))


def load_source():
    level, ranks = trunk.read_level(SRC_TRUNK)
    ci = class_index()
    brush_names = [n for n in level.order
                   if level.actors[n].brush is not None and BM._in_world_csg(level.actors[n], ci)]
    other_names = [n for n in level.order if n not in set(brush_names)]
    print(f"source: {len(level.actors)} actors; {len(brush_names)} world-csg brushes; "
          f"{len(other_names)} other (non-brush) actors")
    return level, ranks, brush_names, other_names


def native_prefix_counts(level, brush_names, n):
    names_n = brush_names[:n]
    ins = [BM._build_brush_input(nm, level.actors[nm]) for nm in names_n]
    built = uedcli_native.build_geometry_bspcsg(ins)
    nbody = uedcli_native.serialize_model(built)
    return UM.parse_model_body(nbody, 0, len(nbody))


def write_prefix_trunk(level, ranks, brush_names, other_names, n):
    keep = set(other_names) | set(brush_names[:n])
    new_order = [nm for nm in level.order if nm in keep]
    dst = PREFIX_ROOT / f"n{n:03d}" / "maps/freeclinic08"
    if dst.exists():
        shutil.rmtree(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    new_level = type(level)(actors={k: v for k, v in level.actors.items() if k in keep}, order=new_order)
    new_ranks = {k: v for k, v in ranks.items() if k in keep}
    trunk.write_level(dst, new_level, new_ranks)
    proj = dst.parent.parent
    (proj / "uedcli.toml").write_text('game = "deusex"\nmaps = "maps"\n')
    return dst, proj


def parse_golden(path):
    pkg = UT.load_package(str(path))
    models = [i for i in range(len(pkg.exports)) if pkg.class_of_export(i) == "Model"]
    mi = max(models, key=lambda i: pkg.exports[i]["ssize"])
    return UM.parse_model_body(pkg.buf, pkg.exports[mi]["soff"], pkg.exports[mi]["ssize"])


def editor_prefix_counts(level, ranks, brush_names, other_names, n, *, force=False):
    dst, proj = write_prefix_trunk(level, ranks, brush_names, other_names, n)
    golden = proj / f"golden_n{n:03d}.dx"
    if golden.exists() and not force:
        print(f"  [n={n}] reusing existing golden {golden}")
    else:
        cmd = [PYEXE, str(BUILD_SCRIPT), "--trunk", str(dst), "--out", str(golden),
               "--world-only", "--no-light", "--no-obj-load", "--overwrite"]
        print(f"  [n={n}] building editor golden: {' '.join(cmd)}", flush=True)
        r = subprocess.run(cmd, cwd=str(ROOT))
        if r.returncode != 0:
            raise RuntimeError(f"build_ued_golden.py failed for n={n} (rc={r.returncode})")
    return parse_golden(golden)


def compare(level, ranks, brush_names, other_names, n, *, force=False):
    nm = native_prefix_counts(level, brush_names, n)
    gm = editor_prefix_counts(level, ranks, brush_names, other_names, n, force=force)
    d_nodes = len(nm.nodes) - len(gm.nodes)
    d_leaves = len(nm.leaves) - len(gm.leaves)
    d_surfs = len(nm.surfs) - len(gm.surfs)
    print(f"n={n:3d} brush={brush_names[n-1]:20s} native(nodes={len(nm.nodes)},surfs={len(nm.surfs)},leaves={len(nm.leaves)}) "
          f"editor(nodes={len(gm.nodes)},surfs={len(gm.surfs)},leaves={len(gm.leaves)}) "
          f"d_nodes={d_nodes:+d} d_surfs={d_surfs:+d} d_leaves={d_leaves:+d}")
    return d_nodes, d_surfs, d_leaves


def main():
    level, ranks, brush_names, other_names = load_source()
    assert len(brush_names) == 141, f"expected 141 structural world-csg brushes, got {len(brush_names)}"

    args = sys.argv[1:]
    if args and args[0] == "--search":
        lo, hi = 1, len(brush_names)
        # invariant: at n=lo everything (so far checked) is EXACT; at n=hi it's NOT exact.
        # first confirm hi is indeed non-exact (full 141 known -38/-23) and find a exact lo via n=1.
        d = compare(level, ranks, brush_names, other_names, hi)
        if d == (0, 0, 0):
            print("full prefix (n=141) is EXACT -- nothing to localize (unexpected, stop).")
            return 0
        d0 = compare(level, ranks, brush_names, other_names, lo)
        if d0 != (0, 0, 0):
            print(f"n={lo} ALREADY diverges -- cannot binary search from lo=1, inspect directly.")
            return 0
        while hi - lo > 1:
            mid = (lo + hi) // 2
            d = compare(level, ranks, brush_names, other_names, mid)
            if d == (0, 0, 0):
                lo = mid
            else:
                hi = mid
        print(f"\nFIRST DIVERGING BRUSH: n={hi} -> {brush_names[hi-1]} "
              f"(prefix n={lo}={brush_names[lo-1]} is exact, n={hi} is not)")
        return 0

    ns = [int(a) for a in args] if args else [141]
    for n in ns:
        compare(level, ranks, brush_names, other_names, n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

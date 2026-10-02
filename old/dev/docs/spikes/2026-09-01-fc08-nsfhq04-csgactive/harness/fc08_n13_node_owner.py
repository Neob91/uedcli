#!/usr/bin/env python3
"""Per-brush node-plane-owner attribution on the fc08 13-brush minimal reproduction (n=13):
native under-builds by -12 nodes/-4 leaves vs the live editor golden the instant Brush47 (13th
structural brush in CSG order) is added; brushes 1-12 alone are byte-exact. Attributes each
node's owning brush via node.i_surf -> surf.i_actor (node-owner method from
`fc08_node_owner_diff.py`), scaled down to this much smaller, already-isolated case.
"""
import os
import sys
from pathlib import Path
from collections import Counter

ROOT = Path("/workspace/uedcli")
WORKTREE = ROOT / ".claude/worktrees/nsfhq04-residual-investigation"
# See prefix_search_lib.py's comment: import `uedcli`/`uedcli_native` from the ISOLATED WORKTREE,
# never the shared main checkout (a concurrent agent has in-flight, uncommitted CsgOper edits there).
sys.path.insert(0, str(WORKTREE))
sys.path.insert(0, str(WORKTREE / "dev/docs/spikes/2026-07-15-native-materialize/harness"))
sys.path.insert(0, str(WORKTREE / "dev/docs/spikes/2026-06-27-decontainerize-uedcli/harness"))
os.environ.setdefault("UEDCLI_PROJECT", str(ROOT / "_scratch/fc08-structural-only"))

from uedcli import trunk                          # noqa: E402
from uedcli.native import brush_marshal as BM      # noqa: E402
from uedcli.native import umodel as UM             # noqa: E402
import uedcli_native                               # noqa: E402
import utexture_decode as UT                       # noqa: E402
from spike_classindex import class_index           # noqa: E402

SRC_TRUNK = ROOT / "_scratch/fc08-structural-only/maps/freeclinic08"
GOLDEN = ROOT / "_scratch/fc08-prefix/n013/golden_n013.dx"


def main():
    level, _ranks = trunk.read_level(SRC_TRUNK)
    ci = class_index()
    brush_names = [n for n in level.order
                   if level.actors[n].brush is not None and BM._in_world_csg(level.actors[n], ci)]
    names13 = brush_names[:13]
    print("13 brushes in CSG order:", names13)

    ins = [BM._build_brush_input(nm, level.actors[nm]) for nm in names13]
    built = uedcli_native.build_geometry_bspcsg(ins)
    nbody = uedcli_native.serialize_model(built)
    nm = UM.parse_model_body(nbody, 0, len(nbody))

    pkg = UT.load_package(str(GOLDEN))
    models = [i for i in range(len(pkg.exports)) if pkg.class_of_export(i) == "Model"]
    mi = max(models, key=lambda i: pkg.exports[i]["ssize"])
    gm = UM.parse_model_body(pkg.buf, pkg.exports[mi]["soff"], pkg.exports[mi]["ssize"])

    def node_owner_counts(model, resolve_actor_idx):
        c = Counter()
        for node in model.nodes:
            isurf = node.i_surf
            if isurf < 0 or isurf >= len(model.surfs):
                c["<invalid>"] += 1
                continue
            iactor = model.surfs[isurf].i_actor
            c[resolve_actor_idx(iactor)] += 1
        return c

    # native: i_actor is 0-based world-csg brush index into `names13`
    def native_resolve(iactor):
        if iactor is None or iactor < 0 or iactor >= len(names13):
            return f"<bad:{iactor}>"
        return names13[iactor]

    # golden: i_actor is a compact-index ref into the package's export/import table; resolve via
    # epkg.name_of_ref if available, else fall back to raw index.
    try:
        resolve_name = pkg.name_of_ref
    except AttributeError:
        resolve_name = None

    def golden_resolve(iactor):
        if resolve_name is not None:
            try:
                return resolve_name(iactor)
            except Exception:
                return f"<ref:{iactor}>"
        return f"<ref:{iactor}>"

    nc = node_owner_counts(nm, native_resolve)
    gc = node_owner_counts(gm, golden_resolve)

    print(f"\nnative nodes={len(nm.nodes)} golden nodes={len(gm.nodes)}")
    print(f"{'brush':20s} {'native':>7s} {'golden':>7s} {'delta':>7s}")
    all_keys = sorted(set(nc) | set(gc))
    for k in all_keys:
        n_ = nc.get(k, 0)
        g_ = gc.get(k, 0)
        if n_ != g_:
            print(f"{str(k):20s} {n_:7d} {g_:7d} {n_-g_:+7d}")


if __name__ == "__main__":
    raise SystemExit(main())

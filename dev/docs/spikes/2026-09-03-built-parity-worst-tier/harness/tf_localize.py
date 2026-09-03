#!/usr/bin/env python3
"""TrainingFinal first-divergence (`Brush162`, world-CSG idx 686) offline localization: authored
shape, world-bbox overlap candidates among the first 686 brushes, and native counts for candidate
2-brush subsets (`pairs`). Mirrors `wg_localize.py`."""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import prefix_search_lib as PSL  # noqa: E402
from uedcli import rotation as ROT  # noqa: E402
from uedcli.native import brush_marshal as BM  # noqa: E402
from uedcli.native import umodel as UM  # noqa: E402
import uedcli_native  # noqa: E402

CACHE = Path("/workspace/uedcli/.claude/worktrees/breadth-parity-check/_scratch/uedcli-parity-cache"
             "/f3e6539d9ed950dcf1dfb5929040e2da07b37f263727c360fdf2de63e2e73d27/trunk")
TARGET = "Brush162"
PAD = 1.0


def bbox(actor):
    vs = ROT.world_vertices(actor)
    xs, ys, zs = zip(*vs)
    return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))


def overlaps(a, b, pad=PAD):
    (alo, ahi), (blo, bhi) = a, b
    return all(alo[i] - pad <= bhi[i] + pad and blo[i] - pad <= ahi[i] + pad for i in range(3))


def counts(ps, names):
    ins = [BM._build_brush_input(nm, ps.level.actors[nm]) for nm in names]
    built = uedcli_native.build_geometry_bspcsg(ins)
    body = uedcli_native.serialize_model(built)
    m = UM.parse_model_body(body, 0, len(body))
    return len(m.nodes), len(m.surfs), len(m.leaves)


def main():
    ps = PSL.PrefixSearch("00_trainingfinal", CACHE / "maps/00_trainingfinal",
                          Path("/tmp/tf-localize-unused"), CACHE)
    ti = ps.brush_names.index(TARGET)
    ta = ps.level.actors[TARGET]
    tprops = dict(ta.props)
    print(f"{TARGET}: idx {ti}, polys={len(ta.brush.polys)}, CsgOper={tprops.get('CsgOper')}, "
          f"Rotation={tprops.get('Rotation')}, PrePivot={tprops.get('PrePivot')}, "
          f"Location={ta.location}")
    tb = bbox(ta)
    print(f"{TARGET} bbox: {tb}")
    cands = []
    for nm in ps.brush_names[:ti]:
        a = ps.level.actors[nm]
        if overlaps(bbox(a), tb):
            cands.append(nm)
            p = dict(a.props)
            print(f"  overlap: {nm} (idx {ps.brush_names.index(nm)}) CsgOper={p.get('CsgOper')} "
                  f"polys={len(a.brush.polys)} Rotation={p.get('Rotation')}")
    if "pairs" in sys.argv[1:]:
        for nm in cands:
            print(f"  [{nm}] alone: {counts(ps, [nm])}  +{TARGET}: {counts(ps, [nm, TARGET])}")
        print(f"  cands+{TARGET}: {counts(ps, cands + [TARGET])}  cands alone: {counts(ps, cands)}")


if __name__ == "__main__":
    main()

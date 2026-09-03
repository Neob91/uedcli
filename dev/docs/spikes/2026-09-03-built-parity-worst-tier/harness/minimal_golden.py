#!/usr/bin/env python3
"""Live minimal-case A/B: build an editor golden for an arbitrary brush SUBSET of a cached level
trunk (all non-brush actors kept, listed brushes only, trunk order preserved) and compare counts
against the native build of the same subset. Generalizes `wg_minimal_golden.py` (the Garage
[Brush20, Brush21] pair case, which printed editor 58/32/12 == native — pairwise-exact).

Usage: minimal_golden.py <level_name> <cache_hash> <tag> <Brush> [Brush ...] [--force]
"""
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import prefix_search_lib as PSL  # noqa: E402
from uedcli import trunk as TR  # noqa: E402
from uedcli.native import brush_marshal as BM  # noqa: E402
from uedcli.native import umodel as UM  # noqa: E402
import uedcli_native  # noqa: E402

CACHES = Path("/workspace/uedcli/.claude/worktrees/breadth-parity-check/_scratch/uedcli-parity-cache")


def main():
    level_name, cache_hash, tag = sys.argv[1], sys.argv[2], sys.argv[3]
    force = "--force" in sys.argv
    keep_brushes = [a for a in sys.argv[4:] if not a.startswith("--")]
    cache = CACHES / cache_hash / "trunk"
    wt = HERE.parents[4]
    ps = PSL.PrefixSearch(level_name, cache / f"maps/{level_name}",
                          wt / f"_scratch/{tag}-minimal", cache)
    missing = [b for b in keep_brushes if b not in set(ps.brush_names)]
    if missing:
        raise SystemExit(f"not world-CSG brushes of {level_name}: {missing}")
    keep = set(ps.other_names) | set(keep_brushes)
    new_order = [nm for nm in ps.level.order if nm in keep]
    dst = ps.prefix_root / "case" / f"maps/{level_name}"
    if dst.exists():
        shutil.rmtree(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    new_level = type(ps.level)(
        actors={k: v for k, v in ps.level.actors.items() if k in keep}, order=new_order)
    TR.write_level(dst, new_level, {k: v for k, v in ps.ranks.items() if k in keep})
    proj = dst.parent.parent
    (proj / "uedcli.toml").write_text('game = "deusex"\nmaps = "maps"\n')
    golden = proj / "golden_case.dx"
    if not golden.exists() or force:
        ps._yield_editor_slot()
        cmd = [PSL.PYEXE, str(PSL.BUILD_SCRIPT), "--trunk", str(dst), "--out", str(golden),
               "--world-only", "--no-light", "--no-obj-load", "--overwrite"]
        print("building:", " ".join(cmd), flush=True)
        r = subprocess.run(cmd, cwd=str(PSL.WORKTREE))
        if r.returncode != 0:
            raise SystemExit(f"golden build failed rc={r.returncode}")
    em = ps._parse_golden(golden)
    ordered = [nm for nm in ps.brush_names if nm in set(keep_brushes)]
    ins = [BM._build_brush_input(nm, ps.level.actors[nm]) for nm in ordered]
    built = uedcli_native.build_geometry_bspcsg(ins)
    body = uedcli_native.serialize_model(built)
    nm = UM.parse_model_body(body, 0, len(body))
    print(f"case {ordered}:")
    print(f"  native nodes={len(nm.nodes)} surfs={len(nm.surfs)} leaves={len(nm.leaves)}")
    print(f"  editor nodes={len(em.nodes)} surfs={len(em.surfs)} leaves={len(em.leaves)}")
    print(f"  golden: {golden}")


if __name__ == "__main__":
    main()

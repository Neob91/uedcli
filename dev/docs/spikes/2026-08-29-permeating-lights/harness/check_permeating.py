#!/usr/bin/env python3
"""Compare native's `Model.Lights` region 1 (permeating_lights.rs) against a fresh UnrealEd LIT
golden, offline -- no live editor needed for the native side, only for building the golden once.

Rebuild the golden first (see native-light-apply-bake-where-it-stands-and's reproduce commands):
    H=dev/docs/spikes/2026-08-27-native-light-apply-parity/harness
    .venv/bin/python $H/build_ued_lit_golden.py --trunk _scratch/bsp-parity-proj/maps/unatco \\
        --out <out>/golden.dx --overwrite
Then point GOLDEN below at it and run this script with `.venv/bin/python`.

Usage: .venv/bin/python check_permeating.py
"""
import os, sys
from pathlib import Path
os.environ["UEDCLI_PROJECT"] = "/workspace/uedcli/_scratch/bsp-parity-proj"
ROOT = Path("/workspace/uedcli")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness/editor-tree-oracle"))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-08-27-native-light-apply-parity/harness"))
from uedcli import trunk, config
from uedcli.classdefaults import ClassDefaults
from uedcli.packages import schema_resolver
from uedcli.native import materialize as M
from spike_classindex import class_index
from lightparity import _load, level_model

TRUNK = Path("/workspace/uedcli/_scratch/bsp-parity-proj/maps/unatco")
GOLDEN = "/workspace/uedcli/_scratch/permeating-check-2026-08-29/golden.dx"

lvl, _ranks = trunk.read_level(TRUNK)
proj = config.load_project(str(TRUNK.parent.parent))
user_cfg = config.load_user_config()
defaults = ClassDefaults(schema_resolver(proj, user_cfg))
index = class_index()
lights = M.gather_lights(lvl, defaults=defaults)
light_names = [n for n, *_r in lights]
print(f"gather_lights: {len(lights)} participating lights")

native_model, _csg = M.build_world_model(lvl, index=index, lights=lights)

def native_run(m, leaf_idx):
    lf = m.leaves[leaf_idx]
    if lf.i_permeating < 0:
        return None
    out, i = [], lf.i_permeating
    while m.lights[i] != -1:
        out.append(light_names[m.lights[i]]); i += 1
    return out

n_marked = [i for i, lf in enumerate(native_model.leaves) if lf.i_permeating >= 0]
n_total = sum(len(native_run(native_model, i)) for i in n_marked)
print(f"native: {len(n_marked)}/{len(native_model.leaves)} leaves marked, {n_total} region-1 entries")
print(f"native leaf[0]: {native_run(native_model, 0)}")

repo = str(ROOT)
upackage, umodel = _load(repo)
pkg, gm = level_model(upackage, umodel, GOLDEN)
gnames = [None if r == 0 else pkg.name_of_ref(r) for r in gm.lights]

def golden_run(leaf_idx):
    lf = gm.leaves[leaf_idx]
    if getattr(lf, "i_permeating", -1) < 0:
        return None
    out, i = [], lf.i_permeating
    while gnames[i] is not None:
        out.append(gnames[i]); i += 1
    return out

g_marked = [i for i, lf in enumerate(gm.leaves) if getattr(lf, "i_permeating", -1) >= 0]
g_total = sum(len(golden_run(i)) for i in g_marked)
print(f"golden: {len(g_marked)}/{len(gm.leaves)} leaves marked, {g_total} region-1 entries")
print(f"golden leaf[0]: {golden_run(0)}")
print(f"native nodes/surfs/leaves: {len(native_model.nodes)}/{len(native_model.surfs)}/{len(native_model.leaves)}")
print(f"golden nodes/surfs/leaves: {len(gm.nodes)}/{len(gm.surfs)}/{len(gm.leaves)}")

exact = 0
mismatches = []
for i in range(min(len(native_model.leaves), len(gm.leaves))):
    nr, gr = native_run(native_model, i), golden_run(i)
    if (nr or []) == (gr or []):
        exact += 1
    else:
        mismatches.append((i, nr, gr))
print(f"leaves with EXACT matching run (order+content): {exact}/{min(len(native_model.leaves), len(gm.leaves))}")
for i, nr, gr in mismatches[:10]:
    print(f"  leaf {i}: native={nr} golden={gr}")

"""Diff two built packages' per-lightmap light RUNS, naming the surf and nodes that own each.

    lmdiag.py <native.dx> <ref.dx>          # run from the repo root

Replaces `2026-09-03-incremental-actor-parity/harness/lightrun_diff.py` for anything that needs the
SURF: that one mis-decodes `FBspSurf` (it reads `iBrushPoly` where `iLightMap` is), so its `surf=`
column names the wrong surface. Its run comparison is fine.
"""
import sys
sys.path.insert(0, '.')
H = 'dev/docs/spikes/2026-09-03-incremental-actor-parity/harness'
sys.path.insert(0, H)
import model_dump as md
import parity_gate as pg
from uedcli.upackage import load_package


def load(path):
    p = load_package(path)
    for i, e in enumerate(p.exports):
        if (p.object_class_name(i + 1) or "") == "Model" and p.names[e["nm"]].lower() == "model2":
            break
    d = md.decode(p, i)
    idt = pg.Ident(p)
    lights = [idt.ref_identity(v) for v in d["lights"]]
    return p, idt, d, lights


def runs(d, lights):
    out = {}
    for i, (raw, tex, la, tail) in enumerate(d["lightmap"]):
        r = []
        j = la
        while 0 <= j < len(lights) and lights[j] != "None":
            r.append(lights[j]); j += 1
        out[i] = tuple(r)
    return out


pa, ia, da, ga = load(sys.argv[1])
pb, ib, db, gb = load(sys.argv[2])
ra, rb = runs(da, ga), runs(db, gb)
lm2surf_a = {}
for k, s in enumerate(da["surfs"]):
    lm2surf_a.setdefault(s[2][4], []).append(k)
lm2surf_b = {}
for k, s in enumerate(db["surfs"]):
    lm2surf_b.setdefault(s[2][4], []).append(k)
surf2node_a = {}
for ni, n in enumerate(da["nodes"]):
    surf2node_a.setdefault(n[3][1], []).append(ni)
print("lights", len(ga), len(gb), "lightmaps", len(da["lightmap"]), len(db["lightmap"]),
      "surfs", len(da["surfs"]), len(db["surfs"]))
bad = 0
for i in sorted(set(ra) & set(rb)):
    if ra[i] != rb[i]:
        bad += 1
        sa = lm2surf_a.get(i, [])
        sb = lm2surf_b.get(i, [])
        print(f"LM[{i}] nat_surf={sa} ued_surf={sb}")
        for s in sa:
            t = da["surfs"][s]
            print(f"    nat surf {s}: flags={t[1]:#x} actor={ia.ref_identity(t[4])} nodes={surf2node_a.get(s, [])}")
        for s in sb:
            t = db["surfs"][s]
            print(f"    ued surf {s}: flags={t[1]:#x} actor={ib.ref_identity(t[4])}")
        print(f"    nat={ra[i]}\n    ued={rb[i]}")
print("differing runs:", bad)

#!/usr/bin/env python3
"""Per-FIELD diff of two built packages' world `Model2` arrays — what localized OceanLab N=46.

`model_dump.py` prints every differing node/surf/vert WHOLE, so a divergence in one field drowns in
the masked ones (`node_flags`' render-occlusion bits, orphan `iVertex`, remapped `ObjRef`s). This
counts the differences PER FIELD instead, applies the gate's `node_flags & ~0x18` mask, and splits
the Verts diff into live-ring slots (compared by the gate) and orphans (excluded), so a 3041-entry
Verts diff reads as the 0 real ones it is.

Run: model_field_diff.py <native.dx> <ued22.dx>
"""
import sys, os

sys.path.insert(0, os.getcwd())
HARNESS = "dev/docs/spikes/2026-09-03-incremental-actor-parity/harness"
sys.path.insert(0, os.path.abspath(HARNESS))
import parity_gate as pg
import model_dump as md

A, B = sys.argv[1], sys.argv[2]
P, Q = pg.load_package(A), pg.load_package(B)
da, db = md.decode(P, md.find(P, "model2")), md.decode(Q, md.find(Q, "model2"))

FIELDS = ["iVertPool", "iSurf", "iBack", "iFront", "iPlane", "iCollBound",
          "iRenderBound", "iZone0", "iZone1", "NumVerts"]
counts: dict[str, int] = {}
first: dict[str, tuple] = {}


def note(key, detail):
    counts[key] = counts.get(key, 0) + 1
    first.setdefault(key, detail)


for i, (na, nb) in enumerate(zip(da["nodes"], db["nodes"])):
    if na[0] != nb[0]:
        note("plane", (i, na[0], nb[0]))
    if na[1] != nb[1]:
        note("zonemask", (i, na[1], nb[1]))
    if (na[2] & ~0x18) != (nb[2] & ~0x18):     # gate masks NF_PolyOccluded|NF_BoxOccluded
        note("nodeflags", (i, na[2], nb[2]))
    for k, (x, y) in enumerate(zip(na[3], nb[3])):
        if x != y:
            note(FIELDS[k], (i, na[3], nb[3]))
    if na[4] != nb[4]:
        note("iLeaf", (i, na[4].hex(), nb[4].hex()))
print("NODES", len(da["nodes"]))
for k, v in counts.items():
    print(f"  {k:14s} {v:5d}  first={first[k]}")

SF = ["pBase", "vNormal", "vTextureU", "vTextureV", "iLightMap", "iBrushPoly"]
counts, first = {}, {}
for i, (a, b) in enumerate(zip(da["surfs"], db["surfs"])):
    if a[0] != b[0]:
        note("texture", (i, a[0], b[0]))
    if a[1] != b[1]:
        note("polyflags", (i, hex(a[1]), hex(b[1])))
    for k, (x, y) in enumerate(zip(a[2], b[2])):
        if x != y:
            note(SF[k], (i, a[2], b[2]))
    if a[3] != b[3]:
        note("lightmapidx", (i, a[3], b[3]))
    if a[4] != b[4]:
        note("actor", (i, a[4], b[4]))
print("SURFS", len(da["surfs"]))
for k, v in counts.items():
    print(f"  {k:14s} {v:5d}  first={first[k]}")

live = {vp + k for n in da["nodes"] for vp, nv in [(n[3][0], n[3][9])] for k in range(nv)}
live |= {vp + k for n in db["nodes"] for vp, nv in [(n[3][0], n[3][9])] for k in range(nv)}
vd = [(i, a, b) for i, (a, b) in enumerate(zip(da["verts"], db["verts"])) if a != b]
vd_live = [t for t in vd if t[0] in live]
print(f"VERTS diff {len(vd)} ({len(vd_live)} on LIVE ring slots) first live: {vd_live[:4]}")

for key in ("bounds", "leafhulls", "lights", "lightmap", "leaves", "zones"):
    x, y = da[key], db[key]
    d = [i for i in range(min(len(x), len(y))) if x[i] != y[i]]
    print(f"{key}: {len(d)} differ of {len(x)}; first idx {d[:5]}")

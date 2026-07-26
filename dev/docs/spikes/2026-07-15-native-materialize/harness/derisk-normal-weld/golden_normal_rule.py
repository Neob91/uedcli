#!/usr/bin/env python3
"""§92 §50 follow-up (OFFLINE) — decide which downstream rule the editor uses for the Brush755
dome-facet node-plane NORMAL twins, using the UnrealEd golden `.dx` bits (no live editor).

For each Brush755 dome face, anchor on native's ACTUAL N=105 stored surf normal (the §48
`R·calc_normal(local)` emit) and match the corresponding golden surf (by normal-direction + plane
offset).  Then classify each golden twin against the three §50 candidates:

  (a) WORLD-frame plane   — `calc_normal(world = local+loc, f32)`
  (b) bspAddVector POOL   — golden reuses a NEIGHBOUR's pooled vector (goldshare > 1)
  (c) neither             — a small ±1-2 ULP perturbation of `calc_normal(local)`

RESULT (2026-07-20, full golden `_scratch/uedgolden/UEDGolden_unatco_world.dx`):
  * native==golden bits on 59/78 dome faces; 19 twins.
  * (a) REFUTED — `calc_normal(world)` is HUNDREDS of ULP off (catastrophic cancellation of the
    large (540,1204,276) offset against v0; local coords are only |<=32|).  0 twins are world-explained.
  * (b) REFUTED — every twin golden normal has goldshare == 1 (its own dedicated vector), never a
    shared/pooled neighbour value.
  * (c) CONFIRMED — golden is a NON-systematic ±1-2 ULP scatter off `calc_normal(local)`
    (delta dist +2:23 +1:15 -2:8 -1:2 over nonzero comps); no accumulation/normalization variant
    over the EXACT local verts reproduces it (best 2/19).  The perturbation is in the VERTICES the
    editor feeds CalcNormal downstream (the world-CSG `bspAddPoint` pool, §15/§17) — gdb-only for the
    exact bits; NO castle-safe offline rule closes it.

Usage: golden_normal_rule.py [golden.dx]
"""
import sys, struct, math
from collections import Counter
from pathlib import Path

ROOT = Path("/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedcli")
HARNESS = ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(HARNESS))
import surf_class_diff as SCD           # noqa: E402
import unatco_subset as U               # noqa: E402
from spike_classindex import class_index  # noqa: E402  (schema-aware mover gate's index)
from uedcli import trunk                # noqa: E402
from uedcli.native import materialize as M, umodel as UM  # noqa: E402
import uedcli_native                    # noqa: E402

r32 = lambda x: struct.unpack("<f", struct.pack("<f", x))[0]
bits = lambda x: struct.unpack("<I", struct.pack("<f", x))[0]
ibits = lambda x: struct.unpack("<i", struct.pack("<f", x))[0]
fb = lambda t: tuple(bits(c) for c in t)
hx = lambda t: ",".join(f"{bits(c):#010x}" for c in t)


def cross(a, b):
    return (r32(r32(a[1]*b[2])-r32(a[2]*b[1])), r32(r32(a[2]*b[0])-r32(a[0]*b[2])), r32(r32(a[0]*b[1])-r32(a[1]*b[0])))


def sub(a, b):
    return (r32(a[0]-b[0]), r32(a[1]-b[1]), r32(a[2]-b[2]))


def calc_normal(verts):  # native fan-sum f32 op-order (§16), f32-inv normalize
    n = [0.0, 0.0, 0.0]; v0 = verts[0]
    for i in range(2, len(verts)):
        c = cross(sub(verts[i-1], v0), sub(verts[i], v0))
        n = [r32(n[0]+c[0]), r32(n[1]+c[1]), r32(n[2]+c[2])]
    m2 = r32(r32(r32(n[0]*n[0])+r32(n[1]*n[1]))+r32(n[2]*n[2]))
    inv = r32(1.0/r32(math.sqrt(float(m2))))
    return (r32(n[0]*inv), r32(n[1]*inv), r32(n[2]*inv))


def main():
    gpath = sys.argv[1] if len(sys.argv) > 1 else str(ROOT/"_scratch/uedgolden/UEDGolden_unatco_world.dx")

    # native N=105 in-process (mirror unatco_subset.native_surfs)
    level, _ = trunk.read_level(U.FULL_TRUNK)
    brushes = [nm for nm in U._brush_order(level)[:105] if M._in_world_csg(level.actors[nm], class_index())]
    bs = [M._build_brush_input(nm, level.actors[nm]) for nm in brushes]
    body = uedcli_native.serialize_model(uedcli_native.build_geometry_bspcsg(bs))
    nat = UM.parse_model_body(body, 0, len(body))
    gold = SCD.load_model(gpath)
    print(f"native N=105 surfs={len(nat.surfs)} vecs={len(nat.vectors)}   golden surfs={len(gold.surfs)} vecs={len(gold.vectors)}")

    a = level.actors["Brush755"]; loc = [float(c) for c in a.location]
    gshare = Counter(s.v_normal for s in gold.surfs)

    def surfs_of(model):
        out = []
        for s in model.surfs:
            n = model.vectors[s.v_normal]; b = model.points[s.p_base]
            out.append((n, n[0]*b[0]+n[1]*b[1]+n[2]*b[2], s.v_normal))
        return out
    NS, GS = surfs_of(nat), surfs_of(gold)

    def match(surfs, nl, dw):
        best = None
        for n, off, vi in surfs:
            d = n[0]*nl[0]+n[1]*nl[1]+n[2]*nl[2]; s = 1.0 if d >= 0 else -1.0
            if abs(d) < 0.999 or abs(off - s*dw) > 0.3:
                continue
            sc = abs(abs(d)-1)
            if best is None or sc < best[0]:
                best = (sc, n, off, vi, s)
        return best

    natmatch = twins = world_expl = pooled = 0
    ulps = []
    print("--- twin dome faces: native | golden | Δulp | world? | goldshare ---")
    for pi, p in enumerate(a.brush.polys):
        local = [(r32(float(v[0])), r32(float(v[1])), r32(float(v[2]))) for v in p.vertices]
        world = [(r32(v[0]+loc[0]), r32(v[1]+loc[1]), r32(v[2]+loc[2])) for v in local]
        nl = calc_normal(local); nw = calc_normal(world)
        dw = r32(r32(r32(nl[0]*world[0][0])+r32(nl[1]*world[0][1]))+r32(nl[2]*world[0][2]))
        fn, fg = match(NS, nl, dw), match(GS, nl, dw)
        if fn is None or fg is None:
            continue
        _, nn, _, _, _ = fn
        _, gn, _, gvi, gs = fg
        align = 1.0 if (nn[0]*gn[0]+nn[1]*gn[1]+nn[2]*gn[2]) >= 0 else -1.0
        gna = tuple(align*c for c in gn)
        nwa = tuple((1.0 if (nn[0]*nw[0]+nn[1]*nw[1]+nn[2]*nw[2]) >= 0 else -1.0)*c for c in nw)
        if fb(nn) == fb(gna):
            natmatch += 1
            continue
        twins += 1
        is_world = fb(gna) == fb(nwa)
        if is_world:
            world_expl += 1
        if gshare[gvi] > 1:
            pooled += 1
        for k in range(3):
            if abs(nn[k]) > 1e-6:
                ulps.append(ibits(gna[k]) - ibits(nn[k]))
        print(f" poly{pi:2d} N={hx(nn)} G={hx(gna)} world={is_world} goldshare={gshare[gvi]}")

    print(f"\nnative==golden: {natmatch}   twins: {twins}")
    print(f"(a) WORLD-frame explains : {world_expl}/{twins}")
    print(f"(b) POOL neighbour (goldshare>1): {pooled}/{twins}")
    print(f"(c) golden-minus-native ULP scatter (nonzero comps): {dict(Counter(ulps))}")


if __name__ == "__main__":
    main()

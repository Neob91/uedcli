#!/usr/bin/env python3
"""Section 91 §10 — attribute native's `Vectors +24%` residual (UNATCO: native 745 vs golden 599
vs shipped 596) to its true source, OVERTURNING §4's "extra node-plane normals from the §80
leak-repair flipped planes" hypothesis.

Decode-proven findings (run this to reproduce):
  1. Node planes are stored INLINE in FBspNode (model_write.rs::put_node), NEVER in the Vectors
     array -> the §80 leak-repair flipped planes contribute ZERO vectors.
  2. Surf NORMALS agree: distinct vNormal 257 / 257 / 257 (identical). ("261/259/260" figures in
     older notes are surf-REFERENCE counts pre-dedup; the distinct-vector count is 257 all three.)
  3. The entire +146 excess is TEXTURE AXES (vTextureU/vTextureV): native texU 298 / texV 285
     vs golden 193 / 235.
  4. Surfaces geometrically COMMON to native+golden carry IDENTICAL texture axes (0 negated) ->
     NOT a texture-axis sign/convention bug. The excess axes live on native's EXTRA surfaces
     (native-only geo-keys), which come from the §80 less-merged CSG partition.
  5. The "+82 extra negation pairs" §4 flagged are extra negated TEXTURE-AXIS pairs
     (native texaxis-neg-pairs 248 vs golden 166), NOT plane/normal pairs (equal: 170 vs 168).
  6. The editor (golden) ITSELF keeps 310 negation pairs -> it does NOT fold n/-n, so "dedup n/-n"
     would take native BELOW 599 and diverge from the editor + break castle byte-parity.

Usage: vectors_attribution.py <native.dx> <golden.dx> [shipped.dx]
"""
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path("/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedctl")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-06-27-decontainerize-uedctl/harness"))
from uedctl.native import umodel  # noqa: E402
import utexture_decode as UT  # noqa: E402


def load_model(path):
    pkg = UT.load_package(path)
    models = [i for i in range(len(pkg.exports)) if pkg.class_of_export(i) == "Model"]
    mi = max(models, key=lambda i: pkg.exports[i]["ssize"])
    e = pkg.exports[mi]
    return umodel.parse_model_body(bytes(pkg.buf), e["soff"], e["ssize"])


def k(v, q=1e-3):
    return (round(v[0] / q), round(v[1] / q), round(v[2] / q))


def roles(m):
    normals = {s.v_normal for s in m.surfs if s.v_normal >= 0}
    texu = {s.v_texture_u for s in m.surfs if s.v_texture_u >= 0}
    texv = {s.v_texture_v for s in m.surfs if s.v_texture_v >= 0}
    return normals, texu, texv


def summarize(path, label):
    m = load_model(path)
    normals, texu, texv = roles(m)
    ks = {k(v) for v in m.vectors}
    unref = sum(1 for i in range(len(m.vectors)) if i not in normals and i not in texu and i not in texv)
    nrm_ks = {k(m.vectors[i]) for i in normals}
    tex_ks = {k(m.vectors[i]) for i in (texu | texv)}
    npairs = sum(1 for i in normals if k((-m.vectors[i][0], -m.vectors[i][1], -m.vectors[i][2])) in nrm_ks)
    tpairs = sum(1 for i in (texu | texv)
                 if k((-m.vectors[i][0], -m.vectors[i][1], -m.vectors[i][2])) in tex_ks)
    tot = sum(1 for v in m.vectors
              if k((-v[0], -v[1], -v[2])) in ks and k(v) != k((-v[0], -v[1], -v[2])))
    print(f"=== {label}: {Path(path).name} ===")
    print(f"  Vectors={len(m.vectors)} surfs={len(m.surfs)} nodes={len(m.nodes)} "
          f"UNREF-vectors={unref}")
    print(f"  distinct  vNormal={len(nrm_ks)}  texU={len({k(m.vectors[i]) for i in texu})}  "
          f"texV={len({k(m.vectors[i]) for i in texv})}")
    print(f"  neg-pairs total={tot}  among-normals={npairs}  among-texaxes={tpairs}")
    return m


def geokeys(m):
    s = set()
    for surf in m.surfs:
        base = tuple(round(x, 2) for x in m.points[surf.p_base])
        nrm = tuple(round(x, 3) for x in m.vectors[surf.v_normal]) if surf.v_normal >= 0 else None
        s.add((base, nrm))
    return s


def main():
    native = sys.argv[1]
    golden = sys.argv[2]
    shipped = sys.argv[3] if len(sys.argv) > 3 else None
    mn = summarize(native, "NATIVE")
    mg = summarize(golden, "GOLDEN")
    if shipped:
        summarize(shipped, "SHIPPED")

    common = geokeys(mn) & geokeys(mg)
    print(f"\ngeo-keys (base,normal): native {len(geokeys(mn))} golden {len(geokeys(mg))} "
          f"common {len(common)}")
    # texture-axis diversity attributed to common vs native-only surfaces
    for name, m in [("native", mn), ("golden", mg)]:
        cu, ou, cv, ov = set(), set(), set(), set()
        for surf in m.surfs:
            base = tuple(round(x, 2) for x in m.points[surf.p_base])
            nrm = tuple(round(x, 3) for x in m.vectors[surf.v_normal]) if surf.v_normal >= 0 else None
            gk = (base, nrm)
            tu = tuple(round(x, 4) for x in m.vectors[surf.v_texture_u]) if surf.v_texture_u >= 0 else None
            tv = tuple(round(x, 4) for x in m.vectors[surf.v_texture_v]) if surf.v_texture_v >= 0 else None
            (cu if gk in common else ou).add(tu)
            (cv if gk in common else ov).add(tv)
        print(f"  {name}: texU common-surf={len(cu)} {name}-only-surf={len(ou)}   "
              f"texV common-surf={len(cv)} {name}-only-surf={len(ov)}")

    # §10.4 — per-surf pairwise: for surfaces geometrically common to native+golden, is native's
    # texture axis EQUAL, NEGATED, or OTHER vs golden's?  (If native flipped axes on shared faces
    # we'd see NEG > 0; we don't -> it's not a sign-convention bug.)
    def first_by_geo(m):
        d = {}
        for surf in m.surfs:
            base = tuple(round(x, 2) for x in m.points[surf.p_base])
            nrm = tuple(round(x, 3) for x in m.vectors[surf.v_normal]) if surf.v_normal >= 0 else None
            tu = tuple(round(x, 4) for x in m.vectors[surf.v_texture_u]) if surf.v_texture_u >= 0 else None
            tv = tuple(round(x, 4) for x in m.vectors[surf.v_texture_v]) if surf.v_texture_v >= 0 else None
            d.setdefault((base, nrm), (tu, tv))
        return d

    def rel(a, b):
        if a is None or b is None:
            return "none"
        if all(abs(a[i] - b[i]) < 1e-3 for i in range(3)):
            return "eq"
        if all(abs(a[i] + b[i]) < 1e-3 for i in range(3)):
            return "neg"
        return "other"

    ng = first_by_geo(mn)
    gg = first_by_geo(mg)
    cu = Counter()
    cv = Counter()
    for gk in set(ng) & set(gg):
        cu[rel(ng[gk][0], gg[gk][0])] += 1
        cv[rel(ng[gk][1], gg[gk][1])] += 1
    print(f"\nper-surf texture-axis relation on common geo-keys (native vs golden), "
          f"geo-key = (pBase@0.01, vNormal@0.001):")
    print(f"  texU: eq={cu['eq']} NEG={cu['neg']} other={cu['other']} none={cu['none']}")
    print(f"  texV: eq={cv['eq']} NEG={cv['neg']} other={cv['other']} none={cv['none']}")

    # §10.4 — of native's EXTRA texture axes (native-only vTextureU values), how many are collinear
    # with a golden direction (same/opposite unit vector, different scale) vs a genuinely new
    # direction?  And how do their scale ratios distribute (a systematic scale bug would cluster)?
    import math

    def unit(v):
        L = math.sqrt(sum(x * x for x in v))
        return tuple(x / L for x in v) if L > 1e-9 else v

    def texu_set(m):
        return {tuple(round(x, 5) for x in m.vectors[s.v_texture_u])
                for s in m.surfs if s.v_texture_u >= 0}

    n_only = texu_set(mn) - texu_set(mg)
    gdirs = defaultdict(list)
    for gv in texu_set(mg):
        gdirs[tuple(round(x, 3) for x in unit(gv))].append(math.sqrt(sum(x * x for x in gv)))
    collinear = new_dir = 0
    ratios = Counter()
    for v in n_only:
        d = tuple(round(x, 3) for x in unit(v))
        dn = tuple(round(-x, 3) for x in unit(v))
        cand = gdirs.get(d) or gdirs.get(dn)
        if cand:
            collinear += 1
            L = math.sqrt(sum(x * x for x in v))
            ratios[round(L / min(cand, key=lambda g: abs(g - L)), 1)] += 1
        else:
            new_dir += 1
    print(f"\nnative-only texU ({len(n_only)}): collinear-with-golden-dir={collinear} "
          f"genuinely-new-direction={new_dir}")
    print(f"  scale-ratio (native/golden) distribution: {dict(sorted(ratios.items()))}")
    carriers = Counter()
    for s in mn.surfs:
        if s.v_texture_u >= 0 and tuple(round(x, 5) for x in mn.vectors[s.v_texture_u]) in n_only:
            carriers[s.texture_ref] += 1
    print(f"  carried by {sum(carriers.values())} surfs across {len(carriers)} texture refs")


if __name__ == "__main__":
    main()

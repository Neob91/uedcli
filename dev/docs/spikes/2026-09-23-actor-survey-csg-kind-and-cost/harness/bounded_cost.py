"""Measure what `actor survey` actually costs per tier, and check the bounded-neighborhood
truncation against the full-level solve on real content.

Two questions, one script:

1. **Cost.** Per level: trunk load, a full-level native CSG solve, the whole-level raw-tier graph
   (`actorgraph.build_graph`), and the neighborhood-scoped versions of both for one surveyed actor.

2. **Correctness of the truncation.** The claim under test: *the resolved solid/void labelling
   inside a region R depends only on the brushes whose own volume meets R, because a CSG operation
   changes the labelling only inside its own brush.* So solving over `{brushes whose world AABB
   intersects R}` (trunk order preserved) should reproduce, inside R, exactly what the full-level
   solve produces.

   Checked by comparing FACE SIGNATURES: every surviving world face is clipped to R and its area
   accumulated per `(owner actor, owner poly index)`. Full and truncated must agree key-for-key,
   with each area matching to `--area-tol` relative. Faces are compared by owner + clipped area
   rather than by polygon identity on purpose — a different BSP split of the same surface is not a
   divergence, and `actor survey`'s `csg` tier deliberately names no poly index.

Usage:  .venv/bin/python dev/docs/spikes/<slug>/harness/bounded_cost.py [--levels N] [--samples N]
"""
from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
import time
from pathlib import Path

import corpus

PAD = 1.0          # uu the neighborhood region is grown by before selecting brushes


# ------------------------------------------------------------------ geometry helpers

def _clip_to_halfspace(poly, axis, limit, keep_below):
    """Clip a 3-D convex polygon by one axis-aligned half-space."""
    out = []
    n = len(poly)
    for i in range(n):
        cur, prev = poly[i], poly[i - 1]
        cur_in = (cur[axis] <= limit) if keep_below else (cur[axis] >= limit)
        prev_in = (prev[axis] <= limit) if keep_below else (prev[axis] >= limit)
        if cur_in != prev_in:
            t = (limit - prev[axis]) / (cur[axis] - prev[axis])
            out.append(tuple(prev[k] + t * (cur[k] - prev[k]) for k in range(3)))
        if cur_in:
            out.append(cur)
    return out


def clip_to_box(poly, lo, hi):
    for axis in range(3):
        poly = _clip_to_halfspace(poly, axis, hi[axis], True)
        if not poly:
            return []
        poly = _clip_to_halfspace(poly, axis, lo[axis], False)
        if not poly:
            return []
    return poly


def poly_area(poly) -> float:
    """Newell's method — correct for any planar polygon, unlike a 3-point cross product."""
    if len(poly) < 3:
        return 0.0
    nx = ny = nz = 0.0
    for i in range(len(poly)):
        a, b = poly[i], poly[(i + 1) % len(poly)]
        nx += (a[1] - b[1]) * (a[2] + b[2])
        ny += (a[2] - b[2]) * (a[0] + b[0])
        nz += (a[0] - b[0]) * (a[1] + b[1])
    return 0.5 * (nx * nx + ny * ny + nz * nz) ** 0.5


def face_signature(surfaces, lo, hi) -> dict:
    """`{(owner name, owner poly index): (clipped area, [clipped polygons])}` over every face
    meeting the box. One key can hold several polygons — the same surface split differently."""
    sig: dict = {}
    for s in surfaces:
        clipped = clip_to_box([tuple(float(c) for c in v) for v in s.world_verts], lo, hi)
        area = poly_area(clipped)
        if area <= 1e-9:
            continue
        key = (s.actor.name if s.actor else None, s.poly_index)
        prev_area, prev_polys = sig.get(key, (0.0, []))
        sig[key] = (prev_area + area, prev_polys + [clipped])
    return sig


def _plane_basis(poly):
    """An orthonormal (origin, u, v) for a planar polygon's own plane."""
    o = poly[0]
    ux, uy, uz = (poly[1][i] - o[i] for i in range(3))
    ul = (ux * ux + uy * uy + uz * uz) ** 0.5 or 1.0
    u = (ux / ul, uy / ul, uz / ul)
    nx = ny = nz = 0.0
    for i in range(len(poly)):
        a, b = poly[i], poly[(i + 1) % len(poly)]
        nx += (a[1] - b[1]) * (a[2] + b[2])
        ny += (a[2] - b[2]) * (a[0] + b[0])
        nz += (a[0] - b[0]) * (a[1] + b[1])
    nl = (nx * nx + ny * ny + nz * nz) ** 0.5 or 1.0
    n = (nx / nl, ny / nl, nz / nl)
    v = (n[1] * u[2] - n[2] * u[1], n[2] * u[0] - n[0] * u[2], n[0] * u[1] - n[1] * u[0])
    return o, u, v


def _to_2d(poly, o, u, v):
    return [(sum((p[i] - o[i]) * u[i] for i in range(3)),
             sum((p[i] - o[i]) * v[i] for i in range(3))) for p in poly]


def _clip_2d(subject, clip):
    """Sutherland-Hodgman, `clip` convex and CCW."""
    out = list(subject)
    n = len(clip)
    for i in range(n):
        if not out:
            return []
        (cx0, cy0), (cx1, cy1) = clip[i], clip[(i + 1) % n]
        ex, ey = cx1 - cx0, cy1 - cy0
        inside = lambda p: (p[0] - cx0) * ey - (p[1] - cy0) * ex <= 1e-12   # noqa: E731
        new = []
        for j in range(len(out)):
            cur, prev = out[j], out[j - 1]
            if inside(cur) != inside(prev):
                d = ((cur[0] - prev[0]) * ey - (cur[1] - prev[1]) * ex)
                if abs(d) > 1e-15:
                    t = ((cx0 - prev[0]) * ey - (cy0 - prev[1]) * ex) / d
                    new.append((prev[0] + t * (cur[0] - prev[0]), prev[1] + t * (cur[1] - prev[1])))
            if inside(cur):
                new.append(cur)
        out = new
    return out


def _ccw(poly):
    a = sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1]
            for i in range(len(poly)))
    return list(reversed(poly)) if a < 0 else poly


def _area_2d(poly):
    if len(poly) < 3:
        return 0.0
    return abs(sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1]
                   for i in range(len(poly)))) / 2.0


def sym_diff(polys_a, polys_b) -> tuple[float, float]:
    """`(symmetric-difference area, perimeter of A)` for two sets of coplanar polygons.

    Both sets are different subdivisions of the SAME surface, so the polygons WITHIN each set are
    disjoint and `area(A ∩ B) = Σ area(clip(a, b))` is exact. The symmetric difference is then
    `area(A) + area(B) − 2·area(A ∩ B)` — unlike a vertex-to-vertex distance, it does not care how
    either side was subdivided. Divided by the perimeter it gives the implied boundary displacement,
    which is the number to compare against the CSG point-dedup thresholds."""
    o, u, v = _plane_basis(polys_a[0])
    a2 = [_ccw(_to_2d(p, o, u, v)) for p in polys_a]
    b2 = [_ccw(_to_2d(p, o, u, v)) for p in polys_b]
    inter = sum(_area_2d(_clip_2d(b, a)) for a in a2 for b in b2)
    sd = sum(_area_2d(p) for p in a2) + sum(_area_2d(p) for p in b2) - 2 * inter
    per = sum(sum(((p[i][0] - p[i - 1][0]) ** 2 + (p[i][1] - p[i - 1][1]) ** 2) ** 0.5
                  for i in range(len(p))) for p in a2)
    return abs(sd), per


def compare(sig_a: dict, sig_b: dict, tol: float) -> dict:
    keys = set(sig_a) | set(sig_b)
    missing = [k for k in keys if k not in sig_b]
    extra = [k for k in keys if k not in sig_a]
    off = []
    for k in keys:
        if k not in sig_a or k not in sig_b:
            continue
        a, b = sig_a[k][0], sig_b[k][0]
        if abs(a - b) <= tol * max(1.0, a, b):
            continue
        sd, per = sym_diff(sig_a[k][1], sig_b[k][1])
        off.append((k, round(a, 4), round(b, 4), round(sd, 6),
                    round(sd / per, 6) if per else None))
    return {"keys": len(keys), "missing_in_truncated": len(missing),
            "extra_in_truncated": len(extra), "area_mismatch": len(off),
            "max_boundary_shift_uu": max((o[4] for o in off if o[4] is not None), default=0.0),
            "worst": sorted(off, key=lambda t: -t[3])[:3]}


# ------------------------------------------------------------------ neighborhood selection

def region_of(actor, pad=PAD):
    """The actor's world AABB grown by `pad`. Kept in `Decimal` — `writes.aabb_intersects` adds its
    own `Decimal` slack and will not mix with floats."""
    from decimal import Decimal
    from uedcli.writes import actor_bounds
    p = Decimal(str(pad))
    lo, hi = actor_bounds(actor)
    return (tuple(c - p for c in lo), tuple(c + p for c in hi))


def neighborhood(level, index, lo, hi) -> list:
    """Every brush actor whose own world AABB meets the region, in TRUNK ORDER — plus, always, the
    level's FIRST world-CSG brush.

    The first brush is not there for its geometry (it is usually far away and identity on the
    region). It is there because `bsp_brush_csg` special-cases a leading `CSG_Add` against a
    node-less world, seeding it as the WORLD SHELL rather than classifying it (`bspcsg.rs`'s
    `first_add_seed`, whose own comment records the same trap and `brushcsg.build_scaffolding`'s
    workaround for it). Truncation can change which brush is first, and then that shortcut fires on
    the wrong brush: measured, `nsfhq04 DeusExMover31`'s truncated solve lost all four `Brush799`
    faces and gained a `Brush798` one. Keeping the level's own first brush first makes the shortcut
    fire on exactly the brush it fires on in the full solve."""
    from uedcli import movers
    from uedcli.normalize import is_builder_brush
    from uedcli.writes import aabb_intersects
    out, region, have_first = [], (lo, hi), False
    for name in level.order:
        a = level.actors[name]
        if a.brush is None:
            continue
        in_world_csg = not (movers.is_mover(a, index) or is_builder_brush(a))
        near = aabb_intersects(region_of(a, 0.0), region)
        if near or (in_world_csg and not have_first):
            out.append(a)
        if in_world_csg:
            have_first = True
    return out


# ------------------------------------------------------------------ the measurement

def measure_level(name, path, index, samples, rng, area_tol, raw_full_max):
    from uedcli import actorgraph
    from uedcli import preview_native as pn

    t = time.time(); level = corpus.load_level(path); load_s = time.time() - t

    world = [level.actors[n] for n in level.order]
    t = time.time(); full = pn.solve_world_surfaces(world, index); full_csg_s = time.time() - t

    # The WHOLE-LEVEL raw tier (`level graph`'s own computation), for levels small enough that
    # its O(brushes^2) SAT sweep finishes in reasonable time.
    n_brushes = sum(1 for n in level.order if level.actors[n].brush is not None)
    raw_full_s = None
    if n_brushes <= raw_full_max:
        t = time.time(); actorgraph.build_graph(level, index); raw_full_s = round(time.time() - t, 2)

    brush_names = [n for n in level.order if level.actors[n].brush is not None]
    picks = rng.sample(brush_names, min(samples, len(brush_names)))

    rows = []
    for pick in picks:
        actor = level.actors[pick]
        lo, hi = region_of(actor)
        t = time.time(); nbrs = neighborhood(level, index, lo, hi); select_s = time.time() - t
        t = time.time(); trunc = pn.solve_world_surfaces(nbrs, index); trunc_csg_s = time.time() - t
        flo = tuple(float(c) for c in lo)
        fhi = tuple(float(c) for c in hi)
        cmp = compare(face_signature(full.world_surfaces, flo, fhi),
                      face_signature(trunc.world_surfaces, flo, fhi), area_tol)

        # raw tier, scoped: decompose the surveyed brush + its neighbours and classify each pair.
        # A degenerate brush is SKIPPED per-brush, exactly as `build_graph._safe` does, so one bad
        # neighbour doesn't abort the measurement.
        from uedcli.writes import aabb_intersects
        near = [a for a in nbrs if aabb_intersects(region_of(a, 0.0), (lo, hi))]
        cache, order_index, raw_edges = {}, {n: i for i, n in enumerate(brush_names)}, 0
        t = time.time()
        try:
            actorgraph.decompose_convex(actor, cache=cache)
            for other in near:
                if other.name == pick:
                    continue
                try:
                    actorgraph.decompose_convex(other, cache=cache)
                except actorgraph.DegenerateBrushError:
                    continue
                raw_edges += len(actorgraph.classify_pair(
                    pick, actor, other.name, other,
                    order_index=order_index, class_index=index, cache=cache))
            raw_scoped_s = round(time.time() - t, 4)
        except actorgraph.DegenerateBrushError:
            raw_scoped_s = None                         # the SURVEYED brush itself is degenerate
        rows.append({"actor": pick, "neighbours": len(near), "csg_set": len(nbrs),
                     "brushes": len(brush_names),
                     "select_s": round(select_s, 4), "trunc_csg_s": round(trunc_csg_s, 4),
                     "raw_scoped_s": raw_scoped_s, "raw_edges": raw_edges, "compare": cmp})
    return {"level": name, "game": corpus.game_of(name), "actors": len(level.order),
            "brushes": len(brush_names), "load_s": round(load_s, 2),
            "full_csg_s": round(full_csg_s, 3), "raw_full_s": raw_full_s, "samples": rows}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--corpus", type=Path, default=corpus.DEFAULT_CORPUS)
    ap.add_argument("--levels", type=int, default=6)
    ap.add_argument("--smallest", action="store_true",
                    help="take the SMALLEST levels instead of the largest — the only way to reach "
                         "a level where the whole-level raw graph finishes")
    ap.add_argument("--samples", type=int, default=12, help="surveyed actors per level")
    ap.add_argument("--area-tol", type=float, default=1e-4)
    ap.add_argument("--seed", type=int, default=20260923)
    ap.add_argument("--raw-full-max", type=int, default=300,
                    help="also time the WHOLE-LEVEL raw graph on levels with at most this many "
                         "brushes (it is O(brushes^2) and unbounded above that)")
    ap.add_argument("--out", type=Path, default=Path(__file__).parent.parent / "bounded-cost.json")
    args = ap.parse_args()

    index = corpus.ued22_index()
    rng = random.Random(args.seed)
    out = []
    found = corpus.find_levels(args.corpus)
    for name, path in (found[::-1] if args.smallest else found)[: args.levels]:
        try:
            out.append(measure_level(name, path, index, args.samples, rng, args.area_tol,
                                     args.raw_full_max))
        except Exception as e:                                   # noqa: BLE001 — harness
            print(f"{name}: SKIPPED ({type(e).__name__}: {e})", file=sys.stderr, flush=True)
            continue
        print(f"{name}: {json.dumps({k: v for k, v in out[-1].items() if k != 'samples'})}",
              file=sys.stderr, flush=True)

    flat = [s for lv in out for s in lv["samples"]]
    bad = [s for s in flat if s["compare"]["missing_in_truncated"]
           or s["compare"]["extra_in_truncated"] or s["compare"]["area_mismatch"]]
    summary = {
        "levels": len(out),
        "surveys": len(flat),
        "surveys_with_any_divergence": len(bad),
        "neighbour_fraction_p50": round(statistics.median(
            [s["csg_set"] / s["brushes"] for s in flat]), 4) if flat else None,
        "neighbour_fraction_max": round(max(
            [s["csg_set"] / s["brushes"] for s in flat]), 4) if flat else None,
        "trunc_csg_s_p50": round(statistics.median([s["trunc_csg_s"] for s in flat]), 4) if flat else None,
        "trunc_csg_s_max": round(max([s["trunc_csg_s"] for s in flat]), 4) if flat else None,
        "raw_scoped_s_max": max([s["raw_scoped_s"] for s in flat if s["raw_scoped_s"] is not None],
                                default=None),
        "max_boundary_shift_uu_over_all_surveys": max(
            (s["compare"]["max_boundary_shift_uu"] for s in flat), default=None),
        "raw_scoped_s_p50": round(statistics.median(
            [s["raw_scoped_s"] for s in flat if s["raw_scoped_s"] is not None]), 4) if flat else None,
        "per_level": {lv["level"]: {"brushes": lv["brushes"], "load_s": lv["load_s"],
                                    "full_csg_s": lv["full_csg_s"], "raw_full_s": lv["raw_full_s"]}
                      for lv in out},
    }
    args.out.write_text(json.dumps({"summary": summary, "levels": out}, indent=1) + "\n")
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

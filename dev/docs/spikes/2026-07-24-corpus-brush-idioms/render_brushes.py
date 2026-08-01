#!/usr/bin/env python3
"""render_brushes.py — one wireframe per brush, focused, with LOCAL neighborhood as context.

The corpus brush-idiom study's render step. For each brush it renders a `--focus`'d quad (TOP/FRONT/
ISO/SIDE) with only the brush's *local neighborhood* as context — not the whole map. Whole-map context
is both illegible (a 1471-brush map is a tangle) and slow (~13 s/render); the neighborhood is a handful
of brushes → sub-second, and the focused brush reads clearly in its actual surroundings.

Neighborhood = every brush whose world AABB overlaps the focus brush's AABB expanded by `--margin` uu
(true intersection via `writes.actor_bounds`, so straddling walls/floors ARE included — unlike
`--within-bbox` containment). No poly-index labels (`--annotate none`), clean wireframes.

    render_brushes.py <level-dir> <out-dir> [--start N] [--count N] [--margin UU]
                      [--tightness F] [--size PX] [--sheet]

Loads the trunk ONCE and renders in-process via the real preview path (rendering.render_actors_to_out).
`--sheet` also writes contact sheets (≤12 per sheet) batching the chunk's images.
"""
from __future__ import annotations

import argparse
import glob
import os
import sys
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

_PKG_ROOT = Path(__file__).resolve().parents[4]
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

from uedcli import trunk, writes   # noqa: E402
from uedcli.cli import rendering


def _is_axis_aligned_box(actor, tol=1e-3):
    """True if the brush is a plain axis-aligned box: 6 faces, 8 unique local verts sitting exactly on
    the 2×2×2 corners of their own bbox. Filters the boring walls/floors/simple-room brushes so the
    render focuses on the non-trivial shapes (clipped / intersected / vertex-edited / angled). Works on
    LOCAL brush geometry (pre-actor-Rotation), so a rotated box still reads as a box. NOT classification
    — no params, no generator; just 'is this the trivial shape'."""
    b = actor.brush
    if b is None or len(b.polys) != 6:
        return False
    uniq = []
    for p in b.polys:
        for v in p.vertices:
            fv = tuple(float(c) for c in v)
            if not any(all(abs(fv[i] - u[i]) < tol for i in range(3)) for u in uniq):
                uniq.append(fv)
    if len(uniq) != 8:
        return False
    # Cluster each axis' coords with a tolerance (NOT round-to-decimals): real map boxes sit at
    # fractional coords with ~1e-4 float noise, which decimal rounding can split across a boundary
    # (a genuine box then reads as 3 distinct x-values and slips the filter). An axis-aligned box has
    # exactly 2 coord clusters per axis; with 8 unique verts that forces all 8 corners.
    def n_clusters(vals, tol=0.1):
        vals = sorted(vals)
        k = 1
        for a, b_ in zip(vals, vals[1:]):
            if b_ - a > tol:
                k += 1
        return k
    return all(n_clusters([v[ax] for v in uniq]) == 2 for ax in range(3))


def _is_flat_sheet(actor, tol=1.0):
    """True if the brush is a flat panel (a sheet): its local geometry has ~zero extent along some
    axis (min local-bbox dimension < `tol` uu). Catches single-quad sheets and thin flat panels —
    grates/glass/portals/decoration boards — which carry no construction-idiom value."""
    b = actor.brush
    if b is None:
        return False
    pts = [(float(x), float(y), float(z)) for p in b.polys for (x, y, z) in p.vertices]
    if not pts:
        return False
    ext = [max(p[i] for p in pts) - min(p[i] for p in pts) for i in range(3)]
    return min(ext) < tol


def _overlaps(a, b):
    (alo, ahi), (blo, bhi) = a, b
    return all(alo[i] <= bhi[i] and ahi[i] >= blo[i] for i in range(3))


def _expand(box, m):
    lo, hi = box
    return (tuple(lo[i] - m for i in range(3)), tuple(hi[i] + m for i in range(3)))


def _args_for(focus_name, out_path, tightness, size, layout="single"):
    return SimpleNamespace(
        size=size, view="iso", layout=layout, annotate="none", iso_angle=30.0,
        frame=focus_name, frame_tightness=tightness, focus=focus_name,
        highlight=[focus_name],                 # BOLD the focus brush (vivid+thick), not just un-dimmed
        brush_colors="csg", show="", png=True, out=out_path)


def _centroid(box):
    lo, hi = box
    return tuple((lo[i] + hi[i]) / 2 for i in range(3))


def _nearest(focus_box, cand_boxes, cap):
    """The `cap` brushes whose centroids are nearest the focus centroid (focus always included)."""
    fc = _centroid(focus_box)
    scored = sorted(cand_boxes, key=lambda nb: sum((_centroid(nb[1])[i] - fc[i]) ** 2 for i in range(3)))
    return [n for n, _b in scored[:cap]]


def _sheet(paths, out, cols=4, cell=360):
    from PIL import Image, ImageDraw
    n = len(paths)
    rows = (n + cols - 1) // cols
    pad, lab = 6, 16
    W = cols * (cell + pad) + pad
    H = rows * (cell + lab + pad) + pad
    img = Image.new("RGB", (W, H), (28, 28, 28))
    d = ImageDraw.Draw(img)
    for i, p in enumerate(paths):
        r, c = divmod(i, cols)
        x, y = pad + c * (cell + pad), pad + r * (cell + lab + pad)
        im = Image.open(p).convert("RGB").resize((cell, cell))
        img.paste(im, (x, y + lab))
        d.text((x + 2, y + 2), Path(p).stem, fill=(220, 220, 220))
    img.save(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("level_dir")
    ap.add_argument("out_dir")
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--count", type=int, default=24)
    ap.add_argument("--margin", type=float, default=64.0, help="neighborhood padding, uu (default 64)")
    ap.add_argument("--cap", type=int, default=10, help="max context brushes (nearest kept); focus always in")
    ap.add_argument("--tightness", type=float, default=0.7)
    ap.add_argument("--size", type=int, default=640)
    ap.add_argument("--sheet", action="store_true", help="also write contact sheets of the chunk")
    ap.add_argument("--per-sheet", type=int, default=6, help="images per contact sheet (default 6)")
    ap.add_argument("--quad", action="store_true", help="4-view quad instead of the default single ISO")
    ap.add_argument("--include-boxes", action="store_true",
                    help="also render plain axis-aligned box brushes (default: skip them as low-value)")
    ap.add_argument("--names-file", default=None,
                    help="render EXACTLY the brush names in this file (one per line), in file order — "
                         "bypasses the box/sheet filter and --start/--count (for a hand-picked set, "
                         "e.g. the top-complexity brushes)")
    args = ap.parse_args(argv)

    level, _ranks = trunk.read_level(Path(args.level_dir))
    order = level.order or list(level.actors)
    brush_names = [n for n in order if level.actors[n].brush is not None]
    bounds = {n: writes.actor_bounds(level.actors[n]) for n in brush_names}
    # The FOCUS set skips plain boxes (low idiom value); CONTEXT still includes them (they're context).
    from decimal import Decimal
    margin = Decimal(str(args.margin))          # bounds are Decimal (actor_bounds) — match them
    if args.names_file:
        wanted = [ln.strip() for ln in open(args.names_file) if ln.strip()]
        chunk = [n for n in wanted if n in bounds]          # keep file order, only real brushes
        print(f"[render] rendering {len(chunk)}/{len(wanted)} named brushes", file=sys.stderr)
    else:
        if args.include_boxes:
            focus_names = brush_names
        else:
            focus_names = [n for n in brush_names
                           if not _is_axis_aligned_box(level.actors[n])
                           and not _is_flat_sheet(level.actors[n])]
        n_cut = len(brush_names) - len(focus_names)
        print(f"[render] {len(brush_names)} brushes: {n_cut} plain boxes+sheets skipped, "
              f"{len(focus_names)} non-trivial to render", file=sys.stderr)
        chunk = focus_names[args.start:args.start + args.count]
    outdir = Path(args.out_dir)
    outdir.mkdir(parents=True, exist_ok=True)
    written = []
    for i, name in enumerate(chunk):
        box = _expand(bounds[name], margin)
        overlapping = [(n, bounds[n]) for n in brush_names if _overlaps(bounds[n], box)]
        if len(overlapping) > args.cap:                    # keep only the nearest `cap` (focus incl.)
            keep = set(_nearest(bounds[name], overlapping, args.cap)) | {name}
            neigh = [level.actors[n] for n, _b in overlapping if n in keep]
        else:
            neigh = [level.actors[n] for n, _b in overlapping]
        out_path = str(outdir / f"{args.start + i:04d}_{name}.png")
        a = _args_for(name, out_path, args.tightness, args.size, layout="quad" if args.quad else "single")
        with redirect_stdout(open(os.devnull, "w")):
            rendering.render_actors_to_out(neigh, a)
        written.append(out_path)
        print(f"[render] {args.start + i:04d} {name}  ({len(neigh)} in context)", file=sys.stderr)

    if args.sheet and written:
        cols = 2 if args.quad else 3
        for s in range(0, len(written), args.per_sheet):
            group = written[s:s + args.per_sheet]
            sh = str(outdir / f"sheet_{args.start + s:04d}.png")
            _sheet(group, sh, cols=cols)
            print(f"[sheet] {sh}  ({len(group)} brushes)")
    print(f"[render] wrote {len(written)} images -> {outdir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

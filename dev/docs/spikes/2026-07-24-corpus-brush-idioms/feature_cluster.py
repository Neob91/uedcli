#!/usr/bin/env python3
"""feature_cluster.py — group a level's brushes into spatially-connected "features".

⚠ NEGATIVE RESULT — do NOT use as-is. Two review gates found global AABB-overlap connected-components
unfit for real DX geometry (subtractive CSG → one blob at any --gap). See README.md "Status / result".
Retained as the record of what was tried; a redesign would be op-aware/seeded (see README).


Part of the corpus brush-idiom study (`specs/2026-07-24-corpus-brush-idioms.md`, option B for
per-feature selection). A real imported map has hundreds of opaquely-named brushes; the qualitative
(composition-grammar) pass needs to look at ONE feature (an arch, a stairwell, a room + its detail)
as a wireframe. This picks those brush *sets* for you so you can pipe them into `actor preview`:

    feature_cluster.py MAP.T3D --list                 # what features are there
    feature_cluster.py MAP.T3D --names 0 | actor preview -   # wireframe of the biggest one

**Method (deliberately simple, and a `find-spatial` prototype).** Each brush's axis-aligned world
bounds come from the SAME `writes.actor_bounds` the `actor bbox` verb uses (full transform honoured).
Two brushes are joined when their AABBs overlap after padding each by `--gap` uu; connected components
(union-find) over that relation are the features. This is exactly the `--overlapping` / `--within-bbox`
semantics of the parked `find-spatial` spec, so the harness doubles as a prototype for that verb.

**Known coarseness (honest):** AABB connectivity is a proxy for real geometric adjacency. A subtractive
room brush overlaps the additive detail inside it (good — room + contents cluster together), but a
door-shaped subtract that spans two rooms will MERGE them, and a large `--gap` over-merges a whole
connected interior into one blob. Tune `--gap` down (0, or the code allows negative to REQUIRE genuine
overlap) when features fuse; a future refinement would use actual poly overlap, not the AABB. For a
4-map pilot, "biggest connected sub-volume + drill down" is enough.

Run `--selftest` for a dependency-free check (no editor, no real map).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# The uedctl package lives at Tools/uedctl/ — five parents up from this spike file
# (…/uedctl/dev/docs/spikes/<slug>/feature_cluster.py).
_PKG_ROOT = Path(__file__).resolve().parents[4]
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

from uedctl.model import Actor, parse_t3d, parse_t3d_actors   # noqa: E402
from uedctl.writes import actor_bounds                        # noqa: E402


def _aabb_touch(a, b, gap):
    """True when AABBs `a`=(lo,hi) and `b`=(lo,hi) overlap after each is padded by `gap` on every
    side. `gap > 0` bridges near-but-not-touching brushes; `gap == 0` joins face-touching brushes;
    `gap < 0` REQUIRES genuine overlap of at least `-gap`."""
    (alo, ahi), (blo, bhi) = a, b
    for i in range(3):
        # padded intervals must intersect on every axis
        if ahi[i] + gap < blo[i] - gap or bhi[i] + gap < alo[i] - gap:
            return False
    return True


def cluster_features(actors: list[Actor], gap: float = 16.0) -> list[list[Actor]]:
    """Connected-components clustering of the BRUSH actors in `actors` by padded-AABB adjacency.
    Returns a list of clusters (each a list of the brush ACTOR objects), largest cluster first, ties
    broken by the earliest member's export order (stable). Returning the actors, not their names,
    keeps the result correct even when Names collide (a real MAP EXPORT has unique Names, but this
    stays robust regardless). Point actors (no brush) are ignored."""
    from decimal import Decimal
    gap = Decimal(str(gap))                          # bounds are Decimal (parse_t3d) — match them
    brushes = [a for a in actors if a.brush is not None]
    n = len(brushes)
    bounds = [actor_bounds(a) for a in brushes]

    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[max(rx, ry)] = min(rx, ry)

    # O(n^2) pairwise — fine for a per-map harness (a few thousand brushes at worst). A grid/interval
    # index would speed it up if ever needed.
    for i in range(n):
        for j in range(i + 1, n):
            if _aabb_touch(bounds[i], bounds[j], gap):
                union(i, j)

    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)

    clusters = [[brushes[i] for i in idxs] for idxs in groups.values()]
    # largest first; stable tiebreak on the cluster's earliest member export position (identity map,
    # not `.index()` — avoids dataclass-equality collisions and the O(n) scan)
    pos = {id(a): k for k, a in enumerate(brushes)}
    clusters.sort(key=lambda cl: (-len(cl), min(pos[id(a)] for a in cl)))
    return clusters


def _cluster_bbox(cluster: list[Actor]):
    from uedctl.writes import union_bounds
    lo, hi = union_bounds(cluster)
    return (tuple(str(v) for v in lo), tuple(str(v) for v in hi))


# --------------------------------------------------------------------------- CLI

def _load_actors(path: str) -> list[Actor]:
    text = sys.stdin.read() if path == "-" else Path(path).read_text()
    # parse_t3d_actors PRESERVES duplicate Names (parse_t3d would silently keep only the last of each
    # — see its docstring). A real MAP EXPORT has unique Names, but concatenated generator output does
    # not, and dropping brushes would corrupt every count. Warn if the input is that non-map kind.
    actors = parse_t3d_actors(text)
    names = [a.name for a in actors]
    dups = sorted({n for n in names if names.count(n) > 1})
    if dups:
        print(f"# warning: {len(dups)} duplicate actor name(s) (e.g. {dups[:3]}). A real MAP EXPORT has "
              f"unique Names; names are the handle fed to `actor preview`, so duplicates are ambiguous. "
              f"This input looks like concatenated generator output, not a level export.", file=sys.stderr)
    return actors


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Cluster a level's brushes into spatial features.")
    ap.add_argument("t3d", nargs="?", help="path to a level T3D (MAP EXPORT / batchexport output), or "
                                           "`-` for stdin. Omit only with --selftest.")
    ap.add_argument("--gap", type=float, default=16.0,
                    help="adjacency padding in uu (default 16 = the 1-ft grid). 0 = only face-touching "
                         "brushes join; negative = require genuine overlap. Lower it when features fuse.")
    ap.add_argument("--min-size", type=int, default=1,
                    help="drop clusters with fewer than this many brushes (default 1 = keep all).")
    ap.add_argument("--names", type=int, metavar="N",
                    help="print cluster N's brush names, one per line, to stdout (pipe to `actor preview -`).")
    ap.add_argument("--json", action="store_true", help="print all clusters as JSON to stdout.")
    ap.add_argument("--list", action="store_true",
                    help="print a human summary (id, brush count, bbox) — the default when no mode is given.")
    ap.add_argument("--selftest", action="store_true", help="run the built-in check and exit.")
    args = ap.parse_args(argv)

    if args.selftest:
        return _selftest()

    if not args.t3d:
        ap.error("a T3D path (or -) is required unless --selftest")

    actors = _load_actors(args.t3d)
    clusters = [c for c in cluster_features(actors, args.gap) if len(c) >= args.min_size]

    if args.names is not None:
        if not (0 <= args.names < len(clusters)):
            ap.error(f"cluster index {args.names} out of range (0..{len(clusters) - 1})")
        for a in clusters[args.names]:
            print(a.name)
        return 0

    if args.json:
        out = [{"id": i, "count": len(c), "bbox": _cluster_bbox(c), "names": [a.name for a in c]}
               for i, c in enumerate(clusters)]
        print(json.dumps(out, indent=2))
        return 0

    # default / --list
    brush_total = sum(1 for a in actors if a.brush is not None)
    print(f"# {len(clusters)} feature(s) from {brush_total} brushes (gap={args.gap}, "
          f"min-size={args.min_size})", file=sys.stderr)
    for i, c in enumerate(clusters):
        (lo, hi) = _cluster_bbox(c)
        print(f"cluster {i}\t{len(c)} brushes\tbbox=({','.join(lo)})..({','.join(hi)})")
    return 0


def _selftest() -> int:
    """Two separated groups of face-touching cubes + one lone far cube → expect 3 clusters
    (sizes 3, 2, 1). Dependency-free (no editor/CLI/real map) but FAITHFUL: the synthetic actors are
    emitted to T3D and re-parsed through `parse_t3d`, exactly the path a real MAP EXPORT takes — so the
    numeric types (Decimal location AND Decimal vertices) match production, not a hand-built shortcut."""
    from decimal import Decimal
    from uedctl.builders import cube
    from uedctl.emit import emit_actor

    def brush_actor(name, x, y, z):
        return Actor(name=name, cls="Brush", brush=cube(64, 64, 64),
                     location=(Decimal(x), Decimal(y), Decimal(z)))

    def parsed(actors):
        text = "\n".join(emit_actor(a) for a in actors)
        return list(parse_t3d(text).actors.values())

    # group A: three cubes in a touching row near the origin (64 apart = face-to-face)
    a = [brush_actor("A0", 0, 0, 0), brush_actor("A1", 64, 0, 0), brush_actor("A2", 128, 0, 0)]
    # group B: two touching cubes far away on +Y
    b = [brush_actor("B0", 0, 4096, 0), brush_actor("B1", 64, 4096, 0)]
    # a lone cube nowhere near either
    c = [brush_actor("C0", 8192, 8192, 8192)]
    # a point actor (no brush) that must be ignored
    p = [Actor(name="Light0", cls="Engine.Light", location=(Decimal(0), Decimal(0), Decimal(0)))]

    clusters = cluster_features(parsed(a + b + c + p), gap=0.0)
    names = [sorted(x.name for x in cl) for cl in clusters]
    sizes = [len(x) for x in clusters]
    ok = True

    def check(cond, msg):
        nonlocal ok
        print(("PASS" if cond else "FAIL") + f": {msg}")
        ok = ok and cond

    check(sizes == [3, 2, 1], f"cluster sizes {sizes} == [3, 2, 1] (largest first)")
    check(names[0] == ["A0", "A1", "A2"], f"biggest cluster is group A ({names[0]})")
    check(names[1] == ["B0", "B1"], f"second cluster is group B ({names[1]})")
    check(names[2] == ["C0"], f"third cluster is the lone cube ({names[2]})")
    check(all("Light0" not in nm for nm in names), "the point actor (Light0) is ignored")

    # widen the gap enough to bridge A and B (they are 4096-64=... apart on Y) → they should fuse
    fused = cluster_features(parsed(a + b + c), gap=2100.0)
    check(len(fused) == 2 and len(fused[0]) == 5,
          f"a large gap fuses A+B into one 5-brush cluster (got sizes {[len(x) for x in fused]})")

    print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

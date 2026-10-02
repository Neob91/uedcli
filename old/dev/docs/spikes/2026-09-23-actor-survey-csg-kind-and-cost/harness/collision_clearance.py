"""Measure, on real shipped Deus Ex content, how much a correctly-placed actor's collision extent
overlaps RESOLVED SOLID matter — the number `actor survey`'s `crosses` needs as a tolerance.

Method (every step is the engine's own, not an approximation invented here):

* The world is resolved with the faithful native CSG core (`build_geometry_bspcsg`, the same one
  `level materialize --native` uses), then parsed back to a Python `umodel.Model`.
* Solid/void at a point is `solidity.point_is_solid`, the port of the engine's own collision walk
  (`FBspNode::IsCsg` + the walker's running outside state). NOT `UModel::PointRegion`, which reports
  a semisolid's interior as void — see `solidity.py`'s docstring for the measurement behind that.
* An actor's collision volume is the engine's own AABB, half-extents
  `(CollisionRadius, CollisionRadius, CollisionHeight)` (`uedcli-native/src/collision.rs`
  `Scout::extent`), NOT a cylinder.
* Per actor we report the signed uniform clearance `delta`: the largest amount the box can be
  inflated (delta > 0) — or must be shrunk (delta < 0) — for it to be entirely in void. Found by
  bisection over a 27-point sample of the box (8 corners, 12 edge midpoints, 6 face centres,
  centre). `delta < 0` is by-design penetration into solid; its distribution is the answer.

Known limits, stated rather than smoothed over:
  - 27-point sampling can miss a solid slab thinner than the sample spacing. It cannot miss the
    resting/flush-mounted case this measures, which always puts a whole box FACE behind the plane.
  - An actor buried entirely inside solid reports `delta = -(the full half-extent)`, i.e. it
    saturates at the shrink floor; those are reported separately as `buried`.

Usage:  .venv/bin/python dev/docs/spikes/<slug>/harness/collision_clearance.py [--levels N] [--out F]
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
from pathlib import Path

import corpus


def _sample_points(loc, ext):
    """27 sample points of the AABB `loc ± ext`: corners, edge midpoints, face centres, centre."""
    out = []
    for ix in (-1, 0, 1):
        for iy in (-1, 0, 1):
            for iz in (-1, 0, 1):
                out.append((loc[0] + ix * ext[0], loc[1] + iy * ext[1], loc[2] + iz * ext[2]))
    return out


def _box_free(model, is_solid, loc, ext) -> bool:
    return not any(is_solid(model, p) for p in _sample_points(loc, ext))


def signed_clearance(model, is_solid, loc, ext, *, hi=64.0, iters=18) -> float:
    """Largest `delta` with `box(loc, ext + delta)` entirely in void. Negative = penetration."""
    lo = -max(ext)                                # shrink floor: every axis collapses to the centre
    if _box_free(model, is_solid, loc, tuple(e + hi for e in ext)):
        return hi
    if not _box_free(model, is_solid, loc, tuple(max(0.0, e + lo) for e in ext)):
        return lo                                 # even the collapsed box is in solid: buried
    a, b = lo, hi
    for _ in range(iters):
        mid = (a + b) / 2.0
        if _box_free(model, is_solid, loc, tuple(max(0.0, e + mid) for e in ext)):
            a = mid
        else:
            b = mid
    return a


def _to_float(text, default=0.0) -> float:
    try:
        return float(str(text).strip())
    except (TypeError, ValueError):
        return default


_COLLISION_BOOLS = ("bCollideActors", "bCollideWorld", "bBlockActors", "bBlockPlayers")


def collidable_actors(level, defaults) -> tuple[list, int]:
    """Every non-brush actor with a real collision box, resolved instance-else-class-default exactly
    the way `serve/scene.py::_actor_radii` does — plus the engine's other collision booleans, so the
    result can be sliced by them afterwards rather than committing to one gate here.

    Returns `(rows, unresolved)`; `unresolved` counts actors whose class schema would not resolve."""
    from uedcli import uprops
    rows, unresolved = [], 0
    for name in level.order:
        actor = level.actors[name]
        if actor.brush is not None or actor.location is None:
            continue
        instance = {k.casefold(): v for k, v in actor.props}
        try:
            class_defaults = defaults.for_class(actor.cls).defaults
        except uprops.SchemaError:
            unresolved += 1
            continue

        def field(key, _i=instance, _d=class_defaults):
            low = key.casefold()
            return _i[low] if low in _i else _d.get((low, 0))

        flags = {b: str(field(b) if field(b) is not None else "False").strip() == "True"
                 for b in _COLLISION_BOOLS}
        if not flags["bCollideActors"]:
            continue
        r = _to_float(field("CollisionRadius"))
        h = _to_float(field("CollisionHeight"))
        if r <= 0.0 or h <= 0.0:
            continue
        loc = (float(actor.location[0]), float(actor.location[1]), float(actor.location[2]))
        rows.append((name, actor.cls, loc, (r, r, h), flags))
    return rows, unresolved


def build_model(level, index):
    """The resolved world as a parsed `umodel.Model` (nodes + leaves + zones)."""
    from uedcli import movers, preview_native as pn
    from uedcli.native.umodel import parse_model_body
    from uedcli.native_ext import import_native
    from uedcli.normalize import is_builder_brush
    native = import_native()
    brushes = []
    for name in level.order:
        actor = level.actors.get(name)
        if actor is None or actor.brush is None:
            continue
        if movers.is_mover(actor, index) or is_builder_brush(actor):
            continue
        if pn._csg_oper_or_skip(name, dict(actor.props)) is None:
            continue
        brushes.append(pn._marshal_brush(actor))
    built = native.build_geometry_bspcsg(brushes)
    body = native.serialize_model(built)
    return parse_model_body(body, 0, len(body)), len(brushes)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--corpus", type=Path, default=corpus.DEFAULT_CORPUS)
    ap.add_argument("--levels", type=int, default=8, help="how many levels to measure")
    ap.add_argument("--out", type=Path, default=Path(__file__).parent.parent / "collision-clearance.json")
    args = ap.parse_args()

    from solidity import point_is_solid

    index = corpus.ued22_index()
    defaults = corpus.ued22_defaults()
    levels = corpus.find_levels(args.corpus)[: args.levels]

    per_level, all_rows = [], []
    for name, path in levels:
        t0 = time.time()
        try:
            level = corpus.load_level(path)
            model, n_brushes = build_model(level, index)
        except Exception as e:                                  # noqa: BLE001 — harness
            print(f"{name}: SKIPPED ({type(e).__name__}: {e})", file=sys.stderr, flush=True)
            continue
        candidates, unresolved = collidable_actors(level, defaults)
        rows = []
        for aname, cls, loc, ext, flags in candidates:
            d = signed_clearance(model, point_is_solid, loc, ext)
            rows.append({"level": name, "game": corpus.game_of(name), "actor": aname, "cls": cls,
                         "radius": ext[0], "height": ext[2], "delta": round(d, 4),
                         "buried": d <= -max(ext) + 1e-6, **flags})
        all_rows += rows
        per_level.append({"level": name, "game": corpus.game_of(name), "actors": len(level.order),
                          "csg_brushes": n_brushes, "collidable": len(rows),
                          "class_unresolved": unresolved,
                          "penetrating": sum(1 for r in rows if r["delta"] < 0),
                          "buried": sum(1 for r in rows if r["buried"]),
                          "seconds": round(time.time() - t0, 1)})
        print(f"{name}: {per_level[-1]}", file=sys.stderr, flush=True)

    dx = [r for r in all_rows if r["game"] == "deusex"]
    summary = {"levels": per_level,
               "all": _stats(all_rows),
               "deusex": _stats(dx),
               "unreal": _stats([r for r in all_rows if r["game"] == "unreal"]),
               # The gate that actually separates physical matter from a trigger volume: an actor
               # that BLOCKS is one whose extent is meant to be solid-ish; a Trigger/Teleporter
               # sets bCollideActors (so it can be touched) but blocks nothing and is routinely
               # sized to span a room, walls included.
               "deusex_blocking": _stats([r for r in dx if r["bBlockActors"]]),
               "deusex_collide_world": _stats([r for r in dx if r["bCollideWorld"]]),
               "deusex_nonblocking": _stats([r for r in dx if not r["bBlockActors"]])}
    args.out.write_text(json.dumps({"summary": summary, "rows": all_rows}, indent=1) + "\n")
    print(json.dumps(summary, indent=1))
    return 0


def _stats(rows) -> dict:
    """Penetration statistics over `rows`, EXCLUDING buried actors (whose depth saturates at the
    shrink floor and would skew every percentile)."""
    pens = sorted(-r["delta"] for r in rows if r["delta"] < 0 and not r["buried"])
    return {
        "collidable": len(rows),
        "clear": sum(1 for r in rows if r["delta"] >= 0),
        "penetrating": len(pens),
        "buried": sum(1 for r in rows if r["buried"]),
        "depth_uu": {
            "min": pens[0] if pens else None,
            "p50": round(statistics.median(pens), 4) if pens else None,
            "p75": pens[int(0.75 * (len(pens) - 1))] if pens else None,
            "p90": pens[int(0.90 * (len(pens) - 1))] if pens else None,
            "p99": pens[int(0.99 * (len(pens) - 1))] if pens else None,
            "max": pens[-1] if pens else None,
        },
        "histogram_uu": _histogram(pens),
    }


def _histogram(values) -> dict:
    edges = [0.0, 0.001, 0.01, 0.1, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0, math.inf]
    out = {}
    for lo, hi in zip(edges, edges[1:]):
        out[f"{lo}-{hi}"] = sum(1 for v in values if lo <= v < hi)
    return out


if __name__ == "__main__":
    raise SystemExit(main())

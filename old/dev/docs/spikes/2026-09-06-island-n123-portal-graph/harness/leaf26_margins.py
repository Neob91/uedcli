#!/usr/bin/env python3
"""Island N=123: why native's permeating-light flood reaches world leaf 26 and UED22's does not.

Three offline checks against the REFERENCE package (`ref_N123.dx`), whose `points`/`nodes` are
byte-identical to native's — so anything measured here is shared by both builds:

1. `seed`    — replay `ActorVisibility`'s BSP descent for `Light124` and show no `PlaneDot` on the
               path is near zero, i.e. the seed leaf (85) is not a near-tie.
2. `beam`    — replay the beam clip of the 27->26 portal quad by the beam that entered leaf 27, and
               print each clip plane's margin. The tightest is +1.795, 7x `SplitWithPlaneFast`'s
               0.25 epsilon, and it barely moves when the light moves: the constraint really is
               "is the 27->26 quad on leaf 27's side of node 344's plane".
3. `points`  — show all four vertices of the 27->26 portal quad are real `Model.Points` entries
               (within 3e-5) and measure their signed distance to node 344's plane (min 1.90).

The two polygons are the ones native's flood used, captured from a temporary `UEDCLI_PERM_TRACE`
dump of `permeating_lights::actor_visibility`; they are reproduced here as literals so the checks
run with no editor and no native build.

Usage:  leaf26_margins.py [seed|beam|points|all] [--ref <ref_N123.dx>]
"""
from __future__ import annotations

import argparse
import math
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
LADDER = ROOT / "dev/docs/spikes/2026-09-03-incremental-actor-parity/harness"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(LADDER))

import model_dump as md      # noqa: E402
import parity_gate as pg     # noqa: E402

DEFAULT_REF = ROOT / "_scratch/actor-parity/01_nyc_unatcoisland/ref_N123.dx"

# `Light124`, the only light native gives leaf 26 (trunk actor Location; WorldLightRadius 1675).
LIGHT = (-4528.35, 4385.68, 64.37)
# The beam that entered leaf 27 (the node-344 32<->27 portal, clipped by the node-193 window).
BEAM = [(-4400.0, 5108.0, 128.0), (-4400.0, 5108.0, 128.0), (-3696.0, 5108.0, 128.0),
        (-3436.0, 5068.248, 147.87589), (-3436.0, 4617.3335, 373.33316),
        (-3905.1384, 4617.3335, 373.3332)]
# The node-351 27<->26 portal quad the beam is asked to clip.
TARGET = [(-3436.0, 4652.0, 358.12503), (-3436.0, 4652.0, 363.12503),
          (-3436.0, 4720.0, 350.0), (-3436.0, 4720.0, 329.99997)]
NODE_344 = 344


def sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def load(ref: Path) -> dict:
    p = pg.load_package(str(ref))
    return md.decode(p, md.find(p, "Model2"))


def seed(m: dict) -> None:
    """`ActorVisibility`'s seed descent (`Editor.dll 0x100a6d70`): follow `iChild[PlaneDot > 0]`.

    Node on-disk order is `iVertPool, iSurf, iChild[0], iChild[1], iPlane, ...` with `iLeaf[0..1]`
    in the 8-byte tail, so `ci[2]` is the BACK child and `ci[3]` the FRONT one.
    """
    ni = 0
    for step in range(4096):
        plane, _zm, _nf, ci, tail = m["nodes"][ni]
        d = plane[0] * LIGHT[0] + plane[1] * LIGHT[1] + plane[2] * LIGHT[2] - plane[3]
        print(f"  node {ni:4d}  PlaneDot {d:+12.4f}")
        side = 1 if d > 0 else 0
        child = ci[3] if side else ci[2]
        if child < 0:
            print(f"  -> seed leaf {struct.unpack('<2i', tail)[side]}")
            return
        ni = child
    raise SystemExit("descent did not terminate")


def _clip_margins(light, clip, target):
    """Per beam edge, the editor's `FPlane(Light, clip[j], clip[jPrev])` and the target's margins."""
    out = []
    n = len(clip)
    for j in range(n):
        a, b = clip[(j + n - 1) % n], clip[j]
        cr = cross(sub(b, light), sub(a, light))
        sq = dot(cr, cr)
        if sq < 1e-8:
            out.append((j, None, None, None))   # degenerate edge: SafeNormal -> zero -> no constraint
            continue
        ln = math.sqrt(sq)
        nrm = (cr[0] / ln, cr[1] / ln, cr[2] / ln)
        flipped = sum(dot(nrm, sub(v, light)) for v in clip) < 0
        if flipped:
            nrm = (-nrm[0], -nrm[1], -nrm[2])
        ds = [dot(nrm, sub(v, light)) for v in target]
        out.append((j, min(ds), max(ds), flipped))
    return out


def beam(_m: dict) -> None:
    for j, lo, hi, flipped in _clip_margins(LIGHT, BEAM, TARGET):
        if lo is None:
            print(f"  edge {j}: degenerate (duplicate vertex) -> SP_Coplanar, no constraint")
        else:
            print(f"  edge {j}: target margin [{lo:+9.4f}, {hi:+9.4f}]  winding-flip={flipped}")
    print("  (+0.25 is the SplitWithPlaneFast epsilon; the whole quad survives as SP_Front)")
    worst = min(lo for _j, lo, _hi, _f in _clip_margins(LIGHT, BEAM, TARGET) if lo is not None)
    print(f"  tightest with the light where it is: {worst:+.4f}")
    for label, moved in (("dz-64", (0, 0, -64)), ("dz+64", (0, 0, 64)),
                         ("dy-64", (0, -64, 0)), ("dy+64", (0, 64, 0))):
        loc = (LIGHT[0] + moved[0], LIGHT[1] + moved[1], LIGHT[2] + moved[2])
        w = min(lo for _j, lo, _hi, _f in _clip_margins(loc, BEAM, TARGET) if lo is not None)
        print(f"  tightest with the light moved {label}: {w:+.4f}")


def points(m: dict) -> None:
    plane = m["nodes"][NODE_344][0]
    print(f"  node {NODE_344} plane {plane}")
    for q in TARGET:
        best = min(m["points"], key=lambda v: dot(sub(v, q), sub(v, q)))
        d = math.sqrt(dot(sub(best, q), sub(best, q)))
        pd = q[0] * plane[0] + q[1] * plane[1] + q[2] * plane[2] - plane[3]
        print(f"  {q} -> nearest Model.Point {best} ({d:.6f} away), node-344 PlaneDot {pd:+.4f}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("check", nargs="?", default="all", choices=["seed", "beam", "points", "all"])
    ap.add_argument("--ref", default=str(DEFAULT_REF))
    args = ap.parse_args()
    m = load(Path(args.ref))
    for name, fn in (("seed", seed), ("beam", beam), ("points", points)):
        if args.check in (name, "all"):
            print(f"[{name}]")
            fn(m)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

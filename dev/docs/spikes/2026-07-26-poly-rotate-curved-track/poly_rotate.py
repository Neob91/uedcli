#!/usr/bin/env python3
"""SPIKE PROTOTYPE — rotate a set of polys' texture frames in the face plane.

This is throwaway harness for the 2026-07-26 curved-track spike, NOT shipped code. It exists to
answer one question empirically: given a per-face texture ROTATE operation, can an agent align a
repeating track texture around a revolved (curved) brush?

It deliberately mirrors the interface the real `brush poly rotate` verb is expected to take, so the
spike measures the real ergonomics and not the harness's:

    poly_rotate.py --trunk <maps/<level>> (BRUSH:SELECTOR… | -) --by DEG [--about centroid|origin]

`-` reads the targets from stdin (the `BRUSH:idx` lines `brush poly find` prints), exactly like
`brush poly set -`. Empty stdin is a clean no-op (exit 0).

WHAT IT DOES TO THE SURFACE
---------------------------
The T3D UV convention (dev/docs/unrealed/t3d.md "The UV convention") is

    U = (Vertex − Origin) · TextureU + PanU          (V analogously)

with the texel scale carried in |TextureU|. Rotating the texture therefore means rotating the
TextureU/TextureV axes within the face plane (about the face's unit normal), and then re-anchoring
`Origin` so that a chosen PIVOT point keeps the (U,V) it had before — otherwise the texture both
rotates and slides, which is not what "rotate" means to an author.

  --about centroid  (default)  the face's world centroid keeps its (U,V) — the texture spins in
                               place on the face
  --about origin               no re-anchor; the stored Origin keeps its (U,V), so the texture
                               rotates about that point (usually off-face, so it also slides)

SIGN: `--by` is in DEGREES and rotates the texture IMAGE counter-clockwise when the face is viewed
from OUTSIDE (looking along −normal). The axes are therefore rotated by −θ. (Degrees, not unreal
rotation units, is a deliberate spike choice to be evaluated — `--rotate` on the builders takes UU.)

ASSUMPTION: the re-anchor solves for the pivot in the {TextureU, TextureV} basis assuming those two
are ORTHOGONAL. That holds for every frame uedcli's builders emit and for everything `poly align`
writes. A sheared hand-authored frame would re-anchor approximately; the spike does not exercise one.
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_REPO))

from uedcli import polyalign                                    # noqa: E402
from uedcli.dispatch import TrunkLevelSource                    # noqa: E402
from uedcli.polyalign import (_centroid, _dot, _scale, _sub, _world_normal,  # noqa: E402
                              _world_verts, _write_world_frame)
from uedcli.preview_native import _world_uv_frame               # noqa: E402


def _rodrigues(v, n, theta):
    """Rotate `v` about the unit axis `n` by `theta` radians (right-handed)."""
    c, s = math.cos(theta), math.sin(theta)
    cross = (n[1] * v[2] - n[2] * v[1], n[2] * v[0] - n[0] * v[2], n[0] * v[1] - n[1] * v[0])
    d = _dot(n, v)
    return tuple(v[i] * c + cross[i] * s + n[i] * d * (1.0 - c) for i in range(3))


def rotate_face(actor, poly, ref: str, degrees: float, about: str) -> None:
    """Rotate one face's texture frame in place by `degrees` about its normal, re-anchoring so the
    pivot named by `about` keeps its (U,V)."""
    base_w, tu_w, tv_w, pan = _world_uv_frame(actor, poly)
    n = _world_normal(actor, poly, ref)

    pivot = _centroid(_world_verts(actor, poly)) if about == "centroid" else base_w
    u0, v0 = polyalign.face_uv(actor, poly, pivot)               # BEFORE the rotation

    # Rotate the IMAGE by +theta ⇒ rotate the AXES by −theta.
    theta = -math.radians(degrees)
    tu2 = _rodrigues(tu_w, n, theta)
    tv2 = _rodrigues(tv_w, n, theta)

    # Re-anchor: choose base' so that `pivot` still maps to (u0, v0).
    #   (pivot − base')·tu2 = u0 − PanU ,  (pivot − base')·tv2 = v0 − PanV
    # With tu2 ⊥ tv2 (both lie in the face plane), the in-plane displacement is separable.
    a, b = u0 - pan[0], v0 - pan[1]
    d = tuple(a * tu2[i] / _dot(tu2, tu2) + b * tv2[i] / _dot(tv2, tv2) for i in range(3))
    base2 = _sub(pivot, d)

    _write_world_frame(actor, poly, base2, tu2, tv2, pan)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="SPIKE: rotate the texture frame of a set of faces, in the face plane.")
    ap.add_argument("--trunk", required=True,
                    help="the level's trunk dir (e.g. <project>/maps/<level>)")
    ap.add_argument("targets", nargs="+", metavar="BRUSH:SELECTOR",
                    help="BRUSH:SELECTOR tokens (SELECTOR = 'all' or comma indices), a bare brush "
                         "Name (= all its polys), or the single token - to read them from stdin")
    ap.add_argument("--by", type=float, required=True, metavar="DEG",
                    help="rotation in DEGREES, counter-clockwise viewed from outside the face")
    ap.add_argument("--about", choices=["centroid", "origin"], default="centroid",
                    help="pivot that keeps its (U,V): the face's world centroid (default), or the "
                         "surface's stored Origin")
    args = ap.parse_args(argv)

    tokens = args.targets
    if tokens == ["-"]:
        tokens = [ln.strip() for ln in sys.stdin.read().splitlines() if ln.strip()]
        if not tokens:
            return 0                                             # empty stdin: clean no-op
    elif "-" in tokens:
        print("poly_rotate: `-` is the sole targets source — not mixable with named targets",
              file=sys.stderr)
        return 2

    src = TrunkLevelSource(Path(args.trunk))
    level = src.load()
    try:
        targets = polyalign.resolve_align_targets(level, tokens)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    if not targets:
        return 0

    for brush_name, idx in targets:
        actor = level.actors[brush_name]
        rotate_face(actor, actor.brush.polys[idx], f"{brush_name}:{idx}", args.by, args.about)

    touched = sorted({bn for bn, _ in targets})
    src.save(verb="poly-rotate", args={"by": args.by}, level=level, touched=touched)
    # PRODUCER: echo the per-face selectors we acted on, so a second per-face verb can consume them
    # (`… | poly_rotate.py - --by 45 | poly_rotate.py - --by 5`). This is the BRUSH:idx echo the
    # 2026-07-26 design decision adopts for the per-face mutators.
    for brush_name, idx in targets:
        print(f"{brush_name}:{idx}")
    print(f"rotated {len(targets)} face(s) by {args.by}°", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

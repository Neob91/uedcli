"""Controlled verification that the native materialize rotation transform matches the
editor-verified reference (`rotation.world_vertices`).

Context: `materialize._build_brush_input` used to REJECT any non-identity brush `Rotation`
(the transport port passed identity + refused rotated brushes).  2026-07-17 it was enabled:
it builds the rotation matrix `R` from the URU Pitch/Yaw/Roll via `rotation.actor_matrix`
(→ `euler_to_matrix_uu`, GMath sine table) and the Rust `FPoly::transform` applies
`world = Location + R·(v − PrePivot)`.  This is the UE1 FRotator convention pinned in
`spikes/2026-06-19-frotator-convention.md` (yaw = textbook Rz; pitch/roll sin-flipped;
compose Rz·Ry·Rx; unit 65536).

This harness builds a single Add box under several rotations through BOTH the Rust CSG
(`build_geometry`) and the editor-verified Python reference (`rotation.world_vertices`),
and asserts every world vertex the native build emits is explained by the reference — a
differential check against the convention proven live against the editor.

Run:  cd Tools/uedcli && .venv/bin/python dev/docs/spikes/2026-07-15-native-materialize/harness/verify_rotated_brush.py
"""
import sys
from pathlib import Path
from decimal import Decimal as D

ROOT = Path(__file__).resolve().parents[5]      # Tools/uedcli
sys.path.insert(0, str(ROOT))

from uedcli import rotation as ROT
from uedcli.model import Actor, Brush, Polygon
from uedcli.native import materialize as MAT
from uedcli.native import umodel as UM
import uedcli_native


def make_box(loc, rot_str=None, hx=256, hy=64, hz=64):
    pts = [(-hx, -hy, -hz), (hx, -hy, -hz), (hx, hy, -hz), (-hx, hy, -hz),
           (-hx, -hy, hz), (hx, -hy, hz), (hx, hy, hz), (-hx, hy, hz)]
    faces = [[0, 1, 2, 3], [7, 6, 5, 4], [0, 3, 7, 4], [2, 1, 5, 6], [1, 0, 4, 5], [3, 2, 6, 7]]
    a = Actor(name="Box0", cls="Engine.Brush", brush=Brush(model_name="Box0",
        polys=[Polygon(vertices=[tuple(D(c) for c in pts[i]) for i in f]) for f in faces]))
    a.location = tuple(D(c) for c in loc)
    a.props = [("CsgOper", "CSG_Add")]
    if rot_str:
        a.props.append(("Rotation", rot_str))
    return a


def native_world_points(actor):
    bt = MAT._build_brush_input(actor.name, actor)
    body = uedcli_native.serialize_model(uedcli_native.build_geometry([bt]))
    m = UM.parse_model_body(body, 0, len(body))
    return {tuple(round(c, 3) for c in p) for p in m.points}


def main():
    cases = [
        ("identity", None),
        ("Yaw=-16384 (-90deg)", "(Yaw=-16384)"),
        ("Yaw=16384 (+90deg)", "(Yaw=16384)"),
        ("Roll=32768 (180deg)", "(Roll=32768)"),
        ("Pitch=32768", "(Pitch=32768)"),
        ("Yaw=49152,Roll=32768", "(Yaw=49152,Roll=32768)"),
        ("Yaw=8688 (arbitrary)", "(Yaw=8688)"),
    ]
    # geometric anchor: -90deg yaw sends +X to -Y and +Y to +X
    R = ROT.euler_to_matrix_uu(0, (-16384) % 65536, 0)
    mv = lambda M, v: tuple(sum(M[i][k] * v[k] for k in range(3)) for i in range(3))
    print("Yaw=-90 * +X(256,0,0) ->", tuple(round(x, 2) for x in mv(R, (256., 0., 0.))),
          "(expect (0,-256,0))")

    ok = True
    for label, rot in cases:
        a = make_box((500, 0, 300), rot)
        ref = {tuple(round(c, 3) for c in w) for w in ROT.world_vertices(a)}
        nat = native_world_points(a)
        missing = [p for p in nat if not any(all(abs(p[i] - r[i]) < 0.05 for i in range(3))
                                             for r in ref)]
        status = "OK" if not missing else f"BAD {missing[:3]}"
        print(f"  {label:26s} native={len(nat):2d} ref_corners={len(ref):2d} unexplained={len(missing)} {status}")
        ok &= not missing
    print("ALL PASS" if ok else "FAILURES")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

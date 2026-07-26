#!/usr/bin/env python3
"""Build the TEXALIGN probe level as a plain T3D file.

Geometry is chosen so that every hypothesis about `POLY TEXALIGN` is separable:

  Room     subtractive 2048(X) x 1024(Y) x 512(Z) box centred at the origin -> six INWARD-facing
           faces (+Z floor, -Z ceiling, +X/-X/+Y/-Y walls) of three different aspect ratios.
  CubeA    additive 128^3 cube at (-640, 0, 0)          - all six faces square, equal size
  BoxB     additive 256 x 64 x 32 at (0, 0, 0)          - every face a different aspect ratio
  CubeC    additive 128^3 cube at (512, 96, 48)         - same shape as CubeA, moved OFF-grid-centre
                                                          so an anchor at the face min-corner is
                                                          distinguishable from one at the world origin
  SlantXZ  additive wedge with a face normal (0.7071, 0, 0.7071)      - a 45 deg ramp
  SlantYZ  additive wedge with a face normal (0, 0.6, 0.8)            - a non-45 deg slope
  SlantXYZ additive wedge with a face normal (0.577, 0.577, 0.577)    - fully diagonal
  WallYaw  additive prism whose two big faces are VERTICAL but yawed: normals (0.6, 0.8, 0) and
           (-0.6, -0.8, 0) - a wall that is neither an X wall nor a Y wall, which is the
           discriminator between WALLDIR / WALLX / WALLY.

Textures: three different sizes so a fit-to-face rule that depends on the texture's pixel
dimensions is visible - 256x256, 256x64, 128x256.

Usage:  fixture.py <out.t3d>
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_REPO))

from uedcli import builders          # noqa: E402
from uedcli.emit import emit_map     # noqa: E402
from uedcli.model import Brush       # noqa: E402

# name -> (USize, VSize); the analysis needs the pixel dims, so keep them here.
TEXTURES = {
    "GameMisc.ex_Bricks": (256, 256),
    "GameMisc.AirCount_A00": (256, 64),
    "GameMisc.Calendar_2": (128, 256),
}
TEX_PACKAGES = {"GameMisc": "GameMisc.utx"}

SQUARE = "GameMisc.ex_Bricks"
WIDE = "GameMisc.AirCount_A00"
TALL = "GameMisc.Calendar_2"


def _prism(profile, depth, tex):
    """A prism: `profile` is a list of (x, z) points wound CCW in the XZ plane, extruded +/- depth/2
    along Y. Faces get `tex`."""
    hy = depth / 2.0
    front = [(x, -hy, z) for x, z in profile]        # -Y cap
    back = [(x, hy, z) for x, z in profile]          # +Y cap
    faces = [(front, (0, -1, 0)), (list(reversed(back)), (0, 1, 0))]
    n = len(profile)
    for i in range(n):
        x0, z0 = profile[i]
        x1, z1 = profile[(i + 1) % n]
        ring = [(x0, -hy, z0), (x1, -hy, z1), (x1, hy, z1), (x0, hy, z0)]
        # outward = the in-plane normal of the (x0,z0)->(x1,z1) edge, for a CCW profile in XZ
        # viewed from +Y ... sign fixed by _face's winding check anyway; give the right direction.
        ex, ez = x1 - x0, z1 - z0
        outward = (ez, 0.0, -ex)
        faces.append((ring, outward))
    return Brush(model_name="Model",
                 polys=[builders._face(r, o, tex, 0, item="OUTSIDE") for r, o in faces])


def build_actors():
    actors = []

    room = builders.cube(2048, 1024, 512, texture=SQUARE)
    actors.append(builders.make_brush_actor("Room", room, (0, 0, 0), csg="subtract"))

    cube_a = builders.cube(128, 128, 128, texture=SQUARE)
    actors.append(builders.make_brush_actor("CubeA", cube_a, (-640, 0, 0), csg="add"))

    box_b = builders.cube(256, 64, 32, texture=WIDE)
    actors.append(builders.make_brush_actor("BoxB", box_b, (0, 0, 0), csg="add"))

    cube_c = builders.cube(128, 128, 128, texture=TALL)
    actors.append(builders.make_brush_actor("CubeC", cube_c, (512, 96, 48), csg="add"))

    # 45 deg ramp in XZ: right triangle with legs 128 (X) and 128 (Z); the hypotenuse normal
    # is (0.7071, 0, 0.7071).
    slant_xz = _prism([(-64, -64), (64, -64), (-64, 64)], 128, SQUARE)
    actors.append(builders.make_brush_actor("SlantXZ", slant_xz, (-640, -320, 0), csg="add"))

    # non-45 slope in YZ: legs 96 (Y) and 128 (Z) -> hypotenuse normal (0, 0.8, 0.6).
    # Build in XZ then relabel by swapping axes: easier to author the prism along X and rotate.
    slant_yz = _prism([(-48, -64), (48, -64), (-48, 64)], 128, WIDE)
    slant_yz = _swap_xy(slant_yz)
    actors.append(builders.make_brush_actor("SlantYZ", slant_yz, (-640, 320, 0), csg="add"))

    # fully diagonal: corner-cut tetra-ish wedge with one (1,1,1)/sqrt(3) face.
    slant_xyz = _corner_wedge(128, TALL)
    actors.append(builders.make_brush_actor("SlantXYZ", slant_xyz, (640, -320, 0), csg="add"))

    # a VERTICAL wall yawed off both world axes: normal (0.6, 0.8, 0).
    wall_yaw = _prism([(-80, -96), (80, -36), (80, 96), (-80, 96)], 160, SQUARE)
    wall_yaw = _yaw_prism(wall_yaw)
    actors.append(builders.make_brush_actor("WallYaw", wall_yaw, (640, 320, 0), csg="add"))

    return actors


def _swap_xy(brush):
    for p in brush.polys:
        p.vertices = [(y, x, z) for x, y, z in p.vertices]
        p.vertices = list(reversed(p.vertices))          # keep winding outward after the mirror
        p.origin = (p.origin[1], p.origin[0], p.origin[2])
        p.normal = (p.normal[1], p.normal[0], p.normal[2])
        n = p.normal
        u, v = builders._tex_basis(n)
        p.texture_u, p.texture_v = u, v
    return brush


def _yaw_prism(brush):
    """Rotate the whole brush 3-4-5 style in the XY plane: (x,y) -> (0.6x - 0.8y, 0.8x + 0.6y),
    so a face that was normal (1,0,0) becomes normal (0.6, 0.8, 0) — exact rational components,
    no float noise."""
    c, s = 0.6, 0.8

    def rot(v):
        x, y, z = float(v[0]), float(v[1]), float(v[2])
        return (c * x - s * y, s * x + c * y, z)

    for p in brush.polys:
        p.vertices = [rot(v) for v in p.vertices]
        p.origin = rot(p.origin)
        p.normal = rot(p.normal)
        u, v = builders._tex_basis(p.normal)
        p.texture_u, p.texture_v = u, v
    return brush


def _corner_wedge(size, tex):
    """A tetrahedron cut off a cube corner: three axis-aligned faces plus one (1,1,1)/sqrt3 face."""
    a = (0.0, 0.0, 0.0)
    b = (size, 0.0, 0.0)
    c = (0.0, size, 0.0)
    d = (0.0, 0.0, size)
    faces = [
        ([a, c, b], (0, 0, -1)),
        ([a, b, d], (0, -1, 0)),
        ([a, d, c], (-1, 0, 0)),
        ([b, c, d], (1, 1, 1)),
    ]
    return Brush(model_name="Model",
                 polys=[builders._face(r, o, tex, 0, item="OUTSIDE") for r, o in faces])


def main():
    out = Path(sys.argv[1])
    out.write_text(emit_map(build_actors()))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()

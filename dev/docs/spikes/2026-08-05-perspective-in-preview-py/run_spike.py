"""Spike harness: perspective-in-preview.py feasibility + perf + correctness sanity.

Builds a level, solves it through the SAME native CSG core `level preview --native` uses
(`preview_native.build_scene` -> `uedcli_native.build_geometry`), poses ONE shot with the
real SHOT grammar (`preview_shots` + `preview_native.camera_basis`), then renders that frame
BOTH ways over identical world polys/textures:
  - Rust `uedcli_native.render_frame` (the renderer being retired) -- the oracle.
  - the pure-Python prototype (`proto_render.render`).
Reports: CSG time, Rust raster time, Python raster time, mean-abs pixel diff.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parents[3]))   # repo root (dev/docs/spikes/<slug>/ -> repo)
sys.path.insert(0, str(_HERE))              # proto_render, alongside this file

import uedcli_native
from PIL import Image

from uedcli.model import Level
from uedcli.builders import cube, make_brush_actor
from uedcli.tests.conftest import StubClassIndex
from uedcli import preview_native as pn
from uedcli.preview_shots import parse_shot, resolve_pose

import proto_render

IDX = StubClassIndex()
SIZE = 1024
FOV = 75.0
OUT = str(_HERE)


def build_level(n_side=8):
    """A big subtracted hall with an n_side x n_side grid of additive pillars -- retail-ish
    surviving-surface count with full-frame coverage from inside."""
    lvl = Level()
    def add(a):
        lvl.actors[a.name] = a
        lvl.order.append(a.name)
    add(make_brush_actor("Hall", cube(4096, 4096, 1024), csg="subtract"))
    k = 0
    span = 4096
    step = span / (n_side + 1)
    for i in range(n_side):
        for j in range(n_side):
            x = -span / 2 + step * (i + 1)
            y = -span / 2 + step * (j + 1)
            add(make_brush_actor(f"Pillar{k}", cube(180, 180, 1024),
                                 location=(x, y, 0.0), csg="add"))
            k += 1
    return lvl


def checker_texture(size=256, cells=8):
    """A synthetic RGB checker so BOTH renderers exercise the textured sample path (the real
    substrate's game content is not present on this host)."""
    data = bytearray(size * size * 3)
    c = size // cells
    for y in range(size):
        for x in range(size):
            on = ((x // c) + (y // c)) & 1
            o = (y * size + x) * 3
            if on:
                data[o] = 210; data[o + 1] = 120; data[o + 2] = 60
            else:
                data[o] = 40; data[o + 1] = 90; data[o + 2] = 150
    return (size, size, bytes(data))


def main():
    n_side = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    lvl = build_level(n_side)
    n_brushes = 1 + n_side * n_side

    t = time.time()
    polys, _ = pn.build_scene(lvl, [], IDX)
    csg_s = time.time() - t

    # Inject one synthetic texture and point every poly at it, at 1 texel/uu (identical UV
    # frames both renderers already carry from build_scene).
    tex = checker_texture()
    textures = [tex]
    tex_polys = [(vf, bw, tu, tv, pan, 0) for (vf, bw, tu, tv, pan, _idx) in polys]

    # Pose one shot with the real grammar: eye inside the hall, look across the pillar grid.
    shot = parse_shot("at:-2400,-2400,380;look:1600,1600,-260")
    rs = resolve_pose(shot, lambda name: (0.0, 0.0, 0.0))
    fwd, right, up = pn.camera_basis(rs.pitch, rs.yaw)
    camera = (tuple(float(c) for c in rs.eye), fwd, right, up, float(FOV))

    def rust():
        return uedcli_native.render_frame(tex_polys, textures, camera, (SIZE, SIZE))

    def py():
        return proto_render.render(tex_polys, textures, camera, SIZE, SIZE)

    # warm + time Rust
    rust()
    t = time.time(); rgb_rust = rust(); rust_s = time.time() - t

    # time Python (single run -- it is the measurement)
    t = time.time(); rgb_py = py(); py_s = time.time() - t

    # mean-abs pixel diff
    assert len(rgb_rust) == len(rgb_py) == SIZE * SIZE * 3
    total = sum(abs(a - b) for a, b in zip(rgb_rust, rgb_py))
    mad = total / len(rgb_rust)
    nonbg_rust = sum(1 for i in range(0, len(rgb_rust), 3)
                     if (rgb_rust[i], rgb_rust[i+1], rgb_rust[i+2]) != proto_render.BACKGROUND)
    coverage = nonbg_rust / (SIZE * SIZE)

    Image.frombytes("RGB", (SIZE, SIZE), bytes(rgb_rust)).save(f"{OUT}/frame_rust.png")
    Image.frombytes("RGB", (SIZE, SIZE), bytes(rgb_py)).save(f"{OUT}/frame_py.png")
    # amplified diff image
    diff = bytearray(len(rgb_rust))
    for i in range(len(rgb_rust)):
        diff[i] = min(255, abs(rgb_rust[i] - rgb_py[i]) * 8)
    Image.frombytes("RGB", (SIZE, SIZE), bytes(diff)).save(f"{OUT}/frame_diff8x.png")

    print(f"scene: {n_brushes} brushes ({n_side}x{n_side} pillars), {len(polys)} surviving surfaces")
    print(f"size:  {SIZE}x{SIZE}  fov={FOV}  coverage(non-bg)={coverage*100:.1f}%")
    print(f"CSG solve (build_geometry, coarse core): {csg_s:.3f}s")
    print(f"Rust render_frame:   {rust_s:.3f}s")
    print(f"Python prototype:    {py_s:.3f}s   ({py_s/max(rust_s,1e-6):.0f}x Rust)")
    print(f"mean-abs pixel diff (Rust vs Python): {mad:.3f} / 255")

    # Self-check: the prototype must match the retiring Rust renderer. If this trips, the
    # affine-reuse + near-clip + perspective-divide port has drifted.
    assert mad < 1.0, f"prototype diverged from render.rs: mean-abs diff {mad:.3f} >= 1.0"
    assert coverage > 0.5, f"scene did not fill the frame (coverage {coverage:.2f})"
    print("OK: prototype matches render.rs (mean-abs diff < 1.0)")


if __name__ == "__main__":
    main()

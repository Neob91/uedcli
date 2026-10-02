"""Pin the KEY UNKNOWN in isolation: the near-plane Sutherland-Hodgman clip preview.py has no
analog for. Three cases (behind / straddling / in front), Python prototype vs Rust oracle over
identical polys. Mirrors render.rs's `near_plane_clips_geometry_behind_camera`, cross-checked."""
from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parents[3]))
sys.path.insert(0, str(_HERE))

import uedcli_native
import proto_render

# Camera at origin looking +X (UE1 forward), 90 deg fov.
CAMERA = ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0), 90.0)
SIZE = 64
BG = proto_render.BACKGROUND


def wall(verts):
    vf = [c for v in verts for c in v]
    # flat-grey (tex_index -1): geometry-only, isolates the clip.
    return (vf, [0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0], -1)


def nonbg(rgb):
    return sum(1 for i in range(0, len(rgb), 3) if (rgb[i], rgb[i+1], rgb[i+2]) != BG)


def both(polys):
    r = uedcli_native.render_frame(polys, [], CAMERA, (SIZE, SIZE))
    p = proto_render.render(polys, [], CAMERA, SIZE, SIZE)
    mad = sum(abs(a - b) for a, b in zip(r, p)) / len(r)
    return nonbg(r), nonbg(p), mad


# behind the camera (all d < 0): must render NOTHING, both.
behind = wall([(-100.0, -200.0, -200.0), (-100.0, 200.0, -200.0),
               (-100.0, 200.0, 200.0), (-100.0, -200.0, 200.0)])
# straddling the near plane (some verts d<NEAR, some d>NEAR): must clip cleanly, partial.
straddle = wall([(-50.0, -200.0, -10.0), (50.0, -200.0, -10.0),
                 (50.0, 200.0, -10.0), (-50.0, 200.0, -10.0)])
# fully in front: full coverage.
front = wall([(200.0, -400.0, -400.0), (200.0, 400.0, -400.0),
              (200.0, 400.0, 400.0), (200.0, -400.0, 400.0)])

for name, poly in (("behind", behind), ("straddle", straddle), ("front", front)):
    nr, npy, mad = both([poly])
    print(f"{name:9s} rust_nonbg={nr:5d} py_nonbg={npy:5d} mad={mad:.4f}")
    assert mad < 1.0, f"{name}: prototype clip diverged from render.rs (mad {mad:.3f})"

# explicit behavioral pins
assert both([behind])[1] == 0, "behind-camera wall must not wrap into view"
assert 0 < both([straddle])[1] < SIZE * SIZE, "straddling wall must clip to partial coverage"
print("OK: near-plane clip matches render.rs across behind/straddle/front")

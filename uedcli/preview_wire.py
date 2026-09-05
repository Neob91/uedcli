"""Perspective wireframe renderer for `level photo --native --faces wire`.

A freely-posed, content-free brush wireframe: the same CSG-op colours and drawing primitives
`actor diagram` uses, but projected through the shot camera instead of an orthographic view.

Reused from elsewhere (the point of `--faces wire` reusing `actor diagram`):

- `preview._CSG_PALETTE` / `preview.classify_brush` — brush edge colour by CSG op (name-guessed
  mover-ness, so wire needs no game class hierarchy — the owner-accepted cosmetic cost).
- `preview._line` / `preview._blit` / `preview._px` — the drawing primitives (generalised to a
  non-square `(w, h)` frame via `preview._dims`, since photo is 1280x960, not a square).
- `preview_native._mover_actor_world_polys` — the single base-pose actor->world transform home
  (`Location + L*(v - PrePivot)`); despite the name it is the base pose of ANY brush actor, which
  is exactly what a static-world brush and a mover-at-rest both want here.
- `preview_native.camera_basis` / `preview_shots.resolve_pose` / `shot_filename` — the shot grammar.
- The point-actor `PointRender` set is resolved in the command layer (dispatch owns schema/texture
  resolution; this module stays resolver-free, like `preview.py`) and passed in as `points`.

New here: the perspective projector and per-segment near-plane clip. Both match the Rust
`render_frame` (uedcli-native/src/render.rs) EXACTLY — horizontal FOV, `focal = (w/2)/tan(fov/2)`,
`screen = (w/2 + r*focal/d, h/2 - u*focal/d)`, near clip at `NEAR` uu — so a `wire` shot frames
identically to the `textured` shot at the same pose.
"""
from __future__ import annotations

import math
from pathlib import Path

from . import preview
from .normalize import is_builder_brush
from .preview_native import NativePreviewError, camera_basis
from .preview_shots import Shot, resolve_pose, shot_filename
from .preview_native import _mover_actor_world_polys, actor_aim_point

# render.rs constants, kept in sync so wire and textured share a frame.
NEAR = 4.0                      # uu; geometry nearer than this is clipped (render.rs `NEAR`)
BACKGROUND = (56, 56, 60)       # render.rs `BACKGROUND` — same bg as the textured native tier


def _dot(a, b) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


class _Camera:
    """A posed perspective camera: world -> camera frame -> pixels, matching render.rs."""

    def __init__(self, eye, fwd, right, up, fov_deg: float, size: tuple[int, int]) -> None:
        self.eye = eye
        self.fwd, self.right, self.up = fwd, right, up
        self.w, self.h = size
        self.focal = (self.w / 2.0) / math.tan(math.radians(fov_deg) / 2.0)

    def to_cam(self, p) -> tuple[float, float, float]:
        """World point -> (depth along forward, offset right, offset up)."""
        rel = (p[0] - self.eye[0], p[1] - self.eye[1], p[2] - self.eye[2])
        return (_dot(rel, self.fwd), _dot(rel, self.right), _dot(rel, self.up))

    def to_px(self, cam) -> tuple[int, int]:
        """Camera-frame point (depth > 0) -> integer pixel. y points DOWN (row-major)."""
        inv = 1.0 / cam[0]
        return (int(round(self.w / 2.0 + cam[1] * self.focal * inv)),
                int(round(self.h / 2.0 - cam[2] * self.focal * inv)))


def _clip_near(ca, cb) -> tuple | None:
    """Clip a camera-space segment to the near plane `depth >= NEAR` (render.rs `clip_near`, for a
    2-vertex ring). None when the whole segment is behind the camera."""
    a_in, b_in = ca[0] >= NEAR, cb[0] >= NEAR
    if not a_in and not b_in:
        return None
    if a_in and b_in:
        return ca, cb
    t = (NEAR - ca[0]) / (cb[0] - ca[0])
    mid = (NEAR, ca[1] + t * (cb[1] - ca[1]), ca[2] + t * (cb[2] - ca[2]))
    return (ca, mid) if a_in else (mid, cb)


def _wire_brushes(level) -> list[tuple[list, tuple[int, int, int]]]:
    """Every CSG brush actor (movers included) as (world verts, edge colour), base pose, trunk order.
    The transient builder brush is editor scratch and skipped, as in the CSG path."""
    out: list[tuple[list, tuple[int, int, int]]] = []
    for name in level.order:
        actor = level.actors.get(name)
        if actor is None or actor.brush is None or is_builder_brush(actor):
            continue
        rgb = preview._CSG_PALETTE[preview.classify_brush(actor)][0]   # is_mover=None: name guess
        for world, _actor, _poly in _mover_actor_world_polys(actor):
            out.append((world, rgb))
    return out


def _point_items(level, points: dict) -> list[tuple[tuple[float, float, float], object]]:
    """(world Location, PointRender) for each resolved point actor, so this module draws without a
    resolver. A point actor with no Location sits at the origin, matching `preview._draw_point_*`."""
    items = []
    for name, pr in points.items():
        actor = level.actors.get(name)
        if actor is None:
            continue
        loc = actor.location or (0, 0, 0)
        items.append(((float(loc[0]), float(loc[1]), float(loc[2])), pr))
    return items


def _render_frame(cam: _Camera, brushes, point_items) -> bytearray:
    size = (cam.w, cam.h)
    buf = bytearray(bytes(BACKGROUND) * (cam.w * cam.h))

    # Sprite billboards UNDER the wireframe so geometry stays readable (matches _draw_point_underlay).
    # World-sized footprint -> screen pixels scale as focal/depth (perspective), the analogue of the
    # ortho path's fixed `sprite_world * scale`.
    for loc, pr in point_items:
        if pr.sprite is None or pr.sprite_world is None:
            continue
        c = cam.to_cam(loc)
        if c[0] < NEAR:
            continue
        px, py = cam.to_px(c)
        tw, th, rgb, mask = pr.sprite
        pw = int(round(pr.sprite_world[0] * cam.focal / c[0]))
        ph = int(round(pr.sprite_world[1] * cam.focal / c[0]))
        preview._blit(buf, size, px, py, pw, ph, rgb, mask, tw, th)

    # Brush edges — facing-blind (every edge), each poly ring near-clipped then drawn.
    for world, rgb in brushes:
        cverts = [cam.to_cam(v) for v in world]
        n = len(cverts)
        for i in range(n):
            seg = _clip_near(cverts[i], cverts[(i + 1) % n])
            if seg is not None:
                preview._line(buf, size, cam.to_px(seg[0]), cam.to_px(seg[1]), rgb)

    # Markers OVER the wireframe for point actors with no sprite (matches _draw_point_marker legacy).
    for loc, pr in point_items:
        if pr.sprite is not None:
            continue
        c = cam.to_cam(loc)
        if c[0] < NEAR:
            continue
        px, py = cam.to_px(c)
        for d in range(-3, 4):
            preview._px(buf, size, px + d, py, preview.MARKER)
            preview._px(buf, size, px, py + d, preview.MARKER)
    return buf


def render_shots(*, level, shots: list[Shot], out_dir: Path, points: dict,
                 size: tuple[int, int], fov: float) -> int:
    """Render every SHOT as a perspective brush wireframe into `out_dir`. Returns the count written.
    Poses resolve up front, all-or-nothing, before any drawing (matching `preview_native`)."""
    from PIL import Image

    resolved = []
    for shot in shots:
        try:
            resolved.append(resolve_pose(shot, lambda n: actor_aim_point(level, n)))
        except ValueError as e:
            raise NativePreviewError(str(e)) from None

    brushes = _wire_brushes(level)
    point_items = _point_items(level, points)

    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        probe = out_dir / ".uedcli-writable"
        probe.touch()
        probe.unlink()
    except OSError as e:
        raise NativePreviewError(f"cannot write to --out-dir {out_dir}: {e}") from None

    taken: set[str] = set()
    written = 0
    for i, rs in enumerate(resolved):
        fwd, right, up = camera_basis(rs.pitch, rs.yaw)
        cam = _Camera(tuple(float(c) for c in rs.eye), fwd, right, up, float(fov), size)
        buf = _render_frame(cam, brushes, point_items)
        Image.frombytes("RGB", size, bytes(buf)).save(out_dir / shot_filename(shots[i], i, taken))
        written += 1
    return written

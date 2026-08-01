"""Native mesh thumbnail rasterizer — the software renderer behind `class preview`.

Promoted into `uedcli/` from spike `2026-07-25-native-mesh-decode` (`harness/render.py` +
`render_class.py`, which stay put as frozen evidence, mirroring `umesh.py`'s promotion). The
pipeline is editor-free, container-free, game-free: a class's default `Mesh` is decoded by `umesh`,
its skins resolve through `utexture` (P8 for DX class skins), and this module z-buffer-rasterizes
animation frame 0 with affine UV mapping + Lambert shading to a Pillow image.

**The one mesh-local frame** (`direction/asset-catalog.md`, class-arm spec §3, §4). The DEFAULT shot
applies the mesh's `Scale` per-axis, then the iso camera (yaw 45deg / pitch 20deg), and auto-centres
the framing — so `Origin` (a translation) drops out and the picture is in the SAME frame `class
show`'s extents use (`Scale` applied, pre-`Origin`/`RotOrigin`, `DrawScale` not). Picture and extents
therefore cannot disagree.

`--rotate P,Y,R` poses the mesh by a mesh-local FRotator (unreal rotator units, 65536 = 360deg)
BEFORE the iso camera shoots it — the pose oracle: preview a candidate placement rotation. The
reported `azimuth` is the camera's mesh-local yaw (`iso_yaw - rotate_yaw`), which `--rotate`'s yaw
component shifts. Azimuth does NOT claim world facing: a non-identity `RotOrigin` re-aims the mesh in
the world and stays unreconciled here, matching C1's scope.

The tool reports the picture, or a NAMED error (`direction/asset-catalog.md`): a referenced skin that
fails to decode raises `PreviewError` naming the ref, never a traceback or a wrong pixel. A material
with no resolvable texture is not a decode failure — it renders flat grey.
"""
from __future__ import annotations

import math

from . import utexture
from .rotation import euler_to_matrix_uu, matvec, uu_to_deg

# The single default shot: iso = front-three-quarter (spike defaults, spec §4 "iso").
ISO_YAW_DEG = 45.0
ISO_PITCH_DEG = 20.0
DEFAULT_SIZE = 512

_BG = (26, 28, 32)                 # thumbnail background
_FLAT_GREY = (170, 172, 178)       # a material with no texture
_LIGHT = (0.35, -0.5, 0.79)        # Lambert key light (spike render.py)


class PreviewError(Exception):
    """A `class preview` render could not be produced for a reason the user must see and fix — a
    referenced skin that will not decode. Carries a message naming the offending ref; the CLI turns
    it into a clean exit 2, never a traceback."""


def frame_triangles(mesh, frame: int = 0):
    """Triangles for one animation frame as `(v0, v1, v2, uv0, uv1, uv2, material_index)`.

    A `ULodMesh`'s renderable geometry is in Faces/Wedges (its `Tris` is empty) — Faces index Wedges,
    Wedges index Verts and carry the UV; a plain `UMesh` keeps geometry in `Tris`. `Verts` holds every
    frame back-to-back, so frame `f` starts at `f*FrameVerts`, and each frame begins with
    `SpecialVerts` attachment vertices that are NOT model geometry (a wedge's `iVertex` is relative to
    `frame_base + SpecialVerts`; omitting the shift shreds any mesh with attachments)."""
    base = frame * mesh.frame_verts + mesh.special_verts
    tris = []
    if mesh.faces:
        for (iw, mat) in mesh.faces:
            try:
                w = [mesh.wedges[i] for i in iw]
            except IndexError:
                continue
            vs, uvs = [], []
            for (iv, u, v) in w:
                k = base + iv
                if k >= len(mesh.verts):
                    break
                vs.append(mesh.verts[k])
                uvs.append((u, v))
            if len(vs) == 3:
                tris.append((vs[0], vs[1], vs[2], uvs[0], uvs[1], uvs[2], mat))
    else:                                            # plain UMesh: geometry lives in Tris
        for (iv, uv, _flags, tex) in mesh.tris:
            vs = [mesh.verts[base + i] for i in iv if base + i < len(mesh.verts)]
            if len(vs) == 3:
                tris.append((vs[0], vs[1], vs[2],
                             (uv[0], uv[1]), (uv[2], uv[3]), (uv[4], uv[5]), tex))
    return tris


def resolve_skins(mesh, pkg, defaults, package_paths, *, class_fqcn: str) -> dict:
    """`material index -> (w, h, rgb bytes)` for the mesh, decoded through `utexture`.

    Two sources, class-wins: the mesh's OWN `Textures` (via `Materials[i].TextureIndex`) are the
    fallback skin set, then the CLASS's `MultiSkins[i]` (per material index) / `Skin` override — the
    class is the authority, since DX characters carry no mesh-side skins. `package_paths` is the
    composed `.u` set (`ClassIndex.package_paths`); a ref present but undecodable raises `PreviewError`
    naming it (spec §4), a ref with no package/name simply leaves that material flat grey."""
    resolver = utexture.TextureResolver(list(package_paths))
    skins: dict = {}
    mats = mesh.materials or [(0, i) for i in range(max(1, len(mesh.textures)))]
    for mi, (_flags, tex_idx) in enumerate(mats):
        if not (0 <= tex_idx < len(mesh.textures)):
            continue
        path = pkg.object_path(mesh.textures[tex_idx])
        if not path:
            continue
        parts = path.split(".")
        ref = f"{parts[0]}.{parts[-1]}"              # Package.Name (drop any Group segment)
        got = resolver.resolve(ref)
        if isinstance(got, utexture.TextureError):
            raise PreviewError(f"cannot preview {class_fqcn}: mesh skin {ref} did not decode "
                               f"[{got.case}]: {got.detail}")
        skins[mi] = (got.width, got.height, got.rgb)
    for (prop, idx), val in defaults.items():        # class MultiSkins/Skin override per material idx
        if prop not in ("multiskins", "skin"):
            continue
        ref = _skin_ref(val)
        if ref is None:
            continue
        got = resolver.resolve(ref)
        if isinstance(got, utexture.TextureError):
            raise PreviewError(f"cannot preview {class_fqcn}: class {prop} {ref} did not decode "
                               f"[{got.case}]: {got.detail}")
        skins[idx if prop == "multiskins" else 0] = (got.width, got.height, got.rgb)
    return skins


def _skin_ref(text: str | None) -> str | None:
    """A `MultiSkins`/`Skin` default (`Texture'Pkg.Group.Name'`) → the `Package.Name` resolver key,
    or None for a missing/`None`/unparseable ref."""
    if not text or text.strip() in ("", "None"):
        return None
    import re
    m = re.match(r"^\s*\w+'([^']+)'\s*$", text)
    if m is None:
        return None
    parts = m.group(1).split(".")
    if len(parts) < 2:
        return None
    return f"{parts[0]}.{parts[-1]}"


def azimuth_uu(rotate_uu: tuple[int, int, int]) -> int:
    """The camera's mesh-local yaw for this shot, in unreal rotator units (65536 = 360deg). The iso
    camera sits at a fixed yaw (`ISO_YAW_DEG`); posing the mesh by `--rotate`'s yaw spins the mesh
    under it, so the yaw the camera looks FROM in the mesh's own frame is `iso_yaw - rotate_yaw`. This
    is a mesh-local reading, NOT world facing — `RotOrigin` is unreconciled (spec §4)."""
    from .rotation import deg_to_uu
    return (deg_to_uu(ISO_YAW_DEG) - rotate_uu[1]) % 65536


def render_class(mesh, skins: dict, *, rotate_uu=(0, 0, 0), size: int = DEFAULT_SIZE):
    """Rasterize `mesh` (skinned by `skins`) to a Pillow RGB `Image`, returning `(image, azimuth_uu)`.

    Frame: the mesh `Scale` is applied per-axis, then the mesh-local `--rotate` FRotator pose, then
    the fixed iso camera (yaw/pitch), then auto-centred framing. With the default `rotate_uu=(0,0,0)`
    the pose is identity, so the shot is in `class show`'s extents frame (`Scale`, pre-`Origin`, the
    translation dropped by auto-centre). Z-buffered, affine UV, Lambert shading — see the spike."""
    from PIL import Image

    tris = frame_triangles(mesh)
    if not tris:
        raise PreviewError(f"mesh {mesh.name} has no triangles to render "
                           f"(verts={len(mesh.verts)} faces={len(mesh.faces)})")
    sx, sy, sz = mesh.scale if any(mesh.scale) else (1.0, 1.0, 1.0)
    pose = euler_to_matrix_uu(int(rotate_uu[0]), int(rotate_uu[1]), int(rotate_uu[2]))
    cy, syaw = math.cos(math.radians(ISO_YAW_DEG)), math.sin(math.radians(ISO_YAW_DEG))
    cp, sp = math.cos(math.radians(ISO_PITCH_DEG)), math.sin(math.radians(ISO_PITCH_DEG))

    def view(v):
        x, y, z = matvec(pose, (v[0] * sx, v[1] * sy, v[2] * sz))   # Scale, then mesh-local pose
        x, y = x * cy - y * syaw, x * syaw + y * cy                 # camera yaw about Z
        y, z = y * cp - z * sp, y * sp + z * cp                     # camera pitch
        return (x, -z, y)                                           # screen x, screen y (down), depth

    pts = [view(v) for t in tris for v in t[:3]]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    span = max(max(xs) - min(xs), max(ys) - min(ys)) or 1.0
    k = (size * 0.86) / span
    ox = size / 2 - (min(xs) + max(xs)) / 2 * k
    oy = size / 2 - (min(ys) + max(ys)) / 2 * k

    img = Image.new("RGB", (size, size), _BG)
    px = img.load()
    zbuf = [1e30] * (size * size)
    for (a, b, c, ua, ub, uc, mat) in tris:
        va, vb, vc = view(a), view(b), view(c)
        e1 = tuple(vb[i] - va[i] for i in range(3))
        e2 = tuple(vc[i] - va[i] for i in range(3))
        n = (e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2],
             e1[0] * e2[1] - e1[1] * e2[0])
        nl = math.sqrt(sum(q * q for q in n)) or 1.0
        n = tuple(q / nl for q in n)
        shade = 0.30 + 0.70 * max(0.0, sum(n[i] * _LIGHT[i] for i in range(3)))
        p0 = (va[0] * k + ox, va[1] * k + oy, va[2])
        p1 = (vb[0] * k + ox, vb[1] * k + oy, vb[2])
        p2 = (vc[0] * k + ox, vc[1] * k + oy, vc[2])
        area = (p1[0] - p0[0]) * (p2[1] - p0[1]) - (p2[0] - p0[0]) * (p1[1] - p0[1])
        if abs(area) < 1e-9:
            continue
        skin = skins.get(mat)
        minx = max(0, int(min(p0[0], p1[0], p2[0])))
        maxx = min(size - 1, int(max(p0[0], p1[0], p2[0])) + 1)
        miny = max(0, int(min(p0[1], p1[1], p2[1])))
        maxy = min(size - 1, int(max(p0[1], p1[1], p2[1])) + 1)
        for Y in range(miny, maxy + 1):
            for X in range(minx, maxx + 1):
                fx, fy = X + 0.5, Y + 0.5
                w0 = ((p1[0] - p0[0]) * (fy - p0[1]) - (fx - p0[0]) * (p1[1] - p0[1])) / area
                w1 = ((fx - p0[0]) * (p2[1] - p0[1]) - (p2[0] - p0[0]) * (fy - p0[1])) / area
                w2 = 1.0 - w0 - w1
                if w0 < 0 or w1 < 0 or w2 < 0:
                    continue
                depth = w2 * p0[2] + w1 * p1[2] + w0 * p2[2]
                idx = Y * size + X
                if depth >= zbuf[idx]:
                    continue
                zbuf[idx] = depth
                if skin:
                    tw, th, rgb = skin
                    u = (w2 * ua[0] + w1 * ub[0] + w0 * uc[0]) * tw / 256.0
                    v = (w2 * ua[1] + w1 * ub[1] + w0 * uc[1]) * th / 256.0
                    o = ((int(v) % th) * tw + (int(u) % tw)) * 3
                    col = (rgb[o], rgb[o + 1], rgb[o + 2])
                else:
                    col = _FLAT_GREY
                px[X, Y] = tuple(min(255, int(col[i] * shade)) for i in range(3))
    return img, azimuth_uu(rotate_uu)

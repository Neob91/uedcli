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

PF_TRANSLUCENT = 0x4
PF_MODULATED = 0x40
# Real UE1 blend formulas for an 8-bit paletted texture with no per-texel alpha
# (`dev/docs/unrealed/leveldesign/kb/textures.md` "Translucent"/"Modulated"): Translucent is
# ADDITIVE (`dest + src`, clamped -- a black texel is near-invisible, a bright one glows);
# Modulated is D3D modulate-2x (`dest * src / 128`, clamped -- 50%-grey src is neutral).
# `GM_Trench`'s eye-height glasses-lens materials use these (real PolyFlags 0x104/0x140).

_BG = (26, 28, 32)                 # thumbnail background
_FLAT_GREY = (170, 172, 178)       # a material with no texture
_LIGHT = (0.35, -0.5, 0.79)        # Lambert key light (spike render.py)


class PreviewError(Exception):
    """A `class preview` render could not be produced for a reason the user must see and fix — a
    referenced skin that will not decode. Carries a message naming the offending ref; the CLI turns
    it into a clean exit 2, never a traceback."""


def frame_triangles(mesh, frame: int = 0):
    """Triangles for one animation frame as
    `(v0, v1, v2, uv0, uv1, uv2, material_index, poly_flags)`.

    A `ULodMesh`'s renderable geometry is in Faces/Wedges (its `Tris` is empty) — Faces index Wedges,
    Wedges index Verts and carry the UV; a plain `UMesh` keeps geometry in `Tris`. `Verts` holds every
    frame back-to-back, so frame `f` starts at `f*FrameVerts`, and each frame begins with
    `SpecialVerts` attachment vertices that are NOT model geometry (a wedge's `iVertex` is relative to
    `frame_base + SpecialVerts`; omitting the shift shreds any mesh with attachments).

    `poly_flags` comes from a DIFFERENT field depending on mesh kind: a LodMesh's
    `Materials[material_index].PolyFlags`, a plain Mesh's own per-triangle `FMeshTri.PolyFlags` —
    they are not interchangeable (`dev/docs/board/.../native-mesh-rendering-in-level-photo-native/
    spec.md`)."""
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
                flags = mesh.materials[mat][0] if 0 <= mat < len(mesh.materials) else 0
                tris.append((vs[0], vs[1], vs[2], uvs[0], uvs[1], uvs[2], mat, flags))
    else:                                            # plain UMesh: geometry lives in Tris
        for (iv, uv, flags, tex) in mesh.tris:
            vs = [mesh.verts[base + i] for i in iv if base + i < len(mesh.verts)]
            if len(vs) == 3:
                tris.append((vs[0], vs[1], vs[2],
                             (uv[0], uv[1]), (uv[2], uv[3]), (uv[4], uv[5]), tex, flags))
    return tris


# Procedural (bitmap-less) skin placeholder, as the (w, h, rgb, b_masked, mask) skin-tuple shape
# this module returns -- derived from `utexture.PROCEDURAL_RED` (the shared substitute every
# native-draft caller uses) so the two can never drift apart. Real procedural rendering is a
# tracked follow-up (board `native-draft-rasterizer-procedural-mesh-skins`).
PROCEDURAL_RED = (utexture.PROCEDURAL_RED.width, utexture.PROCEDURAL_RED.height,
                   utexture.PROCEDURAL_RED.rgb, bool(utexture.PROCEDURAL_RED.b_masked),
                   utexture.PROCEDURAL_RED.mask)


def resolve_skins(mesh, pkg, defaults, search_files, *, class_fqcn: str, class_index=None) -> dict:
    """`material index -> (w, h, rgb bytes, b_masked, mask bytes)` for the mesh, decoded through
    `utexture`.

    Reproduces `UMesh::GetTexture(Count, Owner)` (`Engine.dll` RVA `0x1129a0`, disassembly+live-probe
    verified — `dev/docs/unrealed/rendering.md` "Mesh material-slot skin resolution", evidence in
    `dev/docs/spikes/2026-09-10-multiskin-skin-precedence/`), the ONE function every mesh class
    resolves a material slot's texture through, per slot `i`:

        MultiSkins[i]  ->  (i != 0 and Textures[i])  ->  Skin  ->  Textures[i]

    `MultiSkins[i]` always wins; `Skin` is a SLOT-0-FIRST fallback, not a whole-mesh override — it
    reaches a non-zero slot only when the mesh has no texture of its own there. `defaults` is
    EFFECTIVE, not necessarily class-only: `class preview` passes plain class defaults, while `level
    photo --native`'s per-actor mesh render passes `ChainMap(actor's own stored props, class
    defaults)` so a placed actor's own override wins over its class's (board
    `per-actor-skins-override-in-native-mesh-render`) — `resolve_skins` itself is agnostic to which,
    it just reads whatever `defaults` hands it for each `("multiskins"|"skin", i)` key.

    `i` here is `Count` itself — the mesh's own `Textures` index, NOT the material-list ordinal
    (board `resolve-skins-keys-by-material-ordinal-not`, closed: keying by material ordinal instead
    shifted skins onto the wrong material for any mesh where `Materials[i].TextureIndex != i` —
    confirmed on `DeusExCharacters.GM_Trench`, materials 3-6 of 7, each landing one slot off).
    Resolution runs once per real texture index a MATERIAL actually references (not the full
    `range(Textures.Num())` `DrawLodMesh` loops — an unreferenced slot's bad/procedural ref would
    otherwise raise or decode for pixels nothing ever shows, unlike the real engine's mere pointer
    fetch there), then each MATERIAL is re-keyed to its resolved texture via its own `TextureIndex`
    — the shape triangles actually reference (`frame_triangles`' `material_index`).

    `search_files` is the FULL composed search path (all package extensions) — NOT the `.u`-only
    `ClassIndex.package_paths`: a skin can live in a `.utx` (`Effects.BioCell_SFX`), never on the
    `.u` set, and the full path also covers deco skins that live in a deco `.u`. `class_index`
    WIDENS the resolver from the exact `Texture` class to every `Engine.Texture` descendant, so a
    procedural skin (a FireTexture etc.) resolves to `no-mip-data` rather than `unknown-texture`.

    A procedural (`no-mip-data`) skin renders as solid RED (`PROCEDURAL_RED`) — the draft rasterizer
    has no bitmap to sample. Any OTHER undecodable ref still raises `PreviewError` naming it
    (spec §4); a ref with no package/name simply leaves that material flat grey.

    `b_masked` is the texture's own `bMasked` render-policy flag, carried out as a fact for callers
    that alpha-test (`level photo --native`): the engine ORs a texture's PolyFlags onto every surface
    it is applied to, so a bMasked skin masks even with no PF_Masked triangle flag. `mask` is the
    decoded per-texel mask (`DecodedTexture.mask`, `width*height` bytes, 1=opaque/0=transparent) —
    the real alpha data the rasterizer's mask test needs, not a synthesized stand-in."""
    resolver = utexture.TextureResolver(list(search_files), class_index=class_index)

    def skin_tuple(got, what: str):
        """`got` → the skin tuple. `got` has already had `utexture.resolve_or_procedural_red`
        applied by the caller, so a procedural (`no-mip-data`) miss already IS
        `utexture.PROCEDURAL_RED` here. Any other `TextureError` raises `PreviewError` naming
        `what` and the case."""
        if isinstance(got, utexture.TextureError):
            raise PreviewError(f"cannot preview {class_fqcn}: {what} did not decode "
                               f"[{got.case}]: {got.detail}")
        return (got.width, got.height, got.rgb, bool(got.b_masked), got.mask)

    mats = mesh.materials or [(0, i) for i in range(max(1, len(mesh.textures)))]

    def texture_ref_at(t: int) -> str | None:
        """`Textures[t]`'s resolver key (`t` is `Count` — the mesh's own texture index), or None
        when `t` is out of range or unset."""
        if not (0 <= t < len(mesh.textures)):
            return None
        path = pkg.object_path(mesh.textures[t])
        if not path:
            return None
        parts = path.split(".")
        return f"{parts[0]}.{parts[-1]}"              # Package.Name (drop any Group segment)

    # Only texture indices some MATERIAL actually references — not the full `Textures.Num()` range
    # `DrawLodMesh` loops (a mesh can carry unreferenced texture slots; a bad/procedural ref THERE
    # would raise or decode for pixels nothing ever shows, unlike the real engine, which only ever
    # fetches a POINTER per slot, not a full decode).
    resolved: dict[int, tuple] = {}
    for t in sorted({tex_idx for _flags, tex_idx in mats if 0 <= tex_idx < len(mesh.textures)}):
        multiskin_ref = _skin_ref(defaults.get(("multiskins", t)))
        if multiskin_ref is not None:
            resolved[t] = skin_tuple(utexture.resolve_or_procedural_red(resolver, multiskin_ref),
                                     f"multiskins override {multiskin_ref}")
            continue
        mesh_ref = texture_ref_at(t)
        if t != 0 and mesh_ref is not None:
            resolved[t] = skin_tuple(utexture.resolve_or_procedural_red(resolver, mesh_ref),
                                     f"mesh skin {mesh_ref}")
            continue
        skin_ref = _skin_ref(defaults.get(("skin", 0)))
        if skin_ref is not None:
            resolved[t] = skin_tuple(utexture.resolve_or_procedural_red(resolver, skin_ref),
                                     f"skin override {skin_ref}")
            continue
        if mesh_ref is not None:
            resolved[t] = skin_tuple(utexture.resolve_or_procedural_red(resolver, mesh_ref),
                                     f"mesh skin {mesh_ref}")

    # Re-key by MATERIAL — the shape triangles reference (`frame_triangles`' `material_index`),
    # via each material's own `TextureIndex` (its real `Count`).
    skins: dict = {}
    for mi, (_flags, tex_idx) in enumerate(mats):
        if tex_idx in resolved:
            skins[mi] = resolved[tex_idx]
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
    translation dropped by auto-centre). Z-buffered, affine UV, Lambert shading — see the spike.

    Every OPAQUE triangle draws first (z-tested + z-written, as always). `PF_Translucent`/
    `PF_Modulated` triangles draw in a SECOND pass, back-to-front (painter's), z-TESTED against that
    opaque buffer but never z-WRITTEN — so overlapping blended layers all test against the same
    opaque depth and composite in draw order, nearest last. See the module-level `PF_TRANSLUCENT`/
    `PF_MODULATED` comment for the blend formulas."""
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

    def project(t):
        (a, b, c, *_rest) = t
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
        return p0, p1, p2, shade

    def draw_tri(p0, p1, p2, ua, ub, uc, mat, shade, *, blend_flags):
        area = (p1[0] - p0[0]) * (p2[1] - p0[1]) - (p2[0] - p0[0]) * (p1[1] - p0[1])
        if abs(area) < 1e-9:
            return
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
                    continue                                # opaque geometry already nearer here
                if skin:
                    tw, th, rgb, _b_masked, _mask = skin  # thumbnails draw opaque: no alpha test here
                    u = (w2 * ua[0] + w1 * ub[0] + w0 * uc[0]) * tw / 256.0
                    v = (w2 * ua[1] + w1 * ub[1] + w0 * uc[1]) * th / 256.0
                    o = ((int(v) % th) * tw + (int(u) % tw)) * 3
                    col = (rgb[o], rgb[o + 1], rgb[o + 2])
                else:
                    col = _FLAT_GREY
                shaded = tuple(min(255, int(col[i] * shade)) for i in range(3))
                if not blend_flags:
                    zbuf[idx] = depth                       # opaque: z-tested AND z-written
                    px[X, Y] = shaded
                elif blend_flags & PF_TRANSLUCENT:
                    dest = px[X, Y]                         # additive, no z-write (see module doc)
                    px[X, Y] = tuple(min(255, dest[i] + shaded[i]) for i in range(3))
                else:                                       # PF_MODULATED: modulate-2x, no z-write
                    dest = px[X, Y]
                    px[X, Y] = tuple(min(255, (dest[i] * shaded[i]) // 128) for i in range(3))

    opaque = [t for t in tris if not (t[7] & (PF_TRANSLUCENT | PF_MODULATED))]
    blended = [t for t in tris if t[7] & (PF_TRANSLUCENT | PF_MODULATED)]

    for t in opaque:
        p0, p1, p2, shade = project(t)
        draw_tri(p0, p1, p2, t[3], t[4], t[5], t[6], shade, blend_flags=0)

    # Painter's back-to-front: farthest (largest avg depth) first, so a nearer blended layer
    # composites on top of a farther one.
    projected_blend = sorted(((project(t), t) for t in blended),
                             key=lambda pt: -(pt[0][0][2] + pt[0][1][2] + pt[0][2][2]))
    for (p0, p1, p2, shade), t in projected_blend:
        draw_tri(p0, p1, p2, t[3], t[4], t[5], t[6], shade, blend_flags=t[7])

    return img, azimuth_uu(rotate_uu)

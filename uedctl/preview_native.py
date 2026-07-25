"""`level preview --native` — the offline draft backend (spec
`dev/docs/specs/2026-07-16-native-preview-design.md`). Zero docker, zero editor, zero game:
the trunk is carved in-process by the Rust CSG core (`uedctl_native.build_geometry`), each
built surface is joined back to its SOURCE brush poly for texture/Pan/flags (the same
`i_actor`/`i_brush_poly` provenance `assemble._patch_surf_refs` consumes at materialize),
textures decode natively (`uedctl.utexture`), and `uedctl_native.render_frame` software-
rasterizes each SHOT pose to an RGB buffer that Pillow encodes as PNG.

Deliberate divergences from `materialize._build_brush_input` (spec §4.2):
- **Rotation passes through** as the GMath rot3x3 (a DRAFT preview of a rotated brush beats
  an error; validated offline against `rotation.world_vertices`, not editor goldens).
- **Scale/sheer are checked here, explicitly**: non-identity `MainScale`/`PostScale`/
  `SheerRate` → a named error (materialize's check misses PostScale/SheerRate — boarded).

The per-surf UV frame is computed HERE, Python-side, from the source poly's authored
`Origin`/`TextureU`/`TextureV`/`Pan` (`base_w = Location + R·(Origin − PrePivot)`,
`axes_w = R·axes`) — the built surf's texture vectors are NEVER read (the build synthesizes
default axes that ignore authored alignment, and Pan doesn't survive the build at all;
spec §5). Movers are out of world CSG, so they render directly as world-transformed
`extra_polys` at the base pose (`rotation.actor_matrix` — the same math every measurement
verb uses)."""
from __future__ import annotations

import math
import re
import sys
from pathlib import Path

from . import movers
from .normalize import is_builder_brush
from .preview_shots import ResolvedShot, Shot, resolve_pose, shot_filename
from .rotation import (actor_matrix, actor_prepivot, deg_to_uu, euler_to_matrix_uu, matvec)
from .utexture import TextureResolver

PF_INVISIBLE = 0x1

# The game's first-person default horizontal FOV: Engine.PlayerPawn defaultproperties
# `DesiredFOV=75.000000` / `DefaultFOV=75.000000` (DX install `Engine/Classes/PlayerPawn.uc:4940`,
# read 2026-07-16; DeusExPlayer does not override it). Spec §3 pins --fov's default to this.
DEFAULT_FOV = 75.0
DEFAULT_SIZE = (1280, 960)

_IDENTITY_ROT = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
_CSG_OPER = {"CSG_Add": 1, "CSG_Subtract": 2}

# The unresolvable-texture checkerboard (spec §4.5): magenta/black 8-px checks, 64².
_CHECKER_SIZE, _CHECKER_CELL = 64, 8


class NativePreviewError(Exception):
    """User-facing native-preview failure (→ stderr + exit 2, never a traceback)."""


# --------------------------------------------------------------------- scale/sheer gate

_SCALE_XYZ = re.compile(r"Scale=\(([^)]*)\)")
_AXIS_VAL = re.compile(r"\b([XYZ])=(-?[0-9.]+)")
_SHEER_RATE = re.compile(r"SheerRate=(-?[0-9.]+)")


def _scale_identity(raw_value: str) -> tuple[bool, str]:
    """Is a `MainScale`/`PostScale` T3D value the identity transform? Returns
    (identity?, offending-part). The value form is
    `( [Scale=(X=..,Y=..,Z=..),] [SheerRate=..,] SheerAxis=.. )` — a Scale axis is present
    iff ≠ 1.0, SheerRate iff ≠ 0.0 (quirks.md "Scale & sheer"). `SheerAxis` alone is
    identity."""
    m = _SCALE_XYZ.search(raw_value)
    if m:
        for axis, val in _AXIS_VAL.findall(m.group(1)):
            try:
                if float(val) != 1.0:
                    return False, f"Scale {axis}={val}"
            except ValueError:
                return False, f"Scale {axis}={val!r}"
    m = _SHEER_RATE.search(raw_value)
    if m:
        try:
            if float(m.group(1)) != 0.0:
                return False, f"SheerRate={m.group(1)}"
        except ValueError:
            return False, f"SheerRate={m.group(1)!r}"
    return True, ""


def _reject_scaled(name: str, actor) -> None:
    """Named exit-2 on any non-identity MainScale/PostScale/SheerRate (spec §4.2/§7).
    The native geometry core still passes identity scale to Rust, so a scaled brush would build
    wrong — reject loudly. Scale now lives in the typed model fields (spec §10); re-serialize each to
    the T3D form so the existing identity check applies unchanged."""
    from .transform import emit_fscale
    fields = (("MainScale", actor.main_scale), ("PostScale", actor.post_scale))
    for field, fs in fields:
        if fs is None:
            continue
        ok, part = _scale_identity(emit_fscale(fs))
        if not ok:
            raise NativePreviewError(
                f"brush {name}: non-identity {field} ({part}) is not supported by the native "
                f"preview (scale support is a deferred spec; remove the scale or use --game "
                f"when that tier lands)")


# --------------------------------------------------------------------- brush inputs

def _poly_flags_int(raw: dict) -> int:
    try:
        return int(raw.get("PolyFlags", "0"))
    except ValueError:
        return 0


def _rot3x3(actor):
    R = actor_matrix(actor)                  # None == renders-as-identity (low-bit fields)
    return _IDENTITY_ROT if R is None else R


def _brush_inputs(level, index) -> tuple[list, list[tuple[str, list]]]:
    """CSG brush actors (trunk order) → the `BrushTuple` flat buffers `build_geometry`
    takes, plus the `(actor_name, polys)` join list indexed by the surf `i_actor` tag.
    Movers and the transient builder brush are EXCLUDED from world CSG (movers render as
    extra_polys; the builder brush is editor scratch)."""
    from .native.materialize import _parse_vec3

    brushes, join = [], []
    for name in level.order:
        actor = level.actors.get(name)
        if actor is None or actor.brush is None:
            continue
        if movers.is_mover(actor, index) or is_builder_brush(actor):
            continue
        raw = dict(actor.props)
        oper = _CSG_OPER.get(raw.get("CsgOper", "CSG_Add"))
        if oper is None:
            # Intersect/Deintersect never appear in a trunk (they are live-editor verbs);
            # anything unknown renders nothing — skip loudly rather than mis-build.
            print(f"WARNING: brush {name}: CsgOper {raw.get('CsgOper')!r} is not a world CSG "
                  f"op; skipped", file=sys.stderr)
            continue
        _reject_scaled(name, actor)
        loc = tuple(float(c) for c in actor.location) if actor.location else (0.0, 0.0, 0.0)
        prepivot = _parse_vec3(raw.get("PrePivot"))

        verts_flat: list[float] = []
        poly_sizes: list[int] = []
        normals_flat: list[float] = []
        poly_flags_flat: list[int] = []
        have_all_normals = True
        for poly in actor.brush.polys:
            poly_sizes.append(len(poly.vertices))
            for v in poly.vertices:
                verts_flat += [float(v[0]), float(v[1]), float(v[2])]
            if poly.normal is not None:
                normals_flat += [float(poly.normal[0]), float(poly.normal[1]),
                                 float(poly.normal[2])]
            else:
                have_all_normals = False
            poly_flags_flat.append(poly.flags or 0)
        if not have_all_normals:
            normals_flat = []                        # Rust CalcNormal from winding
        # Empty per-poly texture-axis lists: preview derives its UV frames from the join polys'
        # authored axes separately (see `# UV frames` below), so the built model's surf axes are
        # unused here — leaving them empty keeps the built geometry byte-for-byte as before.
        # Trailing empties: tex_u, then the (tex_v, origins, vec_xform) triple — all defaulted here
        # (preview derives UV frames from the join polys separately, its built geometry is
        # pBase-agnostic so base stays verts[0], and preview rejects scaled brushes so no covariant
        # normal map is needed).  The triple keeps the marshalled arity at 12 (PyO3 tuple cap).
        brushes.append((verts_flat, poly_sizes, normals_flat, oper, _poly_flags_int(raw),
                        list(loc), _rot3x3(actor), list(prepivot), [1.0, 1.0, 1.0],
                        poly_flags_flat, [], ([], [], [])))
        join.append((name, actor.brush.polys))
    return brushes, join


# --------------------------------------------------------------------- UV frames

def _tex_basis_default(normal):
    """The Python default matching `builders._tex_basis` (spec §5 fallback): unit in-plane
    axes seeded from the world axis least aligned with the normal."""
    from .builders import _tex_basis
    return _tex_basis(normal)


def _newell(verts) -> tuple[float, float, float]:
    n = [0.0, 0.0, 0.0]
    for i in range(len(verts)):
        a, b = verts[i], verts[(i + 1) % len(verts)]
        n[0] += (a[1] - b[1]) * (a[2] + b[2])
        n[1] += (a[2] - b[2]) * (a[0] + b[0])
        n[2] += (a[0] - b[0]) * (a[1] + b[1])
    return tuple(n)


def _world_uv_frame(actor, poly):
    """The source poly's authored texture frame, transformed to world space:
    `base_w = Location + R·(Origin − PrePivot)`, `axes_w = R·axes`. Missing Origin → local
    zero; missing/zero axes → the `_tex_basis`-matching default (spec §5)."""
    loc = tuple(float(c) for c in (actor.location or (0, 0, 0)))
    pp = tuple(float(c) for c in actor_prepivot(actor))
    R = actor_matrix(actor)

    origin = tuple(float(c) for c in poly.origin) if poly.origin is not None else (0.0, 0.0, 0.0)
    rel = (origin[0] - pp[0], origin[1] - pp[1], origin[2] - pp[2])
    if R is not None:
        rel = matvec(R, rel)
    base_w = (loc[0] + rel[0], loc[1] + rel[1], loc[2] + rel[2])

    tu = tuple(float(c) for c in poly.texture_u) if poly.texture_u is not None else None
    tv = tuple(float(c) for c in poly.texture_v) if poly.texture_v is not None else None

    def _zero(v):
        return v is None or (abs(v[0]) + abs(v[1]) + abs(v[2])) < 1e-12

    if _zero(tu) or _zero(tv):
        n = tuple(float(c) for c in poly.normal) if poly.normal is not None \
            else _newell([tuple(float(c) for c in v) for v in poly.vertices])
        size = math.sqrt(sum(c * c for c in n)) or 1.0
        tu, tv = _tex_basis_default(tuple(c / size for c in n))
    if R is not None:
        tu, tv = tuple(matvec(R, tu)), tuple(matvec(R, tv))
    pan = (float(poly.pan[0]), float(poly.pan[1])) if poly.pan else (0.0, 0.0)
    return base_w, tu, tv, pan


# --------------------------------------------------------------------- geometry extract

def _node_polys(model) -> list[tuple[list[tuple[float, float, float]], int, int]]:
    """Each BSP node's polygon from its vert pool → (world verts, i_actor, i_brush_poly).
    Guarded like `assemble._patch_surf_refs`: an out-of-range index never raises — the surf
    joins to no source poly and renders flat grey."""
    out = []
    for n in model.nodes:
        if n.num_vertices < 3:
            continue
        if not (0 <= n.i_surf < len(model.surfs)):
            continue
        if n.i_vert_pool < 0 or n.i_vert_pool + n.num_vertices > len(model.verts):
            continue
        idx = [model.verts[n.i_vert_pool + k].i_vertex for k in range(n.num_vertices)]
        if any(not (0 <= i < len(model.points)) for i in idx):
            continue
        s = model.surfs[n.i_surf]
        out.append(([model.points[i] for i in idx], s.i_actor, s.i_brush_poly))
    return out


def _mover_world_polys(level, index) -> list[tuple[list, object, object]]:
    """Movers render directly (no BSP surfs): each brush poly world-transformed at the BASE
    pose (`Location + R·(v − PrePivot)` — `rotation.actor_matrix` path). Returns
    `(world_verts, actor, poly)` so the UV frame comes from the same authored fields.
    A draft preview without doors would be actively misleading (spec §5)."""
    out = []
    for name in level.order:
        actor = level.actors.get(name)
        if actor is None or actor.brush is None or not movers.is_mover(actor, index):
            continue
        _reject_scaled(name, actor)
        loc = tuple(float(c) for c in (actor.location or (0, 0, 0)))
        pp = tuple(float(c) for c in actor_prepivot(actor))
        R = actor_matrix(actor)
        for poly in actor.brush.polys:
            world = []
            for v in poly.vertices:
                rel = (float(v[0]) - pp[0], float(v[1]) - pp[1], float(v[2]) - pp[2])
                if R is not None:
                    rel = matvec(R, rel)
                world.append((loc[0] + rel[0], loc[1] + rel[1], loc[2] + rel[2]))
            out.append((world, actor, poly))
    return out


# --------------------------------------------------------------------- textures

def _checkerboard() -> tuple[int, int, bytes]:
    """The unresolvable-ref placeholder: magenta/black checks — the miss is visible in the
    render itself (spec §4.5)."""
    data = bytearray()
    for y in range(_CHECKER_SIZE):
        for x in range(_CHECKER_SIZE):
            on = ((x // _CHECKER_CELL) + (y // _CHECKER_CELL)) % 2 == 0
            data += b"\xff\x00\xff" if on else b"\x00\x00\x00"
    return (_CHECKER_SIZE, _CHECKER_SIZE, bytes(data))


class _TextureTable:
    """Distinct texture refs → table indices; unresolvable refs share one checkerboard slot
    and warn ONCE per distinct ref (spec §4.5)."""

    def __init__(self, resolver: TextureResolver) -> None:
        self._resolver = resolver
        self.table: list[tuple[int, int, bytes]] = []
        self._by_ref: dict[str, int] = {}
        self._checker_index: int | None = None

    def index_for(self, ref: str | None) -> int:
        if not ref:
            return -1                                    # no texture set → flat grey
        key = ref.casefold()
        if key in self._by_ref:
            return self._by_ref[key]
        got = self._resolver.resolve(ref)
        if got is None:
            print(f"WARNING: texture {ref!r} not resolvable on the composed search path; "
                  f"rendering a checkerboard (qualify the ref as Package.Name and check "
                  f"`project show`)", file=sys.stderr)
            if self._checker_index is None:
                self._checker_index = len(self.table)
                self.table.append(_checkerboard())
            idx = self._checker_index
        else:
            idx = len(self.table)
            self.table.append(got)
        self._by_ref[key] = idx
        return idx


# --------------------------------------------------------------------- camera

def camera_basis(pitch_deg: float, yaw_deg: float):
    """(forward, right, up) world basis for an FRotator pose, via the GMath-verified
    `euler_to_matrix_uu` (degrees quantize to the stored integer field first — exactly what
    the game renders). This is the SINGLE source of the camera convention: Rust receives
    the basis and never converts angles (spec §5, plan refinement 3)."""
    R = euler_to_matrix_uu(deg_to_uu(pitch_deg), deg_to_uu(yaw_deg), 0)
    return (tuple(matvec(R, (1.0, 0.0, 0.0))),           # forward (UE1 +X)
            tuple(matvec(R, (0.0, 1.0, 0.0))),           # right (+Y)
            tuple(matvec(R, (0.0, 0.0, 1.0))))           # up (+Z)


# --------------------------------------------------------------------- aim points

def actor_aim_point(level, name: str) -> tuple[float, float, float]:
    """The point `look:@name`/`orbit:@name` aims at: a brush actor's world-AABB centre (its
    `Location` is the pivot — the wrong target), a point actor's `Location`. Raises
    NativePreviewError naming an unknown actor (case-insensitive resolution)."""
    from .query import resolve_actor_name
    from .writes import actor_bounds
    try:
        canon = resolve_actor_name(level, name)
    except KeyError:
        raise NativePreviewError(f"actor not found: {name}") from None
    actor = level.actors[canon]
    if actor.brush is not None:
        lo, hi = actor_bounds(actor)
        return tuple((float(lo[i]) + float(hi[i])) / 2.0 for i in range(3))
    loc = actor.location or (0, 0, 0)
    return tuple(float(c) for c in loc)


# --------------------------------------------------------------------- orchestration

def build_scene(level, search_files, index) -> tuple[list, list]:
    """Trunk → (render polys, texture table): CSG build + node-poly extraction + source-poly
    join + Python UV frames + mover extra_polys + native texture decode. Raises
    NativePreviewError on every named RENDER failure path (spec §7). `index` is a
    `classindex.ClassIndex`: movers are excluded from world CSG and rendered separately, and
    mover-ness is decided schema-aware by `movers.is_mover` against the game's class hierarchy —
    an unresolvable class therefore raises `classindex.ClassRefError` (naming the class) straight
    through this function, rather than a `NativePreviewError`; dispatch's top-level guard turns it
    into the same clean exit 2."""
    try:
        import uedctl_native
    except ImportError:
        raise NativePreviewError(
            "the uedctl_native extension is not built — `level preview --native` needs it "
            "(build with `maturin develop`, or run bin/test once)") from None

    brushes, join = _brush_inputs(level, index)
    if not brushes:
        raise NativePreviewError("nothing to render: the trunk has no CSG brush actors")
    try:
        built = uedctl_native.build_geometry(brushes)
        body = uedctl_native.serialize_model(built)
    except uedctl_native.BuildError as ex:
        raise NativePreviewError(f"native CSG build failed: {ex}") from ex
    from .native.umodel import parse_model_body
    model = parse_model_body(body, 0, len(body))

    textures = _TextureTable(TextureResolver(search_files))
    polys = []

    def add_poly(world_verts, actor, poly):
        flags = (poly.flags or 0) | (_poly_flags_int(dict(actor.props)) if actor else 0)
        if flags & PF_INVISIBLE:
            return                                       # dropped Python-side (spec §5)
        if actor is not None and poly is not None:
            base_w, tu, tv, pan = _world_uv_frame(actor, poly)
            tex_index = textures.index_for(poly.texture)
        else:
            base_w, tu, tv, pan = (0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0)
            tex_index = -1                               # unknown owner → flat grey
        verts_flat = [c for v in world_verts for c in
                      (float(v[0]), float(v[1]), float(v[2]))]
        polys.append((verts_flat, list(base_w), list(tu), list(tv), list(pan), tex_index))

    for world_verts, i_actor, i_brush_poly in _node_polys(model):
        if 0 <= i_actor < len(join):
            name, source_polys = join[i_actor]
            if 0 <= i_brush_poly < len(source_polys):
                add_poly(world_verts, level.actors[name], source_polys[i_brush_poly])
            else:
                add_poly(world_verts, None, None)        # out-of-range poly → grey (§4.4)
        else:
            add_poly(world_verts, None, None)            # out-of-range owner → grey (§4.4)

    for world_verts, actor, poly in _mover_world_polys(level, index):
        add_poly(world_verts, actor, poly)

    return polys, textures.table


def render_shots(*, level, shots: list[Shot], out_dir: Path, index,
                 size: tuple[int, int] = DEFAULT_SIZE, fov: float = DEFAULT_FOV,
                 search_files=None) -> int:
    """Render every SHOT natively into `out_dir` (created if absent). Returns the count
    written. All actor refs resolve up front (all-or-nothing) BEFORE the build."""
    resolved: list[ResolvedShot] = []
    for shot in shots:                                   # all-or-nothing resolution
        try:
            resolved.append(resolve_pose(shot, lambda n: actor_aim_point(level, n)))
        except ValueError as e:
            raise NativePreviewError(str(e)) from None

    polys, textures = build_scene(level, search_files or [], index)

    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        probe = out_dir / ".uedctl-writable"
        probe.touch()
        probe.unlink()
    except OSError as e:
        raise NativePreviewError(f"cannot write to --out-dir {out_dir}: {e}") from None

    import uedctl_native
    from PIL import Image
    taken: set[str] = set()
    written = 0
    for i, rs in enumerate(resolved):
        fwd, right, up = camera_basis(rs.pitch, rs.yaw)
        camera = (tuple(float(c) for c in rs.eye), fwd, right, up, float(fov))
        rgb = uedctl_native.render_frame(polys, textures, camera,
                                         (int(size[0]), int(size[1])))
        img = Image.frombytes("RGB", (int(size[0]), int(size[1])), rgb)
        shot_src = shots[i]
        img.save(out_dir / shot_filename(shot_src, i, taken))
        written += 1
    return written

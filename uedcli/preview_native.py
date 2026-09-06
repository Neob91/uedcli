"""`level photo --native` — the offline draft backend (spec
board item `de-containerization-follow-on-spec-items`). Zero docker, zero editor, zero game:
the trunk is carved in-process by the faithful Rust CSG core (`uedcli_native.build_geometry_bspcsg`,
the incremental `bspBrushCSG` port that matches the editor's surviving surfaces), each
built surface is joined back to its SOURCE brush poly for texture/Pan/flags (the same
`i_actor`/`i_brush_poly` provenance `assemble._patch_surf_refs` consumes at materialize),
textures decode natively (`uedcli.utexture`), and `uedcli_native.render_frame` software-
rasterizes each SHOT pose to an RGB buffer that Pillow encodes as PNG.

Geometry marshals through the SHARED `brush_marshal._build_brush_input` (`_marshal_brush` is a
thin wrapper): a rotated/scaled/mirrored/sheared brush bakes its full linear map `L` into the CSG
world transform and renders (a degenerate/sheared-singular scale exits 2, named). Draft-validated
offline against `rotation.world_vertices`, not editor goldens. UV is SCALE-AWARE: the frame uses the
same full `L` so textures sit correctly on scaled/sheared/mirrored faces.

The per-surf UV frame is computed HERE, Python-side, from the source poly's authored
`Origin`/`TextureU`/`TextureV`/`Pan` (`base_w = Location + L·(Origin − PrePivot)`,
`axes_w = (L⁻¹)ᵀ·axes`, `L = PostScale·R·MainScale`) — the built surf's texture vectors are NEVER read
(the build synthesizes
default axes that ignore authored alignment, and Pan doesn't survive the build at all;
spec §5). The function is `texframe.world_uv_frame`, shared with the `brush poly align` verbs
(`polyalign.py`), so the two cannot disagree about where a texture sits.
Movers are out of world CSG, so they render directly as world-transformed
`extra_polys` at the base pose (`rotation.actor_linear` — the same math every measurement
verb uses)."""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from . import movers
from .normalize import is_builder_brush
from .preview_shots import ResolvedShot, Shot, resolve_pose, shot_filename
from .rotation import (actor_linear, actor_prepivot, deg_to_uu, euler_to_matrix_uu, matvec)
from .texframe import poly_flags_int, world_uv_frame
from .transform import DegenerateTransformError
from .utexture import TextureError, TextureResolver

PF_INVISIBLE = 0x1
PF_MASKED = 0x2                                       # alpha-test: palette-index-0 texels cut out

# The game's first-person default horizontal FOV: Engine.PlayerPawn defaultproperties
# `DesiredFOV=75.000000` / `DefaultFOV=75.000000` (DX install `Engine/Classes/PlayerPawn.uc:4940`,
# read 2026-07-16; DeusExPlayer does not override it). Spec §3 pins --fov's default to this.
DEFAULT_FOV = 75.0
DEFAULT_SIZE = (1280, 960)

_CSG_OPER = {"CSG_Add": 1, "CSG_Subtract": 2}

# The unresolvable-texture checkerboard (spec §4.5): magenta/black 8-px checks, 64².
_CHECKER_SIZE, _CHECKER_CELL = 64, 8


class NativePreviewError(Exception):
    """User-facing native-photo failure (→ stderr + exit 2, never a traceback)."""


# --------------------------------------------------------------------- brush inputs

def _marshal_brush(actor) -> tuple:
    """One CSG brush actor → the flat `BrushTuple` `build_geometry`/`build_geometry_bspcsg` take,
    via the shared `native.brush_marshal._build_brush_input` — the SINGLE transform-application home
    (scaled/mirrored/sheared brushes bake their linear map `L` into `rot`, unscaled take the exact
    rotation-only path). A degenerate/sheared scale the marshaller refuses surfaces as a named
    exit-2, never a traceback. The built model's surf tex axes are unused by preview (it derives UV
    frames from the join polys' authored axes separately), so passing the authored axes is harmless."""
    from .native.brush_marshal import BuildError, _build_brush_input
    try:
        return _build_brush_input(actor.name, actor)
    except BuildError as e:
        raise NativePreviewError(str(e)) from e


def _csg_oper_or_skip(name: str, raw: dict) -> int | None:
    """The `_CSG_OPER` code for a brush, or None (with a warning) for a non-world op — Intersect/
    Deintersect never appear in a trunk (live-editor verbs); anything unknown renders nothing."""
    oper = _CSG_OPER.get(raw.get("CsgOper", "CSG_Add"))
    if oper is None:
        print(f"WARNING: brush {name}: CsgOper {raw.get('CsgOper')!r} is not a world CSG op; "
              f"skipped", file=sys.stderr)
    return oper


def _brush_inputs(level, index) -> tuple[list, list[tuple[str, list]]]:
    """CSG brush actors (trunk order) → the `BrushTuple` flat buffers `build_geometry`
    takes, plus the `(actor_name, polys)` join list indexed by the surf `i_actor` tag.
    Movers and the transient builder brush are EXCLUDED from world CSG (movers render as
    extra_polys; the builder brush is editor scratch)."""
    brushes, join = [], []
    for name in level.order:
        actor = level.actors.get(name)
        if actor is None or actor.brush is None:
            continue
        if movers.is_mover(actor, index) or is_builder_brush(actor):
            continue
        if _csg_oper_or_skip(name, dict(actor.props)) is None:
            continue
        brushes.append(_marshal_brush(actor))
        join.append((name, actor.brush.polys))
    return brushes, join


# --------------------------------------------------------------------- geometry extract

def _node_polys(model) -> list[tuple[list[tuple[float, float, float]], int, int, int]]:
    """Each BSP node's polygon from its vert pool → (world verts, i_actor, i_brush_poly,
    poly_flags). `poly_flags` is the surf's OWN merged actor+poly `PolyFlags` (the Rust CSG core
    ORs the brush-level flags onto it — `native/brush_marshal.py`'s marshalling docstring) — single
    source for both preview renderers' backface-cull exemption, available even when the join below
    is out of range (a BSP node always has a surf; only i_actor/i_brush_poly can miss).
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
        out.append(([model.points[i] for i in idx], s.i_actor, s.i_brush_poly, s.poly_flags))
    return out


def _mover_actor_world_polys(actor) -> list[tuple[list, object, object]]:
    """One mover actor's brush polys world-transformed at the BASE pose
    (`Location + L·(v − PrePivot)`, `L = actor_linear` — the full scale/rotation map, so a scaled
    mover renders at its real size). A mirrored `L` (`det < 0`) reverses each ring — LOAD-BEARING
    now that both preview renderers backface-cull by winding: a mirrored mover without this flip
    would render inside-out (culled where it should show, and vice versa). Returns
    `(world_verts, actor, poly)` so the UV frame comes from the same authored fields.

    A degenerate (non-invertible) `MainScale`/`PostScale` exits 2 naming the actor, same as a
    world-CSG brush (`brush_marshal._build_brush_input`'s `reject_degenerate`) — movers skip world
    CSG entirely (`_in_world_csg`), so without this check here a degenerate mover would silently
    collapse to a zero-area poly instead of refusing."""
    from .rotation import actor_main_scale, actor_post_scale
    from .transform import flip_winding, reject_degenerate
    loc = tuple(float(c) for c in (actor.location or (0, 0, 0)))
    pp = tuple(float(c) for c in actor_prepivot(actor))
    L = actor_linear(actor)
    scaled = not (actor_main_scale(actor).is_identity() and actor_post_scale(actor).is_identity())
    if scaled:
        try:
            reject_degenerate(L, actor.name)
        except DegenerateTransformError as e:
            raise NativePreviewError(str(e)) from e
    flip = L is not None and flip_winding(L)
    out = []
    for poly in actor.brush.polys:
        world = []
        for v in poly.vertices:
            rel = (float(v[0]) - pp[0], float(v[1]) - pp[1], float(v[2]) - pp[2])
            if L is not None:
                rel = matvec(L, rel)
            world.append((loc[0] + rel[0], loc[1] + rel[1], loc[2] + rel[2]))
        if flip:
            world.reverse()
        out.append((world, actor, poly))
    return out


def _mover_world_polys(level, index) -> list[tuple[list, object, object]]:
    """Movers render directly (no BSP surfs): each brush poly world-transformed at the BASE
    pose. A draft preview without doors would be actively misleading (spec §5)."""
    out = []
    for name in level.order:
        actor = level.actors.get(name)
        if actor is None or actor.brush is None or not movers.is_mover(actor, index):
            continue
        out += _mover_actor_world_polys(actor)
    return out


# --------------------------------------------------------------------- textures

def _checkerboard() -> tuple[int, int, bytes, bytes]:
    """The unresolvable-ref placeholder: magenta/black checks — the miss is visible in the
    render itself (spec §4.5). Fully opaque (all-1 mask) so a PF_Masked face pointing at an
    unresolvable texture still shows the whole checkerboard rather than being cut to nothing."""
    data = bytearray()
    for y in range(_CHECKER_SIZE):
        for x in range(_CHECKER_SIZE):
            on = ((x // _CHECKER_CELL) + (y // _CHECKER_CELL)) % 2 == 0
            data += b"\xff\x00\xff" if on else b"\x00\x00\x00"
    return (_CHECKER_SIZE, _CHECKER_SIZE, bytes(data), b"\x01" * (_CHECKER_SIZE * _CHECKER_SIZE))


class _TextureTable:
    """Distinct texture refs → table indices; unresolvable refs share one checkerboard slot
    and warn ONCE per distinct ref (spec §4.5)."""

    def __init__(self, resolver: TextureResolver) -> None:
        self._resolver = resolver
        self.table: list[tuple[int, int, bytes, bytes]] = []
        self.bmasked: list[bool] = []                    # per-index: is the texture itself bMasked
        self._by_ref: dict[str, int] = {}
        self._checker_index: int | None = None

    def is_bmasked(self, idx: int) -> bool:
        """Does the texture at table `idx` carry `bMasked` (masks index-0 regardless of the surface
        `PF_Masked` flag)? `-1`/out-of-range (no texture) → False."""
        return 0 <= idx < len(self.bmasked) and self.bmasked[idx]

    def index_for(self, ref: str | None) -> int:
        if not ref:
            return -1                                    # no texture set → flat grey
        key = ref.casefold()
        if key in self._by_ref:
            return self._by_ref[key]
        got = self._resolver.resolve(ref)
        if isinstance(got, TextureError):
            # A whole-frame render degrades rather than refusing — one odd texture must not
            # stop a map preview. The named case goes into the warning so the user can tell a
            # typo (`unknown-package`) from a real decode gap (`unverified-format`) without
            # re-running anything. A per-ref request exits 2 instead; the decoder reports, the
            # caller disposes.
            print(f"WARNING: texture {ref!r} did not decode [{got.case}]: {got.detail}; "
                  f"rendering a checkerboard", file=sys.stderr)
            if self._checker_index is None:
                self._checker_index = len(self.table)
                self.table.append(_checkerboard())
                self.bmasked.append(False)
            idx = self._checker_index
        else:
            idx = len(self.table)
            self.table.append((got.width, got.height, got.rgb, got.mask))
            self.bmasked.append(bool(got.b_masked))
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
        import uedcli_native
    except ImportError:
        raise NativePreviewError(
            "the uedcli_native extension is not built — `level photo --native` needs it "
            "(build with `maturin develop`, or run bin/test once)") from None

    brushes, join = _brush_inputs(level, index)
    if not brushes:
        raise NativePreviewError("nothing to render: the trunk has no CSG brush actors")
    try:
        # FAITHFUL incremental `bspBrushCSG` core, same as `solve_world_surfaces` — it reproduces
        # the editor's surviving-surface set (Wanchai ratio ~1.01), where the coarse `build_geometry`
        # convex point-in-solid dropped ~69% of surfaces (board `native-preview-drops-large-geometry-
        # on-full`). Same `BrushTuple` input and `serialize_model`/`_node_polys` join path.
        built = uedcli_native.build_geometry_bspcsg(brushes)
        body = uedcli_native.serialize_model(built)
    except uedcli_native.BuildError as ex:
        raise NativePreviewError(f"native CSG build failed: {ex}") from ex
    from .native.umodel import parse_model_body
    model = parse_model_body(body, 0, len(body))

    textures = _TextureTable(TextureResolver(search_files))
    polys = []

    def add_poly(world_verts, actor, poly, surf_flags=None):
        # `surf_flags` (a CSG-solved surf's OWN `poly_flags`, always real even when the join below
        # is out of range) takes priority; a mover has no surf, so it falls back to deriving the
        # merged flags itself from its authored poly + actor PolyFlags. `poly` can be None (the
        # out-of-range-join grey filler) independently of `actor` being None, so the poly half of
        # the fallback must not assume `poly is not None` just because `actor is not None`.
        if surf_flags is not None:
            flags = surf_flags
        else:
            flags = ((poly.flags or 0) if poly is not None else 0) | (
                poly_flags_int(dict(actor.props)) if actor else 0)
        if flags & PF_INVISIBLE:
            return                                       # dropped Python-side (spec §5)
        if actor is not None and poly is not None:
            try:
                base_w, tu, tv, pan = world_uv_frame(actor, poly)
            except DegenerateTransformError as e:        # degenerate-scale mover/brush → exit 2 (spec §7)
                raise NativePreviewError(str(e)) from e
            tex_index = textures.index_for(poly.texture)
        else:
            base_w, tu, tv, pan = (0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0)
            tex_index = -1                               # unknown owner → flat grey
        verts_flat = [c for v in world_verts for c in
                      (float(v[0]), float(v[1]), float(v[2]))]
        # A face masks index-0 as see-through iff the surface `PF_Masked` flag is set OR the texture
        # itself is `bMasked` — the engine ORs a texture's PolyFlags onto every surface it's applied
        # to, so a masked texture masks with NO surface flag (owner-confirmed, `unrealed/quirks.md`
        # "a face draws index 0 as a hole iff poly.flags & PF_Masked OR its texture carries bMasked").
        # Matches `cli/rendering.py`'s `--faces` gate.
        masked = bool(flags & PF_MASKED) or textures.is_bmasked(tex_index)
        polys.append((verts_flat, list(base_w), list(tu), list(tv), list(pan), tex_index, masked,
                     flags))

    for world_verts, i_actor, i_brush_poly, poly_flags in _node_polys(model):
        if 0 <= i_actor < len(join):
            name, source_polys = join[i_actor]
            if 0 <= i_brush_poly < len(source_polys):
                add_poly(world_verts, level.actors[name], source_polys[i_brush_poly],
                         surf_flags=poly_flags)
            else:
                add_poly(world_verts, None, None, surf_flags=poly_flags)  # out-of-range poly (§4.4)
        else:
            add_poly(world_verts, None, None, surf_flags=poly_flags)     # out-of-range owner (§4.4)

    for world_verts, actor, poly in _mover_world_polys(level, index):
        add_poly(world_verts, actor, poly)

    return polys, textures.table


@dataclass(frozen=True)
class SolvedSurface:
    """One surviving world-space surface from the CSG solve. `actor`/`poly_index` identify the
    SOURCE brush poly (for texture/UV frame and the per-poly index decal), or both are None for a
    BSP node that joined to no source poly (renders flat grey). `world_verts` is the fragment's
    ring, already in world space — NO local→world transform is applied again downstream.
    `poly_flags` is the surf's OWN merged actor+poly `PolyFlags` (real even when actor/poly_index
    are None — a BSP node always has a surf) — the `actor diagram --faces textured` backface
    cull's `PF_TwoSided`/`PF_Portal` exemption reads this, single-sourced with `level photo
    --native`'s own cull."""
    actor: object | None
    poly_index: int | None
    world_verts: list
    poly_flags: int


@dataclass(frozen=True)
class SolvedWorld:
    """The CSG solve output `actor diagram --faces textured` draws: the surviving world surfaces
    plus the movers (excluded from world CSG, drawn as a separate overlay)."""
    world_surfaces: list  # list[SolvedSurface]
    mover_polys: list     # list[(world_verts, actor, poly)]


def solve_world_surfaces(actors, index, search_files=None) -> SolvedWorld:
    """Run the native CSG solve over an ad-hoc actor list (in the order given — the actor-set order
    IS the CSG evaluation order) through the FAITHFUL `build_geometry_bspcsg` core, and return the
    surviving world surfaces + the movers. This is the `actor diagram --faces textured` engine: the
    world is solved in isolation from a SOLID world, so an add not inside subtracted space leaves no
    surface. `index` is a `classindex.ClassIndex`; movers are excluded from world CSG (raising
    `classindex.ClassRefError` straight through on an unresolvable class). Raises `NativePreviewError`
    if the native extension is not built."""
    try:
        import uedcli_native
    except ImportError:
        raise NativePreviewError(
            "the uedcli_native extension is not built — `actor diagram --faces textured` needs it "
            "(build with `maturin develop`, or run bin/test once)") from None

    brushes, join = [], []
    for actor in actors:
        if actor.brush is None:
            continue
        if movers.is_mover(actor, index) or is_builder_brush(actor):
            continue
        if _csg_oper_or_skip(actor.name, dict(actor.props)) is None:
            continue
        brushes.append(_marshal_brush(actor))
        join.append(actor)

    world_surfaces: list[SolvedSurface] = []
    if brushes:
        try:
            built = uedcli_native.build_geometry_bspcsg(brushes)
            body = uedcli_native.serialize_model(built)
        except uedcli_native.BuildError as ex:
            raise NativePreviewError(f"native CSG solve failed: {ex}") from ex
        from .native.umodel import parse_model_body
        model = parse_model_body(body, 0, len(body))
        for world_verts, i_actor, i_brush_poly, poly_flags in _node_polys(model):
            if 0 <= i_actor < len(join):
                actor = join[i_actor]
                if 0 <= i_brush_poly < len(actor.brush.polys):
                    world_surfaces.append(SolvedSurface(actor, i_brush_poly, world_verts, poly_flags))
                else:                                    # out-of-range poly → grey (M5)
                    world_surfaces.append(SolvedSurface(None, None, world_verts, poly_flags))
            else:                                        # out-of-range owner → grey (M5)
                world_surfaces.append(SolvedSurface(None, None, world_verts, poly_flags))

    mover_polys = []
    for actor in actors:
        if actor.brush is not None and movers.is_mover(actor, index):
            mover_polys += _mover_actor_world_polys(actor)
    return SolvedWorld(world_surfaces=world_surfaces, mover_polys=mover_polys)


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
        probe = out_dir / ".uedcli-writable"
        probe.touch()
        probe.unlink()
    except OSError as e:
        raise NativePreviewError(f"cannot write to --out-dir {out_dir}: {e}") from None

    import uedcli_native
    from PIL import Image
    taken: set[str] = set()
    written = 0
    for i, rs in enumerate(resolved):
        fwd, right, up = camera_basis(rs.pitch, rs.yaw)
        camera = (tuple(float(c) for c in rs.eye), fwd, right, up, float(fov))
        rgb = uedcli_native.render_frame(polys, textures, camera,
                                         (int(size[0]), int(size[1])))
        img = Image.frombytes("RGB", (int(size[0]), int(size[1])), rgb)
        shot_src = shots[i]
        img.save(out_dir / shot_filename(shot_src, i, taken))
        written += 1
    return written

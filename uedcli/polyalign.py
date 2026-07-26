"""Continuous texture alignment across a set of faces — `brush poly align` + the `brush poly find`
producer that feeds it. Pure model-side texture-vector math (no editor), the offline analogue of
UnrealEd's `TEXTURE ALIGN`.

Design authority: dev/docs/decisions.md 2026-07-18 21:40 UTC (`poly align` v1 scope + face-selection
grammar) and specs/2026-07-18-poly-align.md (UV math + algorithms).

UV convention (verified from `render.rs`/`preview_native.py`, not memory):
    U = (Vertex − Origin) · TextureU + PanU     (V analogously with TextureV/PanV)
with the texel scale carried in `|TextureU|` (a UNIT TextureU = 1 texel per world unit). The frame is
WORLD-space: two faces are seamlessly aligned when a shared-edge world point maps to the same (U,V)
from either face. The stored `Origin`/`TextureU`/`TextureV` are per-BRUSH (the renderer maps them to
world via `base_w = Location + R·(Origin − PrePivot)`, `axes_w = R·axes`), so a shared world frame is
written into each face by INVERSE-TRANSFORMING it through that face's own brush rotation — NOT by
copying identical stored values (which would only align faces of one brush). The continuity offset
lives in the float `Origin`, so `Pan` stays the seed's integer.
"""
from __future__ import annotations

import math
from decimal import Decimal

from . import rotation
from .builders import _tex_basis
from .model import Actor, Level
from .preview import _face_normal
from .preview_native import _world_uv_frame
from .query import _poly_facing, resolve_actor_name
from .surface import parse_poly_selector, resolve_polys

# World-space tolerances (uu). Coplanarity/plane-offset and edge-coincidence checks run on world
# vertices at map scale, where sub-uu float noise is expected; these are generous relative to real
# geometry spacing (brushes snap to an integer grid).
_PARALLEL_EPS = 1e-3        # 1 − |n̂·n̂'| below this ⇒ same plane orientation
_PLANE_EPS = 0.5            # |Δ(n̂·p)| below this ⇒ same plane offset
_RADIAL_EPS = 0.1           # |n̂·axis| below this ⇒ face is a ring side (not a cap)
_AXIS_EPS = 0.9             # |edge_dir̂·axis| above this ⇒ edge runs along the cylinder axis
_WELD = 0.5                # world points within this coincide (a shared vertical edge)


class PolyAlignError(ValueError):
    """A user-facing alignment error (bad selection, non-coplanar set, non-ring set, …). A
    `ValueError` subclass so the dispatch layer's existing `except ValueError` prints it and exits
    non-zero — no traceback ever reaches the user (uedcli CLAUDE.md)."""


# --------------------------------------------------------------------- tiny vector helpers

def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _len(a):
    return math.sqrt(_dot(a, a))


def _scale(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)


def _neg(a):
    return (-a[0], -a[1], -a[2])


def _unit(a):
    m = _len(a)
    if m < 1e-12:
        raise PolyAlignError("degenerate (zero-length) vector")
    return _scale(a, 1.0 / m)


def _centroid(verts):
    n = len(verts)
    return tuple(sum(v[i] for v in verts) / n for i in range(3))


# --------------------------------------------------------------------- world geometry

def _world_verts(actor: Actor, poly) -> list[tuple[float, float, float]]:
    """A poly's vertices in WORLD space, using the SAME rotation-only transform as
    `preview_native._world_uv_frame` (`Location + R·(v − PrePivot)`), so the UV frame and the
    vertices it is measured against stay mutually consistent. (Scale is not applied — matching
    `_world_uv_frame`; a scaled textured brush is a known out-of-scope edge case, see the module
    doc + inbox follow-up.)"""
    R = rotation.actor_matrix(actor)
    pp = rotation.actor_prepivot(actor)
    loc = actor.location or (Decimal(0), Decimal(0), Decimal(0))
    lx, ly, lz = float(loc[0]), float(loc[1]), float(loc[2])
    out = []
    for v in poly.vertices:
        w = rotation.local_offset(R, pp, v)
        # float() each addend independently — `local_offset` may return Decimals (None-rotation fast
        # path) or floats, so coerce before adding to `loc` to avoid a Decimal+float TypeError.
        out.append((lx + float(w[0]), ly + float(w[1]), lz + float(w[2])))
    return out


def _world_normal(actor: Actor, poly, ref: str) -> tuple[float, float, float]:
    """Unit outward world normal of a poly; raises naming `ref` for a zero-area face."""
    wv = _world_verts(actor, poly)
    n = _face_normal(wv)
    if _len(n) < 1e-9:
        raise PolyAlignError(f"brush poly align: face {ref} is degenerate (zero area)")
    return _unit(n)


def _write_world_frame(actor: Actor, poly, base_w, tu_w, tv_w, pan) -> None:
    """Write a WORLD texture frame `(base_w, tu_w, tv_w, pan)` into `poly` by inverse-transforming
    through `actor`'s own rotation — the exact inverse of `_world_uv_frame`
    (`Origin = R⁻¹·(base_w − Location) + PrePivot`, `TextureU/V = R⁻¹·axes_w`). For an unrotated
    brush R is identity and this is a direct copy. `Pan` is written as the seed's integer."""
    R = rotation.actor_matrix(actor)
    pp = tuple(float(c) for c in rotation.actor_prepivot(actor))
    loc = tuple(float(c) for c in (actor.location or (0, 0, 0)))
    rel = _sub(base_w, loc)
    if R is None:
        origin, tu, tv = (rel[0] + pp[0], rel[1] + pp[1], rel[2] + pp[2]), tu_w, tv_w
    else:
        rinv = rotation.inverse(R)
        ro = rotation.matvec(rinv, rel)
        origin = (ro[0] + pp[0], ro[1] + pp[1], ro[2] + pp[2])
        tu = rotation.matvec(rinv, tu_w)
        tv = rotation.matvec(rinv, tv_w)
    poly.origin = (float(origin[0]), float(origin[1]), float(origin[2]))
    poly.texture_u = (float(tu[0]), float(tu[1]), float(tu[2]))
    poly.texture_v = (float(tv[0]), float(tv[1]), float(tv[2]))
    poly.pan = (int(round(pan[0])), int(round(pan[1])))


# --------------------------------------------------------------------- target resolution

def resolve_align_targets(level: Level, tokens: list[str]) -> list[tuple[str, int]]:
    """Resolve `tokens` to an ORDERED, deduped list of `(canonical_brush, poly_index)`.

    Each token is either a bare actor name (⇒ ALL of that brush's polys, in index order) or a
    `BRUSH:SELECTOR` token (`SELECTOR` = `all` or comma indices — what `brush poly find` emits).
    Order is preserved (first occurrence wins) — the ring seam is the first face. An empty `tokens`
    yields `[]` (the caller treats it as a clean no-op). Raises `PolyAlignError` naming the offender
    for an unknown brush or a bad selector."""
    ordered: list[tuple[str, int]] = []
    seen: set[tuple[str, int]] = set()
    for token in tokens:
        # parse_poly_selector / resolve_polys raise a PLAIN ValueError; re-raise as PolyAlignError
        # so a direct caller can catch this module's single exception type (dispatch catches either).
        try:
            if ":" in token:
                brush_name, selector = parse_poly_selector(token)
            else:
                brush_name, selector = token, "all"
        except ValueError as e:
            raise PolyAlignError(str(e))
        try:
            brush_name = resolve_actor_name(level, brush_name)
        except KeyError:
            raise PolyAlignError(f"unknown brush {brush_name!r}")
        actor = level.actors[brush_name]
        # resolve_polys returns a SET; re-order by the brush's own poly index so a repeated
        # `all`/index list is deterministic. (The set already validated the indices.)
        try:
            idxs = resolve_polys(selector, actor, brush_name=brush_name)
        except ValueError as e:
            raise PolyAlignError(str(e))
        for i in sorted(idxs):
            key = (brush_name, i)
            if key not in seen:
                seen.add(key)
                ordered.append(key)
    return ordered


# --------------------------------------------------------------------- brush poly find

def find_faces(actor: Actor, name: str, *, item: str | None = None,
               facing: str | None = None, texture: str | None = None) -> list[int]:
    """Poly indices of `actor` matching every supplied filter (AND across filters). `item` matches
    the builder ItemName (case-insensitive; e.g. `Side`); `facing` matches the snapped face facing
    (`+X`/`-X`/`+Y`/`-Y`/`+Z`/`-Z`/`slant`); `texture` matches the poly's texture ref
    (case-insensitive, exact or last-dot-component). Raises `PolyAlignError` naming `name` if it is
    not a brush."""
    if actor.brush is None:
        raise PolyAlignError(f"{name!r} is not a brush")
    want_item = item.casefold() if item else None
    want_tex = texture.casefold() if texture else None
    out: list[int] = []
    for idx, poly in enumerate(actor.brush.polys):
        if want_item is not None and (poly.item or "").casefold() != want_item:
            continue
        if facing is not None:
            wv = _world_verts(actor, poly)
            if len(wv) < 3 or _poly_facing(wv) != facing:
                continue
        if want_tex is not None:
            tex = (poly.texture or "").casefold()
            if tex != want_tex and tex.rsplit(".", 1)[-1] != want_tex:
                continue
        out.append(idx)
    return out


# --------------------------------------------------------------------- coplanar (--wall/--floor)

def _check_orientation(mode: str, normal, ref: str) -> None:
    """`--wall` requires a (mostly) VERTICAL face (dominant normal axis X or Y); `--floor` a
    (mostly) HORIZONTAL one (dominant normal axis Z). This orientation guard is the concrete,
    load-bearing difference between the two flags (adopt-seed itself is axis-agnostic): it catches
    aligning a floor with `--wall` (and vice-versa) instead of silently doing the wrong thing. A
    slanted face (neither) is out of v1 scope (turning runs deferred)."""
    dom = max(range(3), key=lambda i: abs(normal[i]))
    if mode == "wall" and dom == 2:
        raise PolyAlignError(
            f"brush poly align --wall: face {ref} is horizontal (normal ≈ ±Z) — use --floor")
    if mode == "floor" and dom != 2:
        raise PolyAlignError(
            f"brush poly align --floor: face {ref} is vertical (normal not ≈ ±Z) — use --wall")


def _coplanar_align(level: Level, targets, mode: str, fresh_frame: bool) -> list[str]:
    faces = [(bn, i, level.actors[bn], level.actors[bn].brush.polys[i]) for bn, i in targets]
    seed_bn, seed_i, seed_actor, seed_poly = faces[0]
    seed_ref = f"{seed_bn}:{seed_i}"
    n0 = _world_normal(seed_actor, seed_poly, seed_ref)
    d0 = _dot(n0, _world_verts(seed_actor, seed_poly)[0])
    _check_orientation(mode, n0, seed_ref)
    for bn, i, a, p in faces[1:]:
        ref = f"{bn}:{i}"
        nk = _world_normal(a, p, ref)
        # Require CO-ORIENTATION (signed dot ≈ +1), not just parallelism: a coplanar face that
        # points the OPPOSITE way would share the frame but render the texture MIRRORED, so reject
        # it rather than silently mirror (align each side of a double-sided wall separately).
        if _dot(n0, nk) < 1.0 - _PARALLEL_EPS:
            raise PolyAlignError(
                f"brush poly align --{mode}: face {ref} is not coplanar with {seed_ref} "
                f"(face normals point in different directions)")
        if abs(_dot(n0, _world_verts(a, p)[0]) - d0) > _PLANE_EPS:
            raise PolyAlignError(
                f"brush poly align --{mode}: face {ref} is not coplanar with {seed_ref} "
                f"(parallel but on a different plane)")
    if fresh_frame:
        tu_w, tv_w = _tex_basis(n0)                      # unit axes ⇒ 1 texel/world-unit
        base_w = _centroid(_world_verts(seed_actor, seed_poly))
        pan = (0, 0)
    else:
        base_w, tu_w, tv_w, pan = _world_uv_frame(seed_actor, seed_poly)
    for bn, i, a, p in faces:
        _write_world_frame(a, p, base_w, tu_w, tv_w, pan)
    return sorted({bn for bn, _ in targets})


# --------------------------------------------------------------------- ring (--ring)

def _vertical_edges(wv, axis):
    """The two axis-parallel edges of a side quad, each as `(bottom_pt, top_pt)` (ordered by axis
    projection)."""
    edges = []
    m = len(wv)
    for k in range(m):
        a, b = wv[k], wv[(k + 1) % m]
        d = _sub(b, a)
        length = _len(d)
        if length < 1e-9:
            continue
        if abs(_dot(_scale(d, 1.0 / length), axis)) > _AXIS_EPS:
            lo, hi = (a, b) if _dot(a, axis) <= _dot(b, axis) else (b, a)
            edges.append((lo, hi))
    return edges


def _edge_eq(e1, e2) -> bool:
    """Two vertical edges coincide iff their bottom endpoints do (each vertical edge sits at a
    unique tangential position around the ring, so the bottom point identifies it)."""
    return _len(_sub(e1[0], e2[0])) < _WELD


def _ring_align(level: Level, targets, fresh_frame: bool, fit_perimeter: bool) -> list[str]:
    brushes = {bn for bn, _ in targets}
    if len(brushes) != 1:
        raise PolyAlignError(
            "brush poly align --ring: all faces must belong to ONE cylinder brush, got: "
            + ", ".join(sorted(brushes)))
    if len(targets) < 2:
        raise PolyAlignError("brush poly align --ring: need at least 2 side faces to form a ring")
    brush_name = targets[0][0]
    actor = level.actors[brush_name]
    faces = [(i, actor.brush.polys[i]) for _, i in targets]
    wverts = [_world_verts(actor, p) for _, p in faces]
    normals = [_world_normal(actor, p, f"{brush_name}:{i}") for i, p in faces]

    # Cylinder axis: perpendicular to every (radial) side-face normal ⇒ the cross of two
    # non-parallel normals. Oriented +Z-ish for determinism.
    axis = None
    for k in range(1, len(normals)):
        c = _cross(normals[0], normals[k])
        if _len(c) > 1e-6:
            axis = _unit(c)
            break
    if axis is None:
        raise PolyAlignError(
            "brush poly align --ring: all faces are parallel — not a ring (a single flat run is "
            "--wall/--floor, not --ring)")
    if _dot(axis, (0, 0, 1)) < 0 or (abs(_dot(axis, (0, 0, 1))) < 1e-9 and _dot(axis, (0, 1, 0)) < 0):
        axis = _neg(axis)
    for (i, _), n in zip(faces, normals):
        if abs(_dot(n, axis)) > _RADIAL_EPS:
            raise PolyAlignError(
                f"brush poly align --ring: face {brush_name}:{i} is not a ring side face (its "
                f"normal is not perpendicular to the cylinder axis) — exclude caps, e.g. "
                f"`brush poly find {brush_name} --item Side | brush poly align --ring -`")

    # Texel densities (adopt the seed's scale, resolving which stored axis is tangential vs axial by
    # PROJECTION so it is robust to the builder's frame having U along the axis). Fresh ⇒ 1/1.
    if fresh_frame:
        density_u = density_v = 1.0
        pan = (0, 0)
        tv_w = axis
    else:
        base0, tu0, tv0, pan = _world_uv_frame(actor, faces[0][1])
        t_hat = _unit(_cross(axis, normals[0]))          # seed's in-plane tangent (⊥ axis)
        density_u = math.hypot(_dot(tu0, t_hat), _dot(tv0, t_hat)) or 1.0
        density_v = math.hypot(_dot(tu0, axis), _dot(tv0, axis)) or 1.0
        tv_w = _scale(axis, density_v)

    # Order faces into a connected strip in INPUT order and accumulate the running chord.
    edges = [_vertical_edges(wv, axis) for wv in wverts]
    for (i, _), e in zip(faces, edges):
        if len(e) != 2:
            raise PolyAlignError(
                f"brush poly align --ring: face {brush_name}:{i} is not a quad side face "
                f"(found {len(e)} axis-parallel edge(s), expected 2)")
    steps = []                                           # (poly, start_edge, end_edge, chord, cum)
    prev_end = None
    cum = 0.0
    for pos, (i, poly) in enumerate(faces):
        e = edges[pos]
        if pos == 0:
            nxt = edges[1]
            if any(_edge_eq(e[0], oe) for oe in nxt):
                start, end = e[1], e[0]
            elif any(_edge_eq(e[1], oe) for oe in nxt):
                start, end = e[0], e[1]
            else:
                raise PolyAlignError(
                    f"brush poly align --ring: face {brush_name}:{i} shares no vertical edge with "
                    f"the next face — the faces are not a connected ring in input order")
        else:
            if _edge_eq(e[0], prev_end):
                start, end = e[0], e[1]
            elif _edge_eq(e[1], prev_end):
                start, end = e[1], e[0]
            else:
                raise PolyAlignError(
                    f"brush poly align --ring: face {brush_name}:{i} shares no vertical edge with "
                    f"the previous face — the faces are not a connected ring in input order")
        chord = _len(_sub(end[0], start[0]))
        if chord < 1e-9:
            raise PolyAlignError(
                f"brush poly align --ring: face {brush_name}:{i} has zero tangential width")
        steps.append((poly, start, end, chord, cum))
        cum += chord
        prev_end = end
    total_chord = cum

    # --fit-perimeter: snap the around-ring density so the TOTAL U advance is an integer number of
    # texels (an exact meet at the closing seam). Default = leave the seam (honest, matches UnrealEd).
    if fit_perimeter:
        target = max(1, round(total_chord * density_u))
        density_u = target / total_chord

    pan_u = float(pan[0])
    for poly, start, end, chord, cum_before in steps:
        t_hat = _unit(_sub(end[0], start[0]))            # this facet's tangent, start→end (+U)
        tu_w = _scale(t_hat, density_u)
        u_start = pan_u + cum_before * density_u
        # base_w so U(start) = u_start with PanU = pan[0]; the offset lives in the (float) Origin.
        base_w = _sub(start[0], _scale(tu_w, (u_start - pan_u) / _dot(tu_w, tu_w)))
        _write_world_frame(actor, poly, base_w, tu_w, tv_w, pan)
    return [brush_name]


# --------------------------------------------------------------------- entry point

def align(level: Level, tokens: list[str], mode: str, *, fresh_frame: bool = False,
          fit_perimeter: bool = False) -> list[str]:
    """Align the texture frames of the faces named by `tokens` (bare names / `BRUSH:SELECTOR`) in
    `mode` (`wall`|`floor`|`ring`). Returns the sorted touched brush names. `fit_perimeter` is
    ring-only (the CLI enforces it). Empty `tokens` ⇒ `[]` (a clean no-op). Raises `PolyAlignError`
    (a `ValueError`) naming the offender for every failure path."""
    if fit_perimeter and mode != "ring":
        raise PolyAlignError("brush poly align: --fit-perimeter applies only to --ring")
    targets = resolve_align_targets(level, tokens)
    if not targets:
        return []
    if mode == "ring":
        return _ring_align(level, targets, fresh_frame, fit_perimeter)
    if mode in ("wall", "floor"):
        return _coplanar_align(level, targets, mode, fresh_frame)
    raise PolyAlignError(f"brush poly align: unknown mode {mode!r}")


def face_uv(actor: Actor, poly, world_point) -> tuple[float, float]:
    """The (U,V) texel coordinate a world point maps to under `poly`'s stored frame, via the canonical
    convention `U=(P−Origin)·TextureU+PanU`. Reuses `_world_uv_frame` (the renderer's frame), so a
    test can assert seam continuity by comparing this across the two faces sharing an edge."""
    base_w, tu_w, tv_w, pan = _world_uv_frame(actor, poly)
    p = tuple(float(c) for c in world_point)
    rel = _sub(p, base_w)
    return (_dot(rel, tu_w) + pan[0], _dot(rel, tv_w) + pan[1])

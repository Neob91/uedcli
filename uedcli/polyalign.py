"""Continuous texture alignment across a set of faces — `brush poly align` + the `brush poly find`
producer that feeds it. Pure model-side texture-vector math (no editor).

`wall`/`floor` REPRODUCE the editor's `POLY TEXALIGN` projection family (`FLOOR`/`WALLX`/`WALLY`),
measured 2026-07-26 (`dev/docs/unrealed/texalign.md`): a world-axis-anchored frame at `|proj|`
density, polarity-blind by construction. `run` (cylinder wrap) has no editor analogue and is uedcli's
own. UnrealEd's verb needs a built BSP and acts on the CSG surface normal; this module is model-side
and uses the brush polygon's normal — harmless for `wall`/`floor` because the whole family is
invariant under `n → −n`.

Design authority: dev/docs/direction/conventions.md 2026-07-18 21:40 UTC (`poly align` v1 scope + face-selection
grammar) and board item `poly-align-brush-poly-find-built` (UV math + algorithms).

UV convention (verified from `render.rs`/`texframe.py`, not memory):
    U = (Vertex − Origin) · TextureU + PanU     (V analogously with TextureV/PanV)
with the texel scale carried in `|TextureU|` (a UNIT TextureU = 1 texel per world unit). The frame is
WORLD-space: two faces are seamlessly aligned when a shared-edge world point maps to the same (U,V)
from either face. The stored `Origin`/`TextureU`/`TextureV` are per-BRUSH (the renderer maps them to
world via `base_w = Location + L·(Origin − PrePivot)`, `axes_w = (L⁻¹)ᵀ·axes`, `L = PostScale·R·
MainScale`), so a shared world frame is written into each face by INVERSE-TRANSFORMING it through that
face's own brush transform — NOT by copying identical stored values (which would only align faces of
one brush). The continuity offset lives in the float `Origin`, so `Pan` stays the seed's integer.
Scale/sheer are honoured (a scaled brush aligns correctly), matching `texframe.world_uv_frame`.
"""
from __future__ import annotations

import math
import sys
from decimal import Decimal
from typing import Callable

from . import rotation
from .facing_spec import FacingSpec, match_facing
from .model import Actor, Level
from .query import resolve_actor_name, visible_normal
from .surface import parse_poly_selector, resolve_polys
from .texframe import newell, world_uv_frame

# World-space tolerance (uu). Edge-coincidence checks run on world vertices at map scale, where
# sub-uu float noise is expected; this is generous relative to real geometry spacing (brushes snap
# to an integer grid).
_WELD = 0.5                # world points within this coincide (a shared edge)


class PolyAlignError(ValueError):
    """A user-facing alignment error (bad selection, a forking/disconnected run, a guard failure, …). A
    `ValueError` subclass so the dispatch layer's existing `except ValueError` prints it and exits
    non-zero — no traceback ever reaches the user (uedcli CLAUDE.md)."""


def _uv_frame_guarded(actor, poly):
    """`texframe.world_uv_frame`, translating a degenerate-scale `L` (a zero/sub-epsilon scale axis
    makes the covariant axis map non-invertible) into `PolyAlignError` naming the brush — never a bare
    `ZeroDivisionError`. (The CSG world path guards this in `brush_marshal`.)"""
    from .transform import DegenerateTransformError
    try:
        return world_uv_frame(actor, poly)
    except DegenerateTransformError as e:
        raise PolyAlignError(str(e)) from e


# --------------------------------------------------------------------- tiny vector helpers

def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


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


# --------------------------------------------------------------------- world geometry

def _world_verts(actor: Actor, poly) -> list[tuple[float, float, float]]:
    """A poly's vertices in WORLD space, using the SAME full linear map `L = PostScale·R·MainScale`
    as `texframe.world_uv_frame` (`Location + L·(v − PrePivot)`), so the UV frame and the vertices it
    is measured against stay mutually consistent — including on a scaled/sheared brush. `L=None`
    (unscaled+unrotated) keeps the byte-identical fast path."""
    L = rotation.actor_linear(actor)
    pp = rotation.actor_prepivot(actor)
    loc = actor.location or (Decimal(0), Decimal(0), Decimal(0))
    lx, ly, lz = float(loc[0]), float(loc[1]), float(loc[2])
    out = []
    for v in poly.vertices:
        w = rotation.local_offset(L, pp, v)
        # float() each addend independently — `local_offset` may return Decimals (None-rotation fast
        # path) or floats, so coerce before adding to `loc` to avoid a Decimal+float TypeError.
        out.append((lx + float(w[0]), ly + float(w[1]), lz + float(w[2])))
    return out


def _world_normal(actor: Actor, poly, ref: str) -> tuple[float, float, float]:
    """Unit outward world normal of a poly; raises naming `ref` for a zero-area face."""
    wv = _world_verts(actor, poly)
    n = newell(wv)
    if _len(n) < 1e-9:
        raise PolyAlignError(f"brush poly align: face {ref} is degenerate (zero area)")
    return _unit(n)


def _write_world_frame(actor: Actor, poly, base_w, tu_w, tv_w, pan) -> None:
    """Write a WORLD texture frame `(base_w, tu_w, tv_w, pan)` into `poly` by inverse-transforming
    through `actor`'s own linear map `L = PostScale·R·MainScale` — the exact inverse of
    `world_uv_frame`: the POINT `Origin = L⁻¹·(base_w − Location) + PrePivot`, and the COVECTORS
    `TextureU/V = Lᵀ·axes_w` (`Lᵀ` inverts the forward `(L⁻¹)ᵀ`). Unscaled+unrotated (L=None) is a
    direct copy; a pure rotation keeps the old `R⁻¹`-for-both path byte-for-byte (`Rᵀ = R⁻¹`).
    `Pan` is written as the seed's integer."""
    L = rotation.actor_linear(actor)
    scaled = not (rotation.actor_main_scale(actor).is_identity()
                  and rotation.actor_post_scale(actor).is_identity())
    if scaled:                                       # degenerate L → the inverse() below crashes; exit 2
        from .transform import DegenerateTransformError, reject_degenerate
        try:
            reject_degenerate(L, getattr(actor, "name", "?"))
        except DegenerateTransformError as e:
            raise PolyAlignError(str(e)) from e
    pp = tuple(float(c) for c in rotation.actor_prepivot(actor))
    loc = tuple(float(c) for c in (actor.location or (0, 0, 0)))
    rel = _sub(base_w, loc)
    if L is None:
        origin, tu, tv = (rel[0] + pp[0], rel[1] + pp[1], rel[2] + pp[2]), tu_w, tv_w
    elif not scaled:
        rinv = rotation.inverse(L)                   # L == R; `R⁻¹` for point AND axes (old path)
        ro = rotation.matvec(rinv, rel)
        origin = (ro[0] + pp[0], ro[1] + pp[1], ro[2] + pp[2])
        tu = rotation.matvec(rinv, tu_w)
        tv = rotation.matvec(rinv, tv_w)
    else:
        ro = rotation.matvec(rotation.inverse(L), rel)   # POINT → L⁻¹
        origin = (ro[0] + pp[0], ro[1] + pp[1], ro[2] + pp[2])
        lt = rotation.transpose(L)                       # COVECTORS → Lᵀ (inverse of (L⁻¹)ᵀ)
        tu = rotation.matvec(lt, tu_w)
        tv = rotation.matvec(lt, tv_w)
    poly.origin = (float(origin[0]), float(origin[1]), float(origin[2]))
    poly.texture_u = (float(tu[0]), float(tu[1]), float(tu[2]))
    poly.texture_v = (float(tv[0]), float(tv[1]), float(tv[2]))
    poly.pan = (int(round(pan[0])), int(round(pan[1])))


# --------------------------------------------------------------------- target resolution

def resolve_align_targets(level: Level, tokens: list[str]) -> list[tuple[str, int]]:
    """Resolve `tokens` to an ORDERED, deduped list of `(canonical_brush, poly_index)`.

    Each token is either a bare actor name (⇒ ALL of that brush's polys, in index order) or a
    `BRUSH:SELECTOR` token (`SELECTOR` = `all` or comma indices — what `brush poly find` emits).
    Order is preserved (first occurrence wins), but `run` derives its own walk order from geometry and
    poly index, so the token order has no bearing on its result. An empty `tokens` yields `[]` (the
    caller treats it as a clean no-op). Raises `PolyAlignError` naming the offender for an unknown
    brush or a bad selector."""
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
               facing: FacingSpec | None = None, texture: str | None = None) -> list[int]:
    """Poly indices of `actor` matching every supplied filter (AND across filters). `item` matches
    the builder ItemName (case-insensitive; e.g. `Side`); `facing` (a parsed `FacingSpec`) matches
    the face's VISIBLE unit normal (`query.visible_normal` — polarity-resolved for subtract brushes);
    `texture` matches the poly's texture ref (case-insensitive, exact or last-dot-component). Raises
    `PolyAlignError` naming `name` if it is not a brush."""
    if actor.brush is None:
        raise PolyAlignError(f"{name!r} is not a brush")
    want_item = item.casefold() if item else None
    want_tex = texture.casefold() if texture else None
    out: list[int] = []
    for idx, poly in enumerate(actor.brush.polys):
        if want_item is not None and (poly.item or "").casefold() != want_item:
            continue
        if facing is not None:
            if len(poly.vertices) < 3 or not match_facing(visible_normal(actor, poly), facing):
                continue
        if want_tex is not None:
            tex = (poly.texture or "").casefold()
            if tex != want_tex and tex.rsplit(".", 1)[-1] != want_tex:
                continue
        out.append(idx)
    return out


# --------------------------------------------------------------------- world-space projection (wall/floor)

_PROJ_GUARD = 0.05   # |N.A| must EXCEED this to project down world axis A (editor's .rdata constant)
_AXIS_NAME = "XYZ"
_WORLD_AXES = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))


def _proj(axis_vec, n):
    """World axis `axis_vec` projected into the plane of unit normal `n`, deliberately NOT
    renormalised: `proj(B) = B − n(n·B)`, so `|proj(B)| = √(1 − (n·B)²) ≤ 1` — the texel density the
    editor's projection modes write. Invariant under `n → −n` (both sign flips cancel), which is why
    `wall`/`floor` produce a byte-identical frame from a subtractive brush's reversed normal."""
    d = _dot(n, axis_vec)
    return (axis_vec[0] - n[0] * d, axis_vec[1] - n[1] * d, axis_vec[2] - n[2] * d)


# axis index -> (U_src, V_src): the editor's FLOOR/WALLX/WALLY table (`dev/docs/unrealed/texalign.md`),
# COPIED, not derived from a cyclic rule — both wall rows put V on Ẑ. Shared by `wall`/`floor`
# (§2.3, axis chosen from `mode`) and `one-tile` (§2.6, axis chosen as the face's own argmax).
_AXIS_UV = {2: (_WORLD_AXES[0], _WORLD_AXES[1]),          # A = Z (floor): U ← X̂, V ← Ŷ
            0: (_WORLD_AXES[1], _WORLD_AXES[2]),          # A = X (wall):  U ← Ŷ, V ← Ẑ
            1: (_WORLD_AXES[0], _WORLD_AXES[2])}          # A = Y (wall):  U ← X̂, V ← Ẑ


def _projection_axis(mode: str, n) -> tuple[int, tuple, tuple]:
    """The world axis this face is projected DOWN (its index) plus the world axes its U and V come
    from (`_AXIS_UV`). `floor` drops Z; `wall` derives X vs Y from the axis the face faces MORE
    (`|N.X| ≥ |N.Y|`), ties resolving to X (the lowest axis index, matching `builders._tex_basis`)."""
    axis_idx = 2 if mode == "floor" else (0 if abs(n[0]) >= abs(n[1]) else 1)
    u_src, v_src = _AXIS_UV[axis_idx]
    return axis_idx, u_src, v_src


def _projected_align(level: Level, targets, mode: str) -> list[str]:
    """The editor's projection family (`FLOOR`/`WALLX`/`WALLY`): each face gets a world-space frame —
    the texture anchored where the face's plane crosses the projection axis, its U/V the other two
    world axes projected into the face and negated, `Pan` zeroed. A frame is a pure function of the
    face's own plane and the world axes: there is no seed and no set-level relationship, so a set is
    simply a batch (two invocations over subsets of one plane agree byte-for-byte). A face too near
    edge-on to its projection axis (`|N.A| ≤ 0.05`) is collected and the whole batch exits 2 — nothing
    is written."""
    faces = [(bn, i, level.actors[bn], level.actors[bn].brush.polys[i]) for bn, i in targets]
    prepared, failures = [], []
    for bn, i, a, p in faces:                             # pre-pass: all-or-nothing (conventions.md)
        ref = f"{bn}:{i}"
        n = _world_normal(a, p, ref)                     # raises naming a zero-area face
        axis_idx, u_src, v_src = _projection_axis(mode, n)
        if abs(n[axis_idx]) <= _PROJ_GUARD:
            failures.append((ref, n, axis_idx))
        else:
            prepared.append((a, p, n, axis_idx, u_src, v_src))
    if failures:
        raise PolyAlignError(_projection_guard_message(mode, failures))
    for a, p, n, axis_idx, u_src, v_src in prepared:
        d = _dot(n, _world_verts(a, p)[0])               # plane offset (any point of the plane)
        origin = [0.0, 0.0, 0.0]
        origin[axis_idx] = d / n[axis_idx]               # where the plane crosses the projection axis
        _write_world_frame(a, p, tuple(origin), _neg(_proj(u_src, n)), _neg(_proj(v_src, n)), (0, 0))
    return sorted({bn for bn, _ in targets})


def _projection_guard_message(mode: str, failures) -> str:
    """Name EVERY guard-failing face with its selector, normal component and projection axis, plus
    why the 0.05 floor exists — a hard exit 2 rather than the editor's silent skip
    (`direction/conventions.md` 'No silent half-answers'). The escape is `brush poly find --facing`
    upstream."""
    listed = ", ".join(f"`{ref}` (|N.{_AXIS_NAME[ax]}| = {abs(n[ax]):.3f})" for ref, n, ax in failures)
    near = "vertical" if mode == "floor" else "horizontal"
    return (f"brush poly align {mode}: {len(failures)} face(s) too close to {near} for a "
            f"{'Z' if mode == 'floor' else 'X/Y'} projection — {listed}; the 0.05 floor exists "
            f"because a texture projected down an axis it is nearly parallel to is stretched past "
            f"20× and anchored thousands of uu away. Filter the set first, e.g. "
            f"`brush poly find <brush> --facing {'floor' if mode == 'floor' else 'wall'} | "
            f"brush poly align {mode} -`")


# --------------------------------------------------------------------- fit-to-poly (one-tile)

def _one_tile_align(level: Level, targets, resolve_dims) -> list[str]:
    """`align one-tile`: fit exactly one texture tile to each face, independently — no shared
    frame, no orientation guard (the projection axis is always the world axis the face faces
    MOST over all three, so `|N.A| ≥ 1/√3` always and the wall/floor guard can never fire here).
    §2.6: a uedcli invention (UnrealEd's own `ONETILE` is a no-op), reusing the wall/floor
    projection table but ORTHOGONALISING it (Gram-Schmidt of U against V) — the raw table's two
    projected axes are not perpendicular off-axis, which both shears the image and moves the
    fitted extent's minimum corner off a vertex."""
    faces = [(bn, i, level.actors[bn], level.actors[bn].brush.polys[i]) for bn, i in targets]

    # Batch pre-pass (conventions.md "all-or-nothing"): every face with no bound texture, and
    # every DISTINCT ref that fails to resolve, named together before anything is written.
    missing = [f"{bn}:{i}" for bn, i, a, p in faces if p.texture is None]
    dims: dict[str, tuple[int, int]] = {}
    tried: set[str] = set()
    bad_refs: list[str] = []
    for _, _, _, p in faces:
        if p.texture is None:
            continue
        key = p.texture.casefold()
        if key in tried:
            continue
        tried.add(key)
        try:
            dims[key] = resolve_dims(p.texture)
        except ValueError as e:
            bad_refs.append(str(e))
    if missing or bad_refs:
        parts = []
        if missing:
            parts.append(f"{len(missing)} face(s) carry no texture — {', '.join(missing)}")
        if bad_refs:
            parts.append("; ".join(bad_refs))
        raise PolyAlignError(f"brush poly align one-tile: {'; '.join(parts)}")

    prepared = []
    for bn, i, a, p in faces:
        ref = f"{bn}:{i}"
        n = _world_normal(a, p, ref)                      # raises naming a zero-area face
        axis_idx = max(range(3), key=lambda k: abs(n[k]))  # over ALL three axes; first-wins ⇒ lowest
        u_src, v_src = _AXIS_UV[axis_idx]
        v_hat = _unit(_neg(_proj(v_src, n)))                # kept EXACTLY as the table gives it
        raw_u = _neg(_proj(u_src, n))
        u_hat = _unit(_sub(raw_u, _scale(v_hat, _dot(raw_u, v_hat))))   # Gram-Schmidt: square U to V

        wv = _world_verts(a, p)
        pu = [_dot(v, u_hat) for v in wv]
        pv = [_dot(v, v_hat) for v in wv]
        extent_u, extent_v = max(pu) - min(pu), max(pv) - min(pv)
        if extent_u < 1e-6 or extent_v < 1e-6:
            # Defensive only, not reachable by a real face: a positive-area planar polygon has
            # nonzero extent along ANY in-plane direction, so `_world_normal`'s zero-area check
            # above already catches every genuine degenerate case. This guards the division below.
            raise PolyAlignError(
                f"brush poly align one-tile: face {ref} has zero extent along its own fit "
                f"axis (a degenerate projection) — {extent_u:.4g} x {extent_v:.4g}")

        w, h = dims[p.texture.casefold()]
        tu_w, tv_w = _scale(u_hat, w / extent_u), _scale(v_hat, h / extent_v)
        p0 = wv[0]
        # Origin = P0 minus its own Û/V̂ components (its component along n̂ survives), plus the
        # extremal corner along Û/V̂ — the world point whose Û/V̂ projections are exactly
        # (min(pu), min(pv)), so that corner maps to texel (0,0). Exact only because û ⊥ v̂ ⊥ n̂.
        origin = _add(_sub(p0, _add(_scale(u_hat, _dot(p0, u_hat)), _scale(v_hat, _dot(p0, v_hat)))),
                      _add(_scale(u_hat, min(pu)), _scale(v_hat, min(pv))))
        prepared.append((a, p, origin, tu_w, tv_w))

    for a, p, origin, tu_w, tv_w in prepared:
        _write_world_frame(a, p, origin, tu_w, tv_w, (0, 0))
    return sorted({bn for bn, _ in targets})


# --------------------------------------------------------------------- connected run (run)

def _face_edges(wv):
    """The ring of a face's edges as `(local_index, (pa, pb))`."""
    m = len(wv)
    return [(k, (wv[k], wv[(k + 1) % m])) for k in range(m)]


def _edges_coincide(e_a, e_b) -> bool:
    """Two edges coincide when their endpoints match within `_WELD`, matched UNORDERED (the two faces
    wind a shared edge opposite ways). A DISTANCE test, not bucket rounding — bucket keys mis-weld a
    pair straddling a boundary (a real risk on a revolve's off-grid, `emit.clean`-snapped verts)."""
    (a0, a1), (b0, b1) = e_a, e_b
    return ((_len(_sub(a0, b0)) < _WELD and _len(_sub(a1, b1)) < _WELD) or
            (_len(_sub(a0, b1)) < _WELD and _len(_sub(a1, b0)) < _WELD))


def _mid(edge):
    (a, b) = edge
    return ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0, (a[2] + b[2]) / 2.0)


def _run_adjacency(data: dict):
    """Shared-edge adjacency over `data` (keyed by `(brush, idx)` → (world_verts, normal)). Returns
    `(adjacency, shared_local)`: `adjacency[k]` = set of neighbour keys; `shared_local[k][j]` = the
    local edge index of `k` shared with `j`. Enforces §2.4.1 steps 2-3: a face PAIR sharing more
    than one edge, or an EDGE shared by more than two faces, exits 2 — either makes the chord
    ambiguous. Brush-identity-blind: a shared edge is a world-point coincidence, same test whether
    both faces are on one brush or two."""
    idxs = list(data)
    fe = {k: _face_edges(data[k][0]) for k in idxs}
    adjacency = {k: set() for k in idxs}
    shared_local: dict = {k: {} for k in idxs}
    for ai in range(len(idxs)):
        for bi in range(ai + 1, len(idxs)):
            a, b = idxs[ai], idxs[bi]
            shared = [(ka, kb) for ka, ea in fe[a] for kb, eb in fe[b] if _edges_coincide(ea, eb)]
            if len(shared) > 1:
                raise PolyAlignError(
                    f"brush poly align run: faces {a[0]}:{a[1]} and {b[0]}:{b[1]} share "
                    f"{len(shared)} edges — the run chord is ambiguous, not a simple strip")
            if shared:
                ka, kb = shared[0]
                adjacency[a].add(b)
                adjacency[b].add(a)
                shared_local[a][b] = ka
                shared_local[b][a] = kb
    over = []
    for k in idxs:                                       # one local edge of k shared with ≥2 faces
        by_edge: dict = {}
        for nbr, ka in shared_local[k].items():
            by_edge.setdefault(ka, []).append(nbr)
        over += [(k, nbrs) for nbrs in by_edge.values() if len(nbrs) >= 2]
    if over:
        listed = "; ".join(f"{k[0]}:{k[1]} with "
                           + ", ".join(f"{n[0]}:{n[1]}" for n in sorted(nbrs)) for k, nbrs in over)
        raise PolyAlignError(
            f"brush poly align run: an edge is shared by more than two faces ({listed}) — the set "
            f"is not a surface strip")
    return adjacency, shared_local


def _across_root_sign(c):
    """ĉ points along the NEGATIVE side of its own largest-magnitude component (ties → lowest axis
    index). `c` is a unit vector, so its largest component is ≥ 1/√3 — a strict test, no epsilon."""
    k = max(range(3), key=lambda i: abs(c[i]))          # first-wins ⇒ lowest index on a tie
    return c if c[k] < 0 else _neg(c)


def _run_prewalk(level: Level, targets):
    """§2.4.1 steps 1-8: validate the set and DERIVE the ordered walk (root and direction from the
    `(brush, poly)` key alone — spans any number of brushes). Returns `(data, walk, closed)` where
    `walk` is `[((bn, idx), entry_edge, exit_edge), …]` in walk order, each edge a `(pa, pb)`
    world-point pair (a terminal face's missing seam is its opposite quad edge). Raises
    `PolyAlignError` naming the offender for every failure path."""
    # step 1 — ≥ 2 faces (brush count is unconstrained; step 5's connectivity check is what actually
    # ensures the set forms one run, whether that's one brush or several)
    if len(targets) < 2:
        raise PolyAlignError("brush poly align run: need at least 2 faces to form a run")

    # step 2 — world geometry + unit normal; every zero-area face named (batch)
    data: dict = {}
    degenerate = []
    for bn, i in targets:
        actor = level.actors[bn]
        wv = _world_verts(actor, actor.brush.polys[i])
        n = newell(wv)
        if _len(n) < 1e-9:
            degenerate.append((bn, i))
        else:
            data[(bn, i)] = (wv, _unit(n))
    if degenerate:
        raise PolyAlignError("brush poly align run: zero-area face(s) — "
                             + ", ".join(f"{bn}:{i}" for bn, i in degenerate))

    adjacency, shared_local = _run_adjacency(data)   # steps 2-3

    # step 4 — BRANCH CHECK: a run cannot fork (degree ≥ 3). Always carries the --item Side hint.
    branched = sorted(k for k in data if len(adjacency[k]) >= 3)
    if branched:
        listed = ", ".join(f"{bn}:{i} ({len(adjacency[(bn, i)])} neighbours)" for bn, i in branched)
        names = " ".join(sorted({bn for bn, _ in branched}))
        raise PolyAlignError(
            f"brush poly align run: {listed} — a run cannot branch; align each arm as its own set. "
            f"If these are a cylinder's caps, exclude them: "
            f"`brush poly find {names} --item Side | brush poly align run -`")

    # step 5 — CONNECTIVITY: one component (after step 4, max degree ≤ 2 ⇒ a simple path or cycle)
    seen: set = set()
    stack = [min(data)]
    while stack:
        cur = stack.pop()
        if cur not in seen:
            seen.add(cur)
            stack.extend(adjacency[cur] - seen)
    if seen != set(data):
        others = sorted(set(data) - seen)
        raise PolyAlignError(
            "brush poly align run: the faces are not one connected run — "
            + ", ".join(f"{bn}:{i}" for bn, i in others) + " form a separate component")

    # step 6 — NON-QUAD (after branch, so a cylinder+cap still shows the branch hint, not this)
    nonquad = sorted(k for k in data if len(data[k][0]) != 4)
    if nonquad:
        raise PolyAlignError(
            "brush poly align run: non-quad face(s) (a run walks quads) — "
            + ", ".join(f"{bn}:{i} ({len(data[(bn, i)][0])} verts)" for bn, i in nonquad))

    # step 7 — ROOT + WALK DIRECTION, derived from the (brush, poly) key alone (tuple-sorted: brush
    # name first, then poly index — an arbitrary but deterministic tiebreak; it only fixes phase zero
    # and initial across-axis sign, never correctness — see rationale/polyalign.md "run: the frame")
    ends = [i for i in data if len(adjacency[i]) == 1]
    closed = not ends
    root = min(data) if closed else min(ends)
    order = [root]
    if closed:
        prev, cur = root, min(adjacency[root])          # leave through the LOWER-indexed neighbour
        while cur != root:
            order.append(cur)
            prev, cur = cur, next(x for x in adjacency[cur] if x != prev)
    else:
        prev, cur = None, root
        while (nxt := next((x for x in adjacency[cur] if x != prev), None)) is not None:
            order.append(nxt)
            prev, cur = cur, nxt

    # step 8 — resolve each face's entry/exit edge as world-point pairs
    walk = []
    n_order = len(order)
    for pos, idx in enumerate(order):
        wv = data[idx][0]
        if closed:                                      # root's entry seam is order[-1] (higher nbr)
            pv = order[pos - 1] if pos > 0 else order[-1]
            nx = order[pos + 1] if pos + 1 < n_order else root
            entry_i, exit_i = shared_local[idx][pv], shared_local[idx][nx]
        else:
            pv = order[pos - 1] if pos > 0 else None
            nx = order[pos + 1] if pos + 1 < n_order else None
            entry_i = shared_local[idx][pv] if pv is not None else None
            exit_i = shared_local[idx][nx] if nx is not None else None
            if entry_i is None:                         # terminal root: far edge opposite its seam
                entry_i = (exit_i + 2) % 4
            if exit_i is None:                          # terminal last: far edge opposite its seam
                exit_i = (entry_i + 2) % 4
        walk.append((idx, (wv[entry_i], wv[(entry_i + 1) % 4]),
                     (wv[exit_i], wv[(exit_i + 1) % 4])))
    return data, walk, closed


def _run_align(level: Level, targets, turn_uu: int, fit_perimeter: bool,
               resolve_dims: Callable[[str], tuple[int, int]] | None = None) -> list[str]:
    data, walk, closed = _run_prewalk(level, targets)

    tile_texels = None
    if fit_perimeter:                                   # §2.4.4 guards, then the texture requirement
        if not closed:
            raise PolyAlignError(
                "brush poly align run: --fit-perimeter needs a CLOSED run — this run is open, so it "
                "has no loop to close. Fitting an open run is a different operation.")
        if turn_uu % 16384 != 0:
            raise PolyAlignError(
                f"brush poly align run: --fit-perimeter needs a quarter --turn (a multiple of "
                f"16384); got {turn_uu}. At other angles the advance splits across both axes and one "
                f"density cannot close the loop.")
        # The texture requirement lives HERE, after the structural guards above, so a run that is
        # both broken and untextured is diagnosed structurally first (step-5 spec §3) — poly.texture
        # is model data `polyalign` already reads elsewhere (`find_faces`'s texture filter), so this
        # needs no resolver.
        refs_by_idx = {(bn, i): level.actors[bn].brush.polys[i].texture for (bn, i), _, _ in walk}
        missing = [(bn, i) for (bn, i), ref in refs_by_idx.items() if ref is None]
        if missing:
            raise PolyAlignError(
                f"brush poly align run: --fit-perimeter needs every face textured — "
                f"{len(missing)} face(s) carry no texture — "
                + ", ".join(f"{bn}:{i}" for bn, i in sorted(missing)))
        distinct = {ref.casefold() for ref in refs_by_idx.values()}
        if len(distinct) > 1:
            raise PolyAlignError(
                "brush poly align run: --fit-perimeter needs ONE texture across the whole run — "
                "faces carry different textures, so one density cannot satisfy two — split the run "
                "or set one texture first: "
                + ", ".join(f"{bn}:{i} ({ref})" for (bn, i), ref in sorted(refs_by_idx.items())))
        ref = next(iter(refs_by_idx.values()))           # the one texture, original casing
        w, h = resolve_dims(ref)                         # may raise ValueError; propagates as-is
        tile_texels = w if (turn_uu // 16384) % 2 == 0 else h   # the along-run advance's landed axis

    theta = turn_uu / 65536.0 * 2.0 * math.pi
    cth, sth = math.cos(theta), math.sin(theta)

    total_chord = sum(_len(_sub(_mid(xe), _mid(ee))) for _, ee, xe in walk)
    density_u = density_v = 1.0
    if fit_perimeter and total_chord > 1e-9:            # whole TILES: T = tile_texels, not 1 texel
        target = max(tile_texels, round(total_chord / tile_texels) * tile_texels)
        d = target / total_chord
        if (turn_uu // 16384) % 2 == 0:                 # the along-run advance lands in U (else V)
            density_u = d
        else:
            density_v = d

    # across-run sign: derived ONCE at the root, then propagated by continuity (never re-derived
    # per face against a world axis, which would flip V mid-sweep at the 45° discontinuity).
    idx0, ee0, xe0 = walk[0]
    prev_c = _across_root_sign(_cross(data[idx0][1], _unit(_sub(_mid(xe0), _mid(ee0)))))

    frames = []                                          # (base_w, tu_w, tv_w) per face, walk order
    for pos, ((bn, idx), ee, xe) in enumerate(walk):
        wv, n = data[(bn, idx)]
        m_in, m_out = _mid(ee), _mid(xe)
        t_hat = _unit(_sub(m_out, m_in))
        if pos == 0:
            c_hat = prev_c                               # the root sign, already derived above
        else:
            raw = _cross(n, t_hat)                       # propagate the sign, never re-derive it
            c_hat = raw if _dot(raw, prev_c) >= 0 else _neg(raw)
        prev_c = c_hat
        u_dir = tuple(t_hat[j] * cth + c_hat[j] * sth for j in range(3))   # rigid turn in run frame
        v_dir = tuple(-t_hat[j] * sth + c_hat[j] * cth for j in range(3))
        tu_w, tv_w = _scale(u_dir, density_u), _scale(v_dir, density_v)
        if pos == 0:
            u_in = 0.0                                   # phase zero on the root's entry-edge midpoint
            a, b = ee                                    # across zero on its lower-ĉ-projection endpoint
            z = a if _dot(a, c_hat) <= _dot(b, c_hat) else b
            v_in = _dot(_sub(m_in, z), tv_w)             # ⇒ V(z) = 0
        else:                                            # continuity at the shared seam midpoint
            pb, ptu, ptv = frames[pos - 1]
            u_in = _dot(_sub(m_in, pb), ptu)
            v_in = _dot(_sub(m_in, pb), ptv)
        rel = _add(_scale(tu_w, u_in / _dot(tu_w, tu_w)), _scale(tv_w, v_in / _dot(tv_w, tv_w)))
        base_w = _sub(m_in, rel)
        frames.append((base_w, tu_w, tv_w))
        actor = level.actors[bn]
        _write_world_frame(actor, actor.brush.polys[idx], base_w, tu_w, tv_w, (0, 0))

    _report_seam_shear(walk, frames)
    return sorted({bn for bn, _ in data})


def _report_seam_shear(walk, frames) -> None:
    """Print the worst INTERNAL-seam shear to stderr, MEASURED from the written frames (never a closed
    form, which does not hold for cylinder or compound runs). A closed run's closing seam is
    deliberately left open (walk order excludes it), so its full-perimeter gap is not reported."""
    worst_u = worst_v = 0.0
    for p in range(len(walk) - 1):
        seam = walk[p][2]                                # face p's exit edge == face p+1's entry edge
        (ba, ua, va), (bb, ub, vb) = frames[p], frames[p + 1]
        for point in seam:
            worst_u = max(worst_u, abs(_dot(_sub(point, ba), ua) - _dot(_sub(point, bb), ub)))
            worst_v = max(worst_v, abs(_dot(_sub(point, ba), va) - _dot(_sub(point, bb), vb)))
    tail = "" if worst_u < 1e-3 and worst_v < 1e-3 else " — mitre the corner or accept a visible seam"
    print(f"brush poly align run: worst seam shear dU={worst_u:.2f} dV={worst_v:.2f} texels{tail}",
          file=sys.stderr)


# --------------------------------------------------------------------- entry point

def align(level: Level, tokens: list[str], mode: str, *,
          turn: int = 0, fit_perimeter: bool = False,
          resolve_dims: Callable[[str], tuple[int, int]] | None = None) -> list[str]:
    """Align the texture frames of the faces named by `tokens` (bare names / `BRUSH:SELECTOR`) in
    `mode` (`wall`|`floor`|`run`|`one-tile`). `wall`/`floor` write the editor's projection frame
    (`|proj|` density, ≤ 1); `run` walks a connected run laying one continuous texture along it at
    unit density, `--turn` rotating the frame in unreal rotation units; `one-tile` fits exactly one
    texture tile to each face independently. Every mode zeroes `Pan`. Returns the sorted touched
    brush names; `run` also prints the worst seam shear to stderr. `turn`/`fit_perimeter` are
    run-only (argparse enforces it via the subcommand). `resolve_dims` (a `ref -> (USize, VSize)`
    callable that RAISES `ValueError` naming the ref and why on failure) is required for `one-tile`
    and for `run` when `fit_perimeter` is set — the CLI builds it once per invocation over the
    project's package path; `polyalign` never imports a resolver itself. Empty `tokens` ⇒ `[]` (a
    clean no-op). Raises `PolyAlignError` (a `ValueError`) naming the offender for every failure
    path."""
    targets = resolve_align_targets(level, tokens)
    if not targets:
        return []
    if mode == "run":
        return _run_align(level, targets, turn, fit_perimeter, resolve_dims)
    if mode in ("wall", "floor"):
        return _projected_align(level, targets, mode)
    if mode == "one-tile":
        return _one_tile_align(level, targets, resolve_dims)
    raise PolyAlignError(f"brush poly align: unknown mode {mode!r}")


def face_uv(actor: Actor, poly, world_point) -> tuple[float, float]:
    """The (U,V) texel coordinate a world point maps to under `poly`'s stored frame, via the canonical
    convention `U=(P−Origin)·TextureU+PanU`. Reuses `world_uv_frame` (the renderer's frame), so a
    test can assert seam continuity by comparing this across the two faces sharing an edge."""
    base_w, tu_w, tv_w, pan = _uv_frame_guarded(actor, poly)
    p = tuple(float(c) for c in world_point)
    rel = _sub(p, base_w)
    return (_dot(rel, tu_w) + pan[0], _dot(rel, tv_w) + pan[1])

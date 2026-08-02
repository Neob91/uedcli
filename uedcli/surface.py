"""Per-surface (polygon) content edits. Pure model-side transform — no editor (per-poly
`PolyFlags`/`Texture`/`Pan`/`TextureU`/`TextureV` survive the `apply` paste path, quirks-verified).

Two families of verb live here and they do different jobs (`../dev/docs/rationale/surface.md`
"The verb split: attributes vs the frame"):

* `brush poly set` assigns **stored per-face attributes** — texture, surface flags.
* `brush poly pan` / `rotate` / `scale` transform the **texture frame** — the
  `Pan`/`Origin`/`TextureU`/`TextureV` quadruple the renderer maps a face's pixels with.

The UV convention every frame transform is defined against (`../dev/docs/unrealed/t3d.md`
"The UV convention"):

    U = (Vertex − Origin) · TextureU + PanU        (V analogously)

so the **texel scale is carried in `|TextureU|`** (a unit `TextureU` is 1 texel per world unit) and
`Origin` is the point mapping to `(PanU, PanV)`. The stored triples are in the brush's **LOCAL**
frame, which is where the transforms below work: the vertex centroid commutes with the actor's
affine transform, so nothing is gained by a world round trip and the float dust of one is avoided.

See dev/docs/specs/2026-06-19-uedcli-surface-flags-texturing-design.md (the original `set`) and
dev/docs/rationale/surface.md (the split, the centroid re-anchor, the out-of-plane guard)."""
from __future__ import annotations

import math
from decimal import Decimal

from . import rotation, vertex
from .emit import fmt_vertex
from .geometry import validate_brush
from .model import Actor, CoordinateError, Level
from .query import PF_NAMES, resolve_actor_name
from .texframe import newell

_FLAG_BY_NAME = {name: bit for bit, name in PF_NAMES}


def encode_flags(names: list[str]) -> int:
    """OR together the bits for `names` (each must be a `PF_NAMES` name, matched
    CASE-INSENSITIVELY so the docs' `Unlit`/`Masked` capitalization works too). Strict: rejects any
    unknown name — no `none`, no hex literals. `decode_flags` is NOT a clean inverse (it emits
    exactly those for 0 / unknown bits), so it can't supply valid input here."""
    bad = [n for n in names if n.lower() not in _FLAG_BY_NAME]
    if bad:
        valid = ", ".join(name for _, name in PF_NAMES)
        raise ValueError(f"unknown flag name(s): {', '.join(bad)} (valid: {valid})")
    bits = 0
    for n in names:
        bits |= _FLAG_BY_NAME[n.lower()]
    return bits


def parse_poly_selector(token: str) -> tuple[str, str]:
    """Split a `BRUSH:SELECTOR` token by the LAST colon. Actor names are colon-free (UE1 FNames and
    uedcli's name allocation never produce a colon), so the split-on-last-colon is defensive and the
    colon unambiguously separates the brush name from the selector — the selector grammar (and the
    colon-based `--highlight` poly-vs-name disambiguation) depends on that invariant."""
    if ":" not in token:
        raise ValueError(f"surface selector must be BRUSH:SELECTOR, got {token!r}")
    brush, _, selector = token.rpartition(":")
    if not brush:
        raise ValueError(f"surface selector is missing a brush name: {token!r}")
    return brush, selector


def resolve_polys(selector: str, actor: Actor, *, brush_name: str) -> set[int]:
    """`all` -> every poly index of `actor.brush`; else a comma list of zero-based indices
    (matching `query.list_polys`' `enumerate(..., start=0)`). Raises `ValueError` naming
    `brush_name` for every failure mode (not a brush, empty selector, bad/out-of-range index,
    no surfaces selected)."""
    if actor.brush is None:
        raise ValueError(f"{brush_name!r} is not a brush")
    n = len(actor.brush.polys)
    if selector == "all":
        if n == 0:
            raise ValueError(f"{brush_name!r} has no polys to select")
        return set(range(n))
    if not selector:
        raise ValueError(f"empty selector for {brush_name!r} (expected 'all' or indices)")
    indices: set[int] = set()
    for part in selector.split(","):
        part = part.strip()
        if not part.lstrip("-").isdigit():
            raise ValueError(f"{brush_name!r}: bad poly index {part!r} (expected an integer)")
        idx = int(part)
        if not (0 <= idx < n):
            raise ValueError(
                f"{brush_name!r}: poly index {idx} out of range (brush has {n} polys)")
        indices.add(idx)
    return indices


def parse_texture_ref(ref: str) -> str:
    """Validate a qualified Unreal object ref (2+ dotted components: `Package.[Group.]*Name`);
    return the first dot-component (the package, for the `main/packages` union). Bare names and
    `MyLevel.*` are rejected — a texture needs a real package to load, and T3D can't carry
    embedded `myLevel` resources through materialize (`unrealed/t3d.md` "What T3D cannot carry").
    The group, if any, is preserved verbatim here — `brush poly set --texture` callers should still
    omit it (uedcli convention, `unrealed/quirks.md` "T3D format": never required, even when
    the object genuinely has one) but this only validates format, not style."""
    parts = ref.split(".")
    if len(parts) < 2:
        raise ValueError(f"texture ref must be qualified (Package.Name), got {ref!r}")
    if parts[0] == "MyLevel":
        raise ValueError(f"texture ref cannot be MyLevel.* (not materializable): {ref!r}")
    return parts[0]


def resolve_targets(level: Level, targets: list[str]) -> list[tuple[str, int]]:
    """Resolve `BRUSH:SELECTOR` tokens to a DEDUPED, deterministically ordered list of
    `(canonical_brush_name, poly_index)` pairs — sorted by brush name, then by index.

    This is the ONE resolution path for every per-face verb in this module, and it is shared with
    the CLI for a reason: `brush poly set|pan|rotate|scale` print the faces they touched as
    `BRUSH:idx` selectors, and echoing the caller's own tokens back would be wrong three ways —
    `Wall:all` has to expand to `Wall:0 … Wall:5`, `wall:3` has to print the canonical `Wall:3`
    (`resolve_actor_name` matches case-insensitively), and an overlapping target set has to collapse.
    Dedup is also load-bearing for the RELATIVE forms (`pan --by`, `rotate --by`, `scale --by`),
    which would otherwise apply twice to a face named twice.

    Raises `ValueError` naming the first offender for a malformed selector, an unknown brush, a
    non-brush actor, or an out-of-range index — nothing is resolved lazily, so a caller that
    resolves before mutating is all-or-nothing."""
    selected: dict[str, set[int]] = {}
    for token in targets:
        brush_name, selector = parse_poly_selector(token)
        try:
            brush_name = resolve_actor_name(level, brush_name)
        except KeyError:
            raise ValueError(f"unknown brush {brush_name!r}")
        indices = resolve_polys(selector, level.actors[brush_name], brush_name=brush_name)
        selected.setdefault(brush_name, set()).update(indices)
    # `selected[b]` is a SET, whose iteration order is not a contract — sort both levels so the
    # printed selector list and the mutation order are reproducible run to run.
    return [(b, i) for b in sorted(selected) for i in sorted(selected[b])]


def _touched_brushes(pairs: list[tuple[str, int]]) -> list[str]:
    """The sorted unique brush names of a `resolve_targets` pair list — what every mutator here
    returns, for `src.save(touched=…)`. (The mutators deliberately do NOT return the pairs: the
    session-store `touched=` channel is a set of ACTORS, and the CLI gets its per-face selectors by
    calling `resolve_targets` itself.)"""
    return sorted({b for b, _ in pairs})


def apply_surface_edit(level: Level, targets: list[str], *, texture_ref: str | None = None,
                       add_flags: list[str] | None = None,
                       remove_flags: list[str] | None = None) -> list[str]:
    """`brush poly set` — assign stored per-face ATTRIBUTES (texture, surface flags).

    Pure transform: resolve `targets` to a unique `(brush, poly_index)` set, then mutate each
    selected poly in place. Returns the sorted touched brush names. All-or-nothing: every target is
    resolved (raising `ValueError` naming the first offender) before anything is mutated.

    Pan is NOT here — it moves the texture frame, so it is `brush poly pan` (see `apply_pan`)."""
    if texture_ref is None and not add_flags and not remove_flags:
        raise ValueError(
            "brush poly set: at least one of --texture/--add-flag/--remove-flag is required")
    if texture_ref is not None:
        parse_texture_ref(texture_ref)            # validate format before mutating anything
    add_bits = encode_flags(add_flags) if add_flags else 0
    remove_bits = encode_flags(remove_flags) if remove_flags else 0

    pairs = resolve_targets(level, targets)
    for brush_name, idx in pairs:
        poly = level.actors[brush_name].brush.polys[idx]
        if add_bits or remove_bits:
            poly.flags = (poly.flags | add_bits) & ~remove_bits
        if texture_ref is not None:
            poly.texture = texture_ref
    touched = _touched_brushes(pairs)
    for brush_name in touched:
        validate_brush(level.actors[brush_name].brush)
    return touched


def apply_pan(level: Level, targets: list[str], *, pan_to: tuple[int, int] | None = None,
              pan_by: tuple[int, int] | None = None) -> list[str]:
    """`brush poly pan` — offset the texture on each selected face by whole texels, writing the
    polygon `Pan` field and nothing else.

    EXACTLY one of `pan_to` (absolute) / `pan_by` (relative to the current pan, 0,0 if unset) is
    required — a different rule from `apply_surface_edit`'s *at least* one, hence a different
    message. `pan_to=(0, 0)` clears the pan, and a zero pan is never serialized at all
    (`emit.emit_polygon`; `../dev/docs/unrealed/t3d.md` "A poly sub-field has NO class default"), so
    the face round-trips as one that was never panned.

    It never touches `Origin`, which is the counterpart to `rotate`/`scale`'s "writes `Origin`,
    leaves `Pan`" — so a `brush poly align run` continuity offset (which lives in `Origin`) survives
    a pan applied to the WHOLE run. Panning a SUBSET of a run shifts those faces relative to their
    neighbours and breaks the seams.

    Returns the sorted touched brush names."""
    if (pan_to is None) == (pan_by is None):
        raise ValueError("brush poly pan: exactly one of --to/--by is required")
    pairs = resolve_targets(level, targets)
    for brush_name, idx in pairs:
        poly = level.actors[brush_name].brush.polys[idx]
        if pan_to is not None:
            poly.pan = pan_to
        else:
            base = poly.pan or (0, 0)
            poly.pan = (base[0] + pan_by[0], base[1] + pan_by[1])
    touched = _touched_brushes(pairs)
    for brush_name in touched:
        validate_brush(level.actors[brush_name].brush)
    return touched


def apply_move(level: Level, targets: list[str], *, by) -> list[str]:
    """`brush poly move --by DX,DY,DZ` — translate whole faces model-side, via `vertex.move_vertices`.

    Per brush: collect the WELDED corners any selected poly touches (welding dedupes a corner two
    selected adjacent faces share, so `move_vertices` never sees a repeated selector), map the world
    `by` into that brush's local frame (`world_to_local_delta`, per-actor), and move those corners.
    Every copy of a moved corner shifts together, so the brush stays watertight and a face sharing it
    DEFORMS — including a neighbour that was not selected, but NOT one in a different brush (welding is
    per-brush). `move_vertices` validates each result, so a degenerate/non-planar outcome raises
    `GeometryError`. All-or-nothing: `resolve_targets` names the first offender before any mutation.

    (The `--by` help calls most non-axis moves rejected; inaccurate for quad brushes, where a
    whole-face constant-delta move keeps neighbours planar — board `brush-poly-move-spec-help-...`.)"""
    pairs = resolve_targets(level, targets)
    selected: dict[str, set[int]] = {}
    for brush_name, idx in pairs:
        selected.setdefault(brush_name, set()).add(idx)
    for brush_name, idxs in selected.items():
        actor = level.actors[brush_name]
        corners = [w.coord for w in vertex.weld_vertices(actor.brush)
                   if any(pi in idxs for pi, _ in w.refs)]
        local_delta = rotation.world_to_local_delta(actor, by)
        actor.brush = vertex.move_vertices(actor.brush, corners, by=local_delta)
    return _touched_brushes(pairs)


# --------------------------------------------------------- the texture frame: rotate and scale
#
# Both verbs transform the face's `TextureU`/`TextureV` and RE-ANCHOR `Origin` so the face's own
# centroid `C` keeps the `(U,V)` it had — the texture turns or grows IN PLACE instead of sliding off
# the face. They leave `Pan` alone (that is `brush poly pan`'s field).
#
# Everything below works in the brush's LOCAL frame, because that is where `Origin`/`TextureU`/
# `TextureV` are stored and because a centroid commutes with the actor's affine transform: the
# world centroid of a face is the transform of its local centroid, so transforming out to world and
# back would change nothing but the float dust.

_UU_PER_TURN = 65536        # unreal rotation units in a full turn — `--by 16384` is a quarter turn
_UU_PER_QUARTER = _UU_PER_TURN // 4

# `rotate`'s OUT-OF-PLANE guard: an axis is rejected when
#     |axis · n̂|  >  max(_OOP_ABS, _OOP_REL · |axis|)
# The two effects the threshold sits between scale DIFFERENTLY, which is why it is neither purely
# absolute nor purely relative: the serializer's noise is absolute (`emit.clean` snaps each
# component independently within `CLEAN_EPS = 0.001`, so it displaces an axis by up to
# √3·CLEAN_EPS ≈ 1.7e-3 regardless of how long the axis is), while the harm is relative (`n̂ × U`
# shortens the axis by √(1−ε²), costing ε²/2 of texel density). A relative-only gate therefore
# tightens without limit as an axis shrinks — and `brush poly scale --by 8,8` shrinks a unit axis to
# 0.125, where the same absolute noise reads as 1.13e-2 relative and would trip a 1e-2 gate on a
# frame uedcli itself wrote one trunk round trip earlier.
# Full derivation and the corpus measurement: dev/docs/rationale/surface.md.
_OOP_ABS = 3e-3
_OOP_REL = 1e-2

_TINY = 1e-9                # below this a length/normal is treated as zero (degenerate)


def _f3(v) -> tuple[float, float, float]:
    """A model `Vec3` as plain floats. Vertices parse as `Decimal` and the texture triples may be
    either (`model.parse_t3d` yields `Decimal`, `polyalign` writes `float`), and mixing the two in
    one arithmetic expression is a `TypeError` — so every consumer here floats first."""
    return (float(v[0]), float(v[1]), float(v[2]))


def _sub3(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _add3(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _dot3(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross3(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _mul3(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)


def _len3(a) -> float:
    return math.sqrt(_dot3(a, a))


def _local_verts(poly, ref: str, verb: str) -> list[tuple[float, float, float]]:
    verts = [_f3(v) for v in poly.vertices]
    if len(verts) < 3:
        raise ValueError(f"{verb}: face {ref} has fewer than 3 vertices — it has no plane")
    return verts


def _centroid3(verts) -> tuple[float, float, float]:
    n = len(verts)
    return (sum(v[0] for v in verts) / n,
            sum(v[1] for v in verts) / n,
            sum(v[2] for v in verts) / n)


def _unit_normal(verts, ref: str, verb: str) -> tuple[float, float, float]:
    """The face's unit normal, computed from its own VERTEX WINDING by Newell's method — never from
    the stored `poly.normal`, which the engine ignores and recomputes (`unrealed/t3d.md` "Winding
    defines the face"), so an authored one is routinely wrong. Newell rather than a cross product of
    the first three vertices, which produces garbage when those three are near-collinear."""
    n = newell(verts)
    m = _len3(n)
    if m < _TINY:
        raise ValueError(f"{verb}: face {ref} is degenerate (zero area) — it has no face plane")
    return _mul3(n, 1.0 / m)


def _frame(poly, ref: str, verb: str):
    """The face's stored texture frame as float triples, or a named `ValueError`.

    `Origin` is a REQUIRED brush-polygon sub-field (`unrealed/t3d.md` "Polygon sub-fields
    reference"), so an absent one is malformed input rather than a case to default; `TextureU`/
    `TextureV` are equally required and a face missing them has no frame to transform."""
    if poly.origin is None:
        raise ValueError(f"{verb}: face {ref} has no Origin — a brush polygon requires one, so this "
                         f"face's texture frame is incomplete")
    if poly.texture_u is None or poly.texture_v is None:
        raise ValueError(f"{verb}: face {ref} has no TextureU/TextureV — there is no texture frame "
                         f"to transform")
    return _f3(poly.origin), _f3(poly.texture_u), _f3(poly.texture_v)


def _axis_is_writable(axis) -> bool:
    """Will this texture axis survive the trip through the serializer as a NON-ZERO vector?

    It ASKS THE SERIALIZER — `emit.fmt_vertex` is the exact function `emit._vec_line` puts each
    component through on the way into the trunk — and reads back what it produced. Nothing about
    the bound is restated here, because restating it is how this went wrong: an earlier version
    asserted the floor was `emit`'s six decimal places (`5e-7`) and the ceiling was whatever
    `emit.clean` refused, and BOTH were wrong by orders of magnitude.

    * **The floor is `CLEAN_EPS = 1e-3`, not `5e-7`.** `clean` snaps any component *within
      `CLEAN_EPS` of an integer* to that integer, and `0` is an integer — so a component of
      `0.001` is written as `+00000.000000`. An axis whose every component does that reaches the
      CSG rebuild as a ZERO-LENGTH vector and crashes it (`builders._tex_basis`). Measured: on a
      unit axis `scale --by 999` survives and `--by 1000` does not, and three successive
      `--by 10,10` invocations destroyed the axis with no diagnostic. The out-of-plane guard above
      is derived from this same `CLEAN_EPS`, so the module knew it in one place and forgot it here.
    * **The ceiling is `fmt_vertex`, not `clean`.** `clean` only reaches `quantize6` when the value
      is *not* within `CLEAN_EPS` of an integer, and every value from `1e22` up is exactly integral
      in `Decimal` terms — so `clean(1e22)` returns it unharmed while `fmt_vertex(1e22)` raises.
      Checking `clean` left the whole band `[1e22, ~1.3e154]` open, where the failure surfaced from
      `src.save` as a message about world coordinates and ±32768 — on a texture axis.

    Because every writable component is under `1e22`, `|axis|²` is under `3e44` and the Gram
    entries in `apply_scale`'s re-anchor cannot overflow; that is why no separate magnitude test
    is needed here."""
    try:
        written = [Decimal(fmt_vertex(component)) for component in axis]
    except CoordinateError:
        return False
    return any(w != 0 for w in written)


def _visible_normal(actor: Actor, verts, ref: str, verb: str) -> tuple[float, float, float]:
    """The face's normal AS THE AUTHOR SEES IT — the winding normal, flipped when the brush is
    SUBTRACTIVE.

    A polygon's winding normal points out of the *solid* it bounds. On an additive brush that is the
    surface an author looks at; on a subtractive one — a room carved out of the world — the visible
    surface is the room's inside, which faces the other way. Owner ruling 2026-07-27: `rotate` turns
    against the VISIBLE surface normal, so an author who selects a face they can see gets the texture
    turning the way that face turns from where they stand. See
    `../dev/docs/rationale/surface.md` "`rotate` turns against the VISIBLE surface normal".

    The `CsgOper` dependency this introduces is real and was accepted with the ruling: the sign now
    depends on a property of the BRUSH rather than of the face. An author knows whether they are
    texturing a room or a pillar; a silent inversion indoors is not discoverable at all.

    An ABSENT `CsgOper` reads as `CSG_Add`, matching every other reader in the codebase
    (`brushcsg._oper_of`, `preview._csg_color`, `preview_native`) — it is not a subtractive brush, so
    the ruling leaves it unflipped. Any OTHER value is refused rather than guessed: see below."""
    oper = next((v for k, v in actor.props if k == "CsgOper"), "CSG_Add")
    normal = _unit_normal(verts, ref, verb)
    if oper == "CSG_Add":
        return normal
    if oper == "CSG_Subtract":
        return _mul3(normal, -1.0)
    # `CSG_Intersect`/`CSG_Deintersect` are live-editor verbs that do not appear in a trunk, and
    # anything else is malformed. Neither has a "visible surface normal" the ruling's principle can
    # be applied to, so there is no sign to derive — and guessing one is the WORST outcome available
    # here, because a wrong turn direction is silent and looks like the author's own mistake.
    # `direction/conventions.md` "No silent half-answers": refuse, naming the value.
    raise ValueError(
        f"{verb}: face {ref} is on a brush with CsgOper={oper!r}, which is neither CSG_Add nor "
        f"CSG_Subtract — the turn direction follows the VISIBLE surface normal, and this brush has "
        f"no defined inside or outside for that to mean anything")


def _rotator(normal, by_uu: int):
    """The in-plane rotation operator for `by_uu` unreal rotation units about `normal`, as a
    function of one vector. The SAME operator is applied to the axes and to the re-anchor offset,
    which is what makes the centroid's `(U,V)` preserved identically rather than approximately.

    A whole number of QUARTER turns takes an exact, trig-free path: `n̂ × d`, applied
    `k = (by_uu // 16384) % 4` times (floor division and Python's `%` already give a non-negative
    `k` for a negative angle, so `--by -16384` is `--by 49152`). On a `+Z` face this maps
    `TextureU=+X, TextureV=+Y` to exactly `TextureU=+Y, TextureV=−X`, which is what keeps a
    quarter-turn out of the trunk diff as float dust.

    `n̂ × d` annihilates `d`'s component ALONG the normal, so it is not a rotation of a general
    vector. That is fine here and must not be "fixed": the texture axes are guarded to lie in the
    plane, and a normal component of the re-anchor offset cannot affect `(U,V)` at all because both
    axes are perpendicular to `n̂`. One consequence is deliberate and pinned by a test: the two paths
    do NOT agree on the written `Origin` when `Origin` has an out-of-plane component — the exact path
    drops it, the Rodrigues path keeps it — and both are correct, because both preserve the
    centroid's `(U,V)` exactly.

    `by_uu` is reduced MODULO ONE FULL TURN first. A rotation is periodic, so this is exact in the
    integer domain and changes no result; what it removes is the float conversion of an unbounded
    `int`. `--by` is `type=int`, hence arbitrary precision, so a value past ~1e308 that is not a
    whole number of quarter turns would otherwise reach `by_uu * 2.0` and raise
    `OverflowError: int too large to convert to float` — an uncaught traceback, since the dispatch
    guard catches `ValueError`. Reduction is also why `--by -16384` is `--by 49152`: Python's `%`
    returns a non-negative remainder."""
    by_uu %= _UU_PER_TURN
    if by_uu % _UU_PER_QUARTER == 0:
        k = (by_uu // _UU_PER_QUARTER) % 4

        def rotate_exact(d):
            for _ in range(k):
                d = _cross3(normal, d)
            return d
        return rotate_exact, k == 0

    theta = by_uu * 2.0 * math.pi / _UU_PER_TURN
    ct, st = math.cos(theta), math.sin(theta)

    def rotate_rodrigues(d):                     # Rodrigues about n̂
        return _add3(_add3(_mul3(d, ct), _mul3(_cross3(normal, d), st)),
                     _mul3(normal, _dot3(normal, d) * (1.0 - ct)))
    return rotate_rodrigues, False


def apply_rotate(level: Level, targets: list[str], *, by_uu: int) -> list[str]:
    """`brush poly rotate --by UU` — turn each selected face's texture within its own plane by
    `by_uu` unreal rotation units (16384 = 90°), re-anchoring on the face centroid.

    Writes `Origin`/`TextureU`/`TextureV`; leaves `Pan` untouched. Each face pivots about its OWN
    centroid, so this gives NO continuity guarantee across a set — it is the verb for a one-off face
    (a sign, a panel), not for a run.

    The turn direction follows the **VISIBLE** surface normal, so the same `--by 16384` turns the
    texture the same way as seen from outside the face on an additive and on a subtractive brush
    alike (owner ruling 2026-07-27). `n̂` is the winding normal with its sign flipped on a subtract —
    see `_visible_normal`, which also refuses a `CsgOper` that is neither add nor subtract.

    A MIRRORED brush — scale determinant negative, i.e. an ODD number of negative components — has
    its faces drawn with reversed winding, so the visible normal is the opposite of the one computed
    here and the turn inverts again. NOT covered by the flip above; documented rather than corrected,
    and a geometric argument rather than a measured one. An EVEN number of negative components is a
    180° rotation, not a mirror, and is unaffected.

    All-or-nothing: every face is resolved and validated — frame present, non-degenerate, axes in
    the face plane — in a PRE-PASS before anything is written, and every out-of-plane offender is
    named together, so a bad face 7 of 12 leaves faces 0–6 unmutated."""
    verb = "brush poly rotate"
    pairs = resolve_targets(level, targets)
    prepared = []
    offenders: list[str] = []
    for brush_name, idx in pairs:
        ref = f"{brush_name}:{idx}"
        poly = level.actors[brush_name].brush.polys[idx]
        origin, tu, tv = _frame(poly, ref, verb)
        verts = _local_verts(poly, ref, verb)
        normal = _visible_normal(level.actors[brush_name], verts, ref, verb)
        for label, axis in (("TextureU", tu), ("TextureV", tv)):
            mag = _len3(axis)
            if mag < _TINY:
                raise ValueError(f"{verb}: face {ref} has a zero-length {label} — rotating it would "
                                 f"leave a texture frame the CSG rebuild cannot use")
            out_of_plane = abs(_dot3(axis, normal))
            if out_of_plane > max(_OOP_ABS, _OOP_REL * mag):
                offenders.append(f"{ref} {label} ({out_of_plane / mag:.3g} of its length)")
        prepared.append((poly, normal, _centroid3(verts), origin, tu, tv))
    if offenders:
        raise ValueError(
            f"{verb}: these faces' texture axes point out of the face plane, so rotating them would "
            f"silently change the texel density: " + ", ".join(offenders) +
            " — re-align these faces (brush poly align) before rotating them")

    for poly, normal, centroid, origin, tu, tv in prepared:
        rotate, is_identity = _rotator(normal, by_uu)
        if is_identity:
            continue                     # a whole number of turns: writing C − (C − Origin) back
        poly.texture_u = rotate(tu)      # would only add float dust to an unchanged frame
        poly.texture_v = rotate(tv)
        poly.origin = _sub3(centroid, rotate(_sub3(centroid, origin)))
    touched = _touched_brushes(pairs)
    for brush_name in touched:
        validate_brush(level.actors[brush_name].brush)
    return touched


def apply_scale(level: Level, targets: list[str], *, by: tuple[float, float]) -> list[str]:
    """`brush poly scale --by FU,FV` — multiply the texture's APPARENT SIZE on each selected face,
    re-anchoring on the face centroid.

    `--by 2,2` makes the texture look twice as big, which DIVIDES the stored magnitudes
    (`|TextureU| ← |TextureU| / FU`): T3D density is texels per world unit, so a longer axis is a
    smaller-looking texture. The verb is named for what the author sees, not for what is stored.
    U and V scale independently. Directions are preserved, so an out-of-plane axis is harmless here
    and there is no in-plane guard (unlike `rotate`).

    Writes `Origin`/`TextureU`/`TextureV`; leaves `Pan` untouched. A zero or negative factor exits
    non-zero naming the value — a zero-length texture vector crashes the CSG rebuild
    (`builders._tex_basis`).

    **The re-anchor REPROJECTS `Origin` onto the face plane**, exactly as `rotate`'s does. The Gram
    solve writes `Origin' = C − (a·TU' + b·TV')`, which lies in the span of the two texture axes by
    construction, so any component `Origin` had along the face normal is dropped. That is
    rendering-neutral — the axes are perpendicular to the normal, so such a component cannot affect
    `(U,V)`, and the centroid's `(U,V)` is preserved exactly either way — but it IS a change the
    trunk records.

    **`--by 1,1` is therefore short-circuited to write nothing at all**, matching `rotate --by 0`:
    the operation the author asked for is the identity, and reprojecting `Origin` for it would churn
    the trunk's git diff for a request to change nothing.

    NO continuity guarantee, and more strongly than `rotate`: scaling breaks a `brush poly align
    run` even when applied uniformly to the whole run, because each face re-anchors about its own
    centroid while the run's phase offsets were computed for the old density. Scale BEFORE aligning
    a run, never after.

    All-or-nothing: every face is resolved and its frame validated before anything is written."""
    verb = "brush poly scale"
    fu, fv = float(by[0]), float(by[1])
    for label, factor in (("FU", fu), ("FV", fv)):
        if not math.isfinite(factor) or factor <= 0:
            raise ValueError(f"{verb}: --by {label} must be a positive number, got {factor!r} — a "
                             f"zero or negative texture axis crashes the CSG rebuild")
    pairs = resolve_targets(level, targets)
    prepared = []
    for brush_name, idx in pairs:
        ref = f"{brush_name}:{idx}"
        poly = level.actors[brush_name].brush.polys[idx]
        origin, tu, tv = _frame(poly, ref, verb)
        centroid = _centroid3(_local_verts(poly, ref, verb))
        tu2, tv2 = _mul3(tu, 1.0 / fu), _mul3(tv, 1.0 / fv)
        # Name the right offender, in BOTH directions. An axis the trunk cannot store is either the
        # FRAME's fault (it arrived that way) or the FACTOR's (this call made it so), and the Gram
        # check below cannot tell them apart — it would call a perfectly ordinary orthogonal frame
        # "degenerate" for an absurd factor, and blame an innocent `--by 1.0` for a monstrous
        # authored axis. Asking about the axis BEFORE and AFTER scaling separates the two exactly.
        for label, factor, axis_name, axis, scaled in (
                ("FU", fu, "TextureU", tu, tu2), ("FV", fv, "TextureV", tv, tv2)):
            if not _axis_is_writable(axis):
                raise ValueError(
                    f"{verb}: face {ref} already has a {axis_name} the trunk cannot store (it is "
                    f"zero-length, or too large for a T3D coordinate) — the FRAME is malformed, so "
                    f"no --by factor can fix it; re-align the face instead")
            if not _axis_is_writable(scaled):
                raise ValueError(
                    f"{verb}: --by {label}={factor!r} is too extreme for face {ref} — it would "
                    f"leave {axis_name} at a length the trunk cannot store (too short to survive "
                    f"the grid snap, or too large for a T3D coordinate), and a zero-length texture "
                    f"axis crashes the CSG rebuild")
        # Re-anchor by a 2x2 GRAM SOLVE, not by scaling the direct-basis components. T3D does not
        # require TextureU ⊥ TextureV, and scaling the covectors TU,TV by 1/fu,1/fv scales position
        # by the INVERSE TRANSPOSE — along the reciprocal vectors, not along Û/V̂. Preserving the
        # projections directly is what stays correct on a skewed frame under a non-uniform factor:
        # solve D' from D'·TU' = D·TU and D'·TV' = D·TV. (`rotate` genuinely avoids this because a
        # rotation is an isometry and leaves the Gram matrix invariant; scaling does not.)
        g11, g12, g22 = _dot3(tu2, tu2), _dot3(tu2, tv2), _dot3(tv2, tv2)
        det = g11 * g22 - g12 * g12
        # `det/(g11·g22)` is `sin²θ` between the axes, so the test is scale-invariant: it asks only
        # whether they are too nearly PARALLEL to span a plane, which is the one degeneracy the
        # writability checks above cannot see. The `isfinite` half is a backstop and should now be
        # unreachable — both axes are writable by the time we get here, so every component is under
        # `1e22`, `g11`/`g22` are under `3e44` and their product is under `1e89`, decades below the
        # float ceiling. It is kept rather than deleted because that is a proof about float ranges,
        # not a test, and the cost of being wrong is `nan` reaching the trunk.
        if not math.isfinite(det) or det <= 1e-12 * g11 * g22:
            raise ValueError(f"{verb}: face {ref} has a degenerate texture frame — TextureU and "
                             f"TextureV are parallel, so they do not span the face and the scaled "
                             f"texture cannot be re-anchored on the face centroid")
        d = _sub3(centroid, origin)
        u, v = _dot3(d, tu), _dot3(d, tv)
        a = (u * g22 - v * g12) / det
        b = (v * g11 - u * g12) / det
        prepared.append((poly, tu2, tv2, _sub3(centroid, _add3(_mul3(tu2, a), _mul3(tv2, b)))))
    if (fu, fv) != (1.0, 1.0):          # `--by 1,1` is the identity: see the docstring, and
        for poly, tu2, tv2, origin2 in prepared:      # `rotate`'s matching whole-turn skip
            poly.texture_u, poly.texture_v, poly.origin = tu2, tv2, origin2
    touched = _touched_brushes(pairs)
    for brush_name in touched:
        validate_brush(level.actors[brush_name].brush)
    return touched

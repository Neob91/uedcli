"""Model → T3D text. The single write path.

Folds align_grid rules into emission: snap near-integer coords to the grid and
ALWAYS quote Group values (unquoted multi-group values silently drop groups on
IMPORTADD/paste). Vertex winding order is preserved verbatim — winding, not the
emitted Normal, defines a face in UnrealEd's importer.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from .model import Actor, Brush, CoordinateError, Polygon, Vec3

# A coordinate within CLEAN_EPS of an integer is editor/float NOISE and snaps to
# that integer; anything further is a GENUINE fractional vertex and is preserved
# at 6-dp (UnrealEd's T3D precision). Brushes — typically semisolids — can carry
# fractional vertices, and the editor itself emits them (e.g. -479.999969); we
# only clean the sub-grid noise, never force real fractions onto the grid.
CLEAN_EPS = Decimal("0.001")
_SIX_DP = Decimal("0.000001")

# There is deliberately NO magnitude constant here, and the representability check is NOT global.
# The two emitters have genuinely different ranges and always have: `fmt_vertex` rounds through
# `quantize(_SIX_DP)`, which under Decimal's 28-digit working precision leaves 22 digits for the
# integer part (the wall is 1e22), while `fmt_loc` formats with `f"{d:.6f}"` and has no wall at
# all. So the check lives at each quantize site rather than in the shared front door: putting it
# in `_guard` made a Location that had always emitted start exiting 2, which is how an existing
# trunk becomes unreadable to `actor show`. `_guard` therefore rejects only NON-FINITE values —
# never representable in either emitter — and `_quantize6` converts the precision failure into a
# named error where it actually occurs. Net effect: every value master emitted still emits, and
# the ones that used to raise `InvalidOperation` now exit 2 instead of printing a traceback.
# (For scale: the engine's own world is ±32768, far below any of this.)


def _to_decimal(value) -> Decimal:
    # str() first so a float's binary tail (0.1 -> 0.1000000000000000055…) never
    # enters the Decimal — the authored/text value is the source of truth.
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _guard(value) -> Decimal:
    """Decimal-ise a coordinate, rejecting one that is not a finite number.

    Deliberately does NOT check magnitude — see the note above `_to_decimal`: `fmt_loc` can emit
    values `fmt_vertex` cannot, so a shared magnitude check narrows the Location range.

    NOTE the value reported is the one that reached THIS function, which is not always the one
    the user typed — `brush build cube --width 1e25` halves the width to a half-extent first, so
    the message names 5e+24. That is accepted: the emitter cannot see the flag that produced a
    vertex, and a wrong flag name would be worse than an unfamiliar magnitude.
    """
    d = _to_decimal(value)
    if not d.is_finite():
        raise CoordinateError(f"coordinate is not a finite number: {value}")
    return d


def quantize6(d: Decimal) -> Decimal:
    """Round to T3D's 6 decimal places, turning an unrepresentable magnitude into a named error.

    Decimal raises `InvalidOperation` when the result would exceed the context precision; left
    alone that surfaces as a bare traceback, which `CLAUDE.md` forbids. Asking the operation
    itself — rather than comparing against a hand-written bound — is what keeps this check exactly
    equal to the real limit, at the one place the limit applies.
    """
    try:
        return d.quantize(_SIX_DP, rounding=ROUND_HALF_UP)
    except InvalidOperation:
        raise CoordinateError(
            f"coordinate {d} needs more precision than a T3D vertex can carry (6 decimal places "
            f"within 28 significant digits); UE1 world coordinates run to ±32768") from None


def clean(value) -> Decimal:
    """Tolerance-snap a coordinate: snap to the nearest integer when within
    CLEAN_EPS of it (kills editor/float noise), else keep it at 6-dp precision.
    Always returns a Decimal so fractional vertices round-trip without binary drift.

    Raises `CoordinateError` on a value that cannot be emitted at all — non-finite, or too large
    to round to 6 decimals — so the caller gets a named exit 2 rather than a
    `decimal.InvalidOperation` traceback out of the formatter.
    """
    d = _guard(value)
    nearest = d.to_integral_value(rounding=ROUND_HALF_UP)
    if abs(d - nearest) <= CLEAN_EPS:
        return nearest
    return quantize6(d)


def snap(value) -> int:
    """Snap a coordinate to the nearest integer grid point; vertex emission uses `clean` instead,
    so genuine fractions survive.

    **No production caller today** — `grep -rn '\bsnap(' uedctl/` finds only this definition and
    its tests. It was written for selection/box math that is inherently integer (builder boxes,
    INSIDE prediction), which has since moved elsewhere. Kept, not deleted, because it is the
    natural integer counterpart to `clean` on the write path and deleting it is a separate call;
    it goes through the same `_guard` precisely so the two entry points cannot drift apart if a
    caller reappears. See the board for the delete-or-keep question."""
    return int(_guard(value).to_integral_value(rounding=ROUND_HALF_UP))


def fmt_vertex(value) -> str:
    """Zero-padded, signed, 6-decimal coordinate as UnrealEd emits them. Genuine
    fractions are preserved (cleaned of sub-grid noise first)."""
    d = clean(value)
    sign = "-" if d < 0 else "+"
    q = quantize6(abs(d))
    int_part = int(q)
    frac_digits = f"{q - int_part:.6f}"[2:]      # "0.500000" -> "500000"
    return f"{sign}{int_part:05d}.{frac_digits}"


def fmt_loc(value) -> str:
    """Location coordinate: 6-decimal with no sign padding; fractions preserved."""
    d = clean(value)
    if d == 0:                       # avoid a "-0.000000" from a tiny negative clean
        d = Decimal(0)
    return f"{d:.6f}"


def quote_group(value: str) -> str:
    """Always quote a Group value so multi-group lists survive import/paste."""
    return '"' + value.strip('"') + '"'


def _vec_line(kind: str, v: Vec3) -> str:
    return f"         {kind:<8} {fmt_vertex(v[0])},{fmt_vertex(v[1])},{fmt_vertex(v[2])}"


def emit_polygon(p: Polygon) -> str:
    hdr = "         Begin Polygon"
    if p.item:
        hdr += f" Item={p.item}"
    if p.texture:
        hdr += f" Texture={p.texture}"
    if p.flags:
        hdr += f" Flags={p.flags}"
    out = [hdr]
    if p.origin is not None:
        out.append(_vec_line("Origin", p.origin))
    if p.normal is not None:
        out.append(_vec_line("Normal", p.normal))
    if p.texture_u is not None:
        out.append(_vec_line("TextureU", p.texture_u))
    if p.texture_v is not None:
        out.append(_vec_line("TextureV", p.texture_v))
    if p.pan is not None:
        out.append(f"         Pan      U={p.pan[0]} V={p.pan[1]}")
    for v in p.vertices:
        out.append(_vec_line("Vertex", v))
    out.append("         End Polygon")
    return "\n".join(out)


def emit_brush(b: Brush) -> str:
    out = [f"    Begin Brush Name={b.model_name}", "       Begin PolyList"]
    for p in b.polys:
        out.append(emit_polygon(p))
    out += ["       End PolyList", "    End Brush"]
    return "\n".join(out)


def emit_actor(a: Actor) -> str:
    out = [f"Begin Actor Class={a.cls} Name={a.name}"]
    brush_ref = None
    for key, val in a.props:
        if key == "Brush":
            # The actor's Brush=Model'…' reference MUST be emitted AFTER the inline
            # Begin Brush…End Brush block (held back here, re-emitted below). Emitted
            # in prop order — i.e. BEFORE the block — the actor binds to a not-yet-
            # defined model and the resulting brush has no usable bound: it renders,
            # but ACTOR SELECT INSIDE silently skips it. Matches the editor's own
            # EDIT COPY ordering. Verified: before-block => unselectable via EDIT
            # PASTE; after-block => selectable. (MAP IMPORTADD is unselectable
            # regardless — a separate, verb-level limitation.)
            brush_ref = val
            continue
        if key == "Location":
            # Location is owned by a.location (single source of truth); never emit a props
            # copy — a stray one (e.g. from the legacy `actor set` stub) would double-emit.
            continue
        if key in ("MainScale", "PostScale"):
            # Owned by a.main_scale/a.post_scale (single source of truth), re-emitted below;
            # never emit a props copy or the typed field would double-emit (spec §10).
            continue
        if key == "Group":
            out.append(f"    {key}={quote_group(val)}")
        else:
            out.append(f"    {key}={val}")
    if a.location is not None:
        x, y, z = a.location
        out.append(f"    Location=(X={fmt_loc(x)},Y={fmt_loc(y)},Z={fmt_loc(z)})")
    # Re-emit the typed scale fields (byte-match the editor's serialization — spike §1), after
    # Location, non-None only (a point actor with no scale prop emits nothing here).
    if a.main_scale is not None:
        from .transform import emit_fscale
        out.append(f"    MainScale={emit_fscale(a.main_scale)}")
    if a.post_scale is not None:
        from .transform import emit_fscale
        out.append(f"    PostScale={emit_fscale(a.post_scale)}")
    if a.brush is not None:
        out.append(emit_brush(a.brush))
    if brush_ref is not None:
        out.append(f"    Brush={brush_ref}")
    out.append(f'    Name="{a.name}"')
    out.append("End Actor")
    return "\n".join(out)


def inject_carriers(block: str, actor: Actor) -> str:
    """Insert the `// uedctl-folder:` / `// uedctl-labels:` carrier lines inside an actor T3D `block`
    (right after the `Begin Actor` header), from the actor's `folder`/`labels` sidecar fields — the
    on-the-wire form generators and `actor show` use so `actor add` reads organization back. Returns
    `block` unchanged when neither is set. This is the SOLE generator carrier-emit seam; it is NEVER
    applied to `canonical_actor_t3d` / `emit_map` (the trunk body + editor-import map stay carrier-free)."""
    carriers = []
    if actor.folder is not None:
        from .folderlib import format_folder_carrier
        carriers.append(format_folder_carrier(actor.folder))
    if actor.labels:
        from .labellib import format_labels_carrier
        carriers.append(format_labels_carrier(actor.labels))
    if not carriers:
        return block
    lines = block.split("\n")                    # lines[0] is `Begin Actor …`
    return "\n".join([lines[0], *carriers, *lines[1:]])


def emit_actor_t3d(actor: Actor) -> str:
    """Single-actor T3D string for generators (brush build, actor build, brush intersect/deintersect),
    INCLUDING the folder/labels carriers when the actor carries them — the one place generator carriers
    are emitted (see `inject_carriers`). NOT `emit_actor`/`emit_map`/`canonical_actor_t3d`."""
    return inject_carriers(emit_actor(actor), actor) + "\n"


def emit_brush_block(b: Brush) -> str:
    """Raw `Begin PolyList … End PolyList` block — the format `BRUSH IMPORT` consumes.
    Do NOT use for model-side actor emit; use `emit_brush` for that."""
    out = ["Begin PolyList"]
    for p in b.polys:
        out.append(emit_polygon(p))
    out.append("End PolyList")
    return "\n".join(out) + "\n"


def emit_map(actors: list[Actor]) -> str:
    """Wrap actors in a Begin Map…End Map block for MAP IMPORTADD."""
    body = "\n".join(emit_actor(a) for a in actors)
    return f"Begin Map\n{body}\nEnd Map\n"

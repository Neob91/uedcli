"""Per-surface (polygon) content edits: flags, texture, pan. Pure model-side transform — no
editor (per-poly `PolyFlags`/`Texture`/`Pan` survive the `apply` paste path, quirks-verified).
See dev/docs/specs/2026-06-19-uedctl-surface-flags-texturing-design.md."""
from __future__ import annotations

from .geometry import validate_brush
from .model import Actor, Level
from .query import PF_NAMES, resolve_actor_name

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
    uedctl's name allocation never produce a colon), so the split-on-last-colon is defensive and the
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
    omit it (uedctl convention, `unrealed/quirks.md` "T3D format": never required, even when
    the object genuinely has one) but this only validates format, not style."""
    parts = ref.split(".")
    if len(parts) < 2:
        raise ValueError(f"texture ref must be qualified (Package.Name), got {ref!r}")
    if parts[0] == "MyLevel":
        raise ValueError(f"texture ref cannot be MyLevel.* (not materializable): {ref!r}")
    return parts[0]


def apply_surface_edit(level: Level, targets: list[str], *, texture_ref: str | None = None,
                       add_flags: list[str] | None = None, remove_flags: list[str] | None = None,
                       pan_to: tuple[int, int] | None = None,
                       pan_by: tuple[int, int] | None = None) -> list[str]:
    """Pure transform: resolve `targets` to a unique `(brush, poly_index)` set (so an
    overlapping/duplicate target edits each surface once — critical for `pan_by`, which would
    otherwise double-apply), then mutate each selected poly's flags/texture/pan in place.
    Returns the sorted touched brush names. All-or-nothing: every target is resolved (raising
    `ValueError` naming the first offender) before anything is mutated."""
    if (texture_ref is None and not add_flags and not remove_flags
            and pan_to is None and pan_by is None):
        raise ValueError("brush poly set: at least one of --texture/--add-flag/--remove-flag/"
                         "--pan-to/--pan-by is required")
    if texture_ref is not None:
        parse_texture_ref(texture_ref)            # validate format before mutating anything
    add_bits = encode_flags(add_flags) if add_flags else 0
    remove_bits = encode_flags(remove_flags) if remove_flags else 0

    selected: dict[str, set[int]] = {}
    for token in targets:
        brush_name, selector = parse_poly_selector(token)
        try:
            brush_name = resolve_actor_name(level, brush_name)
        except KeyError:
            raise ValueError(f"unknown brush {brush_name!r}")
        indices = resolve_polys(selector, level.actors[brush_name], brush_name=brush_name)
        selected.setdefault(brush_name, set()).update(indices)

    for brush_name, indices in selected.items():
        brush = level.actors[brush_name].brush
        for idx in indices:
            poly = brush.polys[idx]
            if add_bits or remove_bits:
                poly.flags = (poly.flags | add_bits) & ~remove_bits
            if texture_ref is not None:
                poly.texture = texture_ref
            if pan_to is not None:
                poly.pan = pan_to
            elif pan_by is not None:
                base = poly.pan or (0, 0)
                poly.pan = (base[0] + pan_by[0], base[1] + pan_by[1])
        validate_brush(brush)
    return sorted(selected)

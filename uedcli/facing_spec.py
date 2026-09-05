"""`brush poly find --facing` grammar: component predicates on a face's VISIBLE unit normal.

A face's visible normal `(nx, ny, nz)` is a point on the unit sphere (see `query.visible_normal`,
which resolves polarity for subtract brushes). This module parses the `--facing` spec into a
`FacingSpec` and matches normals against it; it also names a normal's polarity-free `orientation`
(flat/wall/ramp) and its polarity-aware `role` (floor/ceiling/None).

Grammar (one CLI param; `;` = AND, `,` = OR within one axis, `..` = inclusive range):

    TERM[;TERM…]
      TERM   = PRESET | AXIS:SPEC
      PRESET = flat | wall | ramp | floor | ceiling
      AXIS   = nx | ny | nz            components of the visible unit normal, each in [-1, 1]
      SPEC   = v | lo..hi | v[,v…]     a bare v matches within EPS; lo..hi is an inclusive band

A parse failure raises `ValueError` naming the offending token (the dispatch layer turns it into a
clean exit 2). A syntactically valid spec that matches nothing is NOT an error — it is a legal query
returning zero faces.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

# Preset cutoffs, stated as an angle for uniform meaning, then used as a |nz| component cut.
_THETA_WALL = math.radians(5)      # within 5° of horizontal ⇒ wall (vertical surface)
_THETA_FLAT = math.radians(5)      # within 5° of vertical ⇒ flat (horizontal surface)
_S = math.sin(_THETA_WALL)         # |nz| < _S ⇒ wall
_C = math.cos(_THETA_FLAT)         # |nz| ≥ _C ⇒ flat
_EPS = 0.05                        # a bare `nz:0` scalar matches within this COMPONENT tolerance

_AXES = {"nx": 0, "ny": 1, "nz": 2}

# A band on one component: (lo, hi, lo_inclusive, hi_inclusive). ±inf for the open outer edges.
_Band = tuple[float, float, bool, bool]

# Presets expand to OR-ed bands on nz (axis 2). Half-open so wall/ramp/flat partition [-1,1] with no
# boundary overlap: wall excludes ±_S (→ ramp owns them); ramp excludes ±_C (→ flat owns them).
_PRESETS: dict[str, tuple[int, tuple[_Band, ...]]] = {
    "wall":    (2, ((-_S, _S, False, False),)),
    "ramp":    (2, ((_S, _C, True, False), (-_C, -_S, False, True))),
    "flat":    (2, ((_C, math.inf, True, True), (-math.inf, -_C, True, True))),
    "floor":   (2, ((_C, math.inf, True, True),)),
    "ceiling": (2, ((-math.inf, -_C, True, True),)),
}


@dataclass(frozen=True)
class FacingSpec:
    """A parsed `--facing` predicate: AND across terms, each an OR of bands on one normal axis."""
    terms: tuple[tuple[int, tuple[_Band, ...]], ...]


def _parse_band(alt: str, term: str) -> _Band:
    """One SPEC alternative → a band. `lo..hi` is an inclusive range; a bare `v` is `v ± _EPS`."""
    if ".." in alt:
        parts = alt.split("..")
        if len(parts) != 2 or not parts[0].strip() or not parts[1].strip():
            raise ValueError(f"brush poly find --facing: malformed range {alt!r} in {term!r} "
                             f"(expected lo..hi)")
        lo, hi = (_parse_float(p, term) for p in parts)
        return (lo, hi, True, True)
    v = _parse_float(alt, term)
    return (v - _EPS, v + _EPS, True, True)


def _parse_float(text: str, term: str) -> float:
    try:
        return float(text.strip())
    except ValueError:
        raise ValueError(f"brush poly find --facing: {text.strip()!r} in {term!r} is not a number")


def parse_facing_spec(text: str) -> FacingSpec:
    """Parse a `--facing` spec string into a `FacingSpec`. Raises `ValueError` naming the offending
    token on any malformed term, unknown axis, or unknown preset."""
    terms: list[tuple[int, tuple[_Band, ...]]] = []
    for raw in text.split(";"):
        term = raw.strip()
        if not term:
            raise ValueError(f"brush poly find --facing: empty term in {text!r} "
                             f"(a stray or trailing ';')")
        if ":" not in term:
            preset = _PRESETS.get(term.casefold())
            if preset is None:
                raise ValueError(f"brush poly find --facing: unknown preset {term!r} "
                                 f"(expected one of {', '.join(sorted(_PRESETS))} or AXIS:SPEC)")
            terms.append(preset)
            continue
        axis_str, spec_str = term.split(":", 1)
        axis = _AXES.get(axis_str.strip().casefold())
        if axis is None:
            raise ValueError(f"brush poly find --facing: unknown axis {axis_str.strip()!r} in "
                             f"{term!r} (expected nx, ny, or nz)")
        alts = spec_str.split(",")
        if not spec_str.strip() or any(not a.strip() for a in alts):
            raise ValueError(f"brush poly find --facing: empty value in {term!r}")
        terms.append((axis, tuple(_parse_band(a, term) for a in alts)))
    return FacingSpec(tuple(terms))


def _in_band(x: float, band: _Band) -> bool:
    lo, hi, lo_incl, hi_incl = band
    return (x >= lo if lo_incl else x > lo) and (x <= hi if hi_incl else x < hi)


def match_facing(normal: tuple[float, float, float], spec: FacingSpec) -> bool:
    """True iff `normal` satisfies every term (AND); a term matches if the component lands in any of
    its bands (OR)."""
    return all(any(_in_band(normal[axis], b) for b in bands) for axis, bands in spec.terms)


def orientation(normal: tuple[float, float, float]) -> str:
    """Polarity-free surface orientation: `flat` (horizontal), `wall` (vertical), or `ramp`."""
    az = abs(normal[2])
    if az < _S:
        return "wall"
    if az < _C:
        return "ramp"
    return "flat"


def role(normal: tuple[float, float, float]) -> str | None:
    """Polarity-aware role: `floor` (up-facing), `ceiling` (down-facing), or None (neither)."""
    if normal[2] >= _C:
        return "floor"
    if normal[2] <= -_C:
        return "ceiling"
    return None

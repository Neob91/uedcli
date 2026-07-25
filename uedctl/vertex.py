"""Model-side vertex editing — MOVE ONLY.

A brush stores its vertices PER-POLYGON (no shared vertex table), so a single
brush corner appears once in each face that touches it (a cube corner: 3 copies).
`weld_vertices` groups those copies back into corners by cleaned coordinate;
`move_vertices` moves a corner by rewriting EVERY copy at once, so the solid stays
watertight. Selection is purely by coordinate — vertices have no name.

Adding or deleting a vertex is intentionally NOT offered: it would open/over-close
the solid and is the easy way to crash UnrealEd's CSG. Every move is validated
(`geometry.validate_brush`) before it is returned, so a move that would collapse a
face or push it non-planar raises here, never reaching the editor. Mirrors `clip.py`:
mutate the PolyList model-side, validate, then write the transformed level back through
the trunk `LevelSource` seam. Coordinates are the brush's own local vertex space; the
caller converts world→local (subtract Location) before calling.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from decimal import Decimal

from .emit import clean
from .geometry import validate_brush
from .model import Brush, Vec3


@dataclass(frozen=True)
class WeldedVertex:
    """One brush corner: its cleaned local coordinate and every (poly, vertex)
    slot that holds a copy of it."""
    coord: Vec3
    refs: tuple[tuple[int, int], ...]


def _clean3(v) -> Vec3:
    return (clean(v[0]), clean(v[1]), clean(v[2]))


def _dec(value) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def weld_vertices(brush: Brush) -> list[WeldedVertex]:
    """Group the brush's per-poly vertices into corners by cleaned coordinate,
    in first-appearance order. Each corner carries the (poly_idx, vertex_idx) of
    every copy."""
    groups: dict[Vec3, list[tuple[int, int]]] = {}
    for pi, poly in enumerate(brush.polys):
        for vi, v in enumerate(poly.vertices):
            groups.setdefault(_clean3(v), []).append((pi, vi))
    return [WeldedVertex(coord=coord, refs=tuple(refs)) for coord, refs in groups.items()]


def move_vertices(brush: Brush, selectors, *, to=None, by=None) -> Brush:
    """Move one or more corners, selected by local coordinate, and return a NEW
    validated brush. Exactly one of `to` (absolute target) / `by` (delta) must be
    given. `to` accepts a SINGLE selector — moving several corners to one point
    would collapse them. Every poly-vertex sharing a selected corner moves together.

    Raises ValueError for bad arguments or a selector that matches no corner, and
    GeometryError if the resulting brush is degenerate/non-planar (so an illegal
    edit never reaches the editor)."""
    if (to is None) == (by is None):
        raise ValueError("move_vertices needs exactly one of to= / by=")
    if to is not None and len(selectors) != 1:
        raise ValueError(
            f"--to moves a single corner, got {len(selectors)} --at selectors; moving "
            f"several corners to one point would collapse them — use --by for a delta"
        )

    welds = weld_vertices(brush)
    by_coord = {w.coord: w for w in welds}
    resolved: list[tuple[WeldedVertex, Vec3]] = []
    seen: set[Vec3] = set()
    for sel in selectors:
        key = _clean3(sel)
        group = by_coord.get(key)
        if group is None:
            corners = [tuple(str(c) for c in w.coord) for w in welds]
            raise ValueError(
                f"no brush vertex at {tuple(str(c) for c in key)}; corners are {corners}"
            )
        if key in seen:
            raise ValueError(f"duplicate --at selector for corner {tuple(str(c) for c in key)}")
        seen.add(key)
        if to is not None:
            new = tuple(_dec(c) for c in to)
        else:
            new = tuple(group.coord[i] + _dec(by[i]) for i in range(3))
        resolved.append((group, new))

    result = copy.deepcopy(brush)
    for group, new in resolved:
        for pi, vi in group.refs:
            result.polys[pi].vertices[vi] = new
    validate_brush(result)
    return result

"""Model-side vertex snap — round near-grid LOCAL vertex components to a grid.

Real/imported brushes carry sub-unit off-grid noise on coordinates that were meant to be on-grid
(a corner at `x=-62.5455` that should read `-64`), and off-grid coordinates are the main cause of
BSP holes. `snap_brush` rounds each poly vertex's LOCAL components to the nearest multiple of `grid`
when within `tolerance` of it, and leaves a component farther than `tolerance` from the grid in place
— so genuinely off-grid geometry (an angled/rotated/curved brush) keeps its intended angles and only
the near-grid float noise is cleaned. It is per-axis and per-vertex independent: a slant vertex keeps
its off-grid axis and snaps the near-grid ones.

`grid`/`tolerance` are `Decimal`, not `float`, and the vertices are `Decimal` — so a snapped
component becomes the EXACT grid value and re-emits unchanged (idempotent); a float grid would
reintroduce the binary-float noise the verb exists to remove. Because every copy of a shared brush
corner gets the identical rule, near-grid copies that had drifted apart both land on the same value —
snapping RE-WELDS them (a consequence, not extra code). The result is validated
(`geometry.validate_brush`), so a snap that pushes a face non-planar/degenerate raises rather than
emitting broken geometry. Mirrors `vertex.move_vertices`' deepcopy→mutate→validate shape.
"""
from __future__ import annotations

import copy
import math
from decimal import Decimal

from .geometry import validate_brush
from .model import Brush, Vec3


def _dec(value) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _snap_component(c: Decimal, *, grid: Decimal, tolerance: Decimal) -> Decimal:
    # Round half toward +inf via floor(x + 0.5) — the deliberate non-banker's rule matching
    # `cli/commands/brush/build.py` `_revolve_sweep`; `round()` (banker's) is NOT used.
    g = grid * math.floor(c / grid + Decimal("0.5"))
    return g if abs(c - g) <= tolerance else c


def _snap_vertex(v: Vec3, *, grid: Decimal, tolerance: Decimal) -> Vec3:
    return tuple(_snap_component(_dec(c), grid=grid, tolerance=tolerance) for c in v)


def snap_brush(brush: Brush, *, grid: Decimal, tolerance: Decimal) -> Brush:
    """Return a NEW brush with each LOCAL vertex component within `tolerance` of a `grid` multiple
    rounded to it (per-axis, per-vertex). Raises `GeometryError` if the snap makes any face
    non-planar/degenerate."""
    result = copy.deepcopy(brush)
    for poly in result.polys:
        poly.vertices = [_snap_vertex(v, grid=grid, tolerance=tolerance) for v in poly.vertices]
    validate_brush(result)
    return result

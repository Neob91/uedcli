"""Brush geometry validation — degenerate geometry crashes UnrealEd's CSG
(at MAP REBUILD/bspBuild). Validate the resulting brush in the text model
BEFORE materializing, and error out so degenerate geometry never reaches the
editor. Validation runs on the EMITTED integer coords (post grid-snap), since a
sub-grid move can collapse a vertex onto its neighbor only after snapping.

Tolerances default conservatively; tune from the Task 0b spike.
"""
from __future__ import annotations

from .model import Brush
from .emit import clean

# From Task 0b spike. COINCIDE_TOL=0 means exact-equal post-clean. PLANAR_TOL is
# the max allowed distance of any vertex from the face's best-fit plane.
COINCIDE_TOL = 0.0
PLANAR_TOL = 0.5


class GeometryError(ValueError):
    pass


def _clean3(v):
    # Validate on the SAME values emit.clean will write: sub-grid noise snaps to
    # the grid, but genuine fractions are preserved (so a planar slanted face is
    # not pushed off-plane by grid-snapping — the old cone-clip failure mode).
    return (clean(v[0]), clean(v[1]), clean(v[2]))


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a, b):
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _norm(a):
    return _dot(a, a) ** 0.5


def validate_brush(brush: Brush, *, planar_fatal: bool = True) -> list[str]:
    """Validate all polygons in brush after grid-snap.

    Raises GeometryError with a precise diagnostic on the first failing polygon. Within-polygon
    coincidence is the only fault checked — vertices shared across different polygons of a brush
    (cube corners) are normal and not flagged.

    With `planar_fatal=False` a non-planar poly is NOT fatal: its diagnostic is collected and
    returned instead of raised, so a caller can build it and warn. `materialize` uses this because
    the editor itself accepts non-planar faces (it built the retail maps that carry them) and
    `doctor` only WARNs on them (owner ruling 2026-08-23). Coincident/degenerate faults still
    raise either way — they genuinely break the editor's CSG. Returns the non-fatal warnings (empty
    unless `planar_fatal=False` caught one)."""
    warnings: list[str] = []
    for pi, poly in enumerate(brush.polys):
        cleaned = [_clean3(v) for v in poly.vertices]
        _check_coincident(brush, pi, cleaned)
        # Plane/degeneracy math is geometric-tolerance work — run it in float.
        vf = [(float(a), float(b), float(c)) for a, b, c in cleaned]
        normal = _check_degenerate(brush, pi, vf)
        try:
            _check_planar(brush, pi, vf, normal)
        except GeometryError as exc:
            if planar_fatal:
                raise
            warnings.append(str(exc))
    return warnings


def _check_coincident(brush, pi, verts) -> None:
    # Exact equality on CLEANED Decimal coords: two corners coincide iff they snap
    # to the same point; genuine sub-grid-distinct corners (0.4 apart) do not.
    for i in range(len(verts)):
        for j in range(i + 1, len(verts)):
            if verts[i] == verts[j]:
                raise GeometryError(
                    f"{brush.model_name} poly {pi}: vertices {i} and {j} "
                    f"coincide at {verts[i]} after grid snap"
                )


def _check_degenerate(brush, pi, verts):
    """Check for degenerate polygon; return a non-zero plane normal on success."""
    distinct = list(dict.fromkeys(verts))
    if len(distinct) < 3:
        raise GeometryError(
            f"{brush.model_name} poly {pi}: degenerate — only "
            f"{len(distinct)} distinct vertices"
        )
    # Find a non-collinear triple to define the plane normal.
    base = distinct[0]
    e1 = _sub(distinct[1], base)
    for k in range(2, len(distinct)):
        n = _cross(e1, _sub(distinct[k], base))
        if _norm(n) > 1e-6:
            return n
    raise GeometryError(
        f"{brush.model_name} poly {pi}: degenerate — all vertices collinear"
    )


def _check_planar(brush, pi, verts, normal) -> None:
    nlen = _norm(normal)
    base = verts[0]
    for i, v in enumerate(verts):
        dist = abs(_dot(_sub(v, base), normal)) / nlen
        if dist > PLANAR_TOL:
            raise GeometryError(
                f"{brush.model_name} poly {pi}: non-planar — vertex {i} is "
                f"{dist:.3f} off the face plane (tol {PLANAR_TOL})"
            )

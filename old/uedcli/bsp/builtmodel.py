"""Locate BSP defects in the built `Model` of a saved `.dx` — the built-model health check.

One located defect class (spec `bsp-issue-ground-truth-detector-d0-d1` §1, P0 spike GO 2026-08-03):
  - invisible wall  = a near-zero-area BSP node (a phantom/sliver node the build kept).

The built `Model` is parsed by the shipping byte-exact reader `native.umodel.parse_model_body`
(itself promoted from the same spike). The located analysis reuses `doctor`'s `Finding`/`Severity`
and its engine-faithful zero-area constant so output matches the static `level doctor`.
"""
from __future__ import annotations

from .. import doctor
from ..doctor import Finding, Severity
from ..native import pkg_write, umodel
from ..native.codec import read_ci

_RF_HAS_STACK = 0x02000000                         # export carries an FStateFrame before its body


def load_model_from_dx(dx_bytes: bytes) -> umodel.Model:
    """Parse the level BSP `Model` (the largest `Model`-class export) out of a saved `.dx`.
    Skips the export's `FStateFrame` when `RF_HasStack` is set (some editor-written Model exports
    carry one — mapimport `_skip_state_frame`). Raises on a map with no Model export."""
    pp = pkg_write.parse_package(dx_bytes)
    best: int | None = None
    for i, e in enumerate(pp.exports):
        nm = pp.names[e["nm"]] if 0 <= e["nm"] < len(pp.names) else ""
        if (pp.class_of_export(i) == "Model" or nm == "Model") and e["ssize"] > 0:
            if best is None or e["ssize"] > pp.exports[best]["ssize"]:
                best = i
    if best is None:
        raise ValueError("no Model export found in the saved map")
    e = pp.exports[best]
    soff, ssize = e["soff"], e["ssize"]
    start = soff
    if e["flags"] & _RF_HAS_STACK:
        node, p = read_ci(dx_bytes, soff)
        _state_node, p = read_ci(dx_bytes, p)
        p += 8 + 4                                  # ProbeMask (u64) + LatentAction (u32)
        if node != 0:
            _off, p = read_ci(dx_bytes, p)
        start = p
    return umodel.parse_model_body(dx_bytes, start, soff + ssize - start)


def _node_poly(model: umodel.Model, node) -> list[tuple[float, float, float]] | None:
    """The node's world-space polygon via iVertPool → Verts → Points, or None if any index is
    out of bounds (a corrupt/unused node — skip it rather than raise)."""
    lo = node.i_vert_pool
    if lo < 0 or lo + node.num_vertices > len(model.verts):
        return None
    pts = []
    for j in range(node.num_vertices):
        vi = model.verts[lo + j].i_vertex
        if not 0 <= vi < len(model.points):
            return None
        x, y, z = model.points[vi]
        pts.append((float(x), float(y), float(z)))
    return pts


def _invisible_walls(model: umodel.Model) -> list[Finding]:
    """Near-zero-area nodes — phantom/sliver nodes that block where nothing renders. Uses the
    engine's own zero-area predicate (`doctor.ZERO_NORMAL_SQ` on the summed fan-normal = 2·area)."""
    out: list[Finding] = []
    for ni, node in enumerate(model.nodes):
        if node.num_vertices < 3:
            continue
        pts = _node_poly(model, node)
        if pts is None:
            continue
        n = doctor._fan_normal(pts)
        area_sq = doctor._dot(n, n)
        if area_sq < doctor.ZERO_NORMAL_SQ:
            out.append(Finding(
                severity=Severity.WARN, category="degenerate", brush="(built BSP)",
                coord=doctor._centroid(pts),
                message=f"BSP node {ni} (surf {node.i_surf}) has ~zero area "
                        f"(|2·area|²={area_sq:.2e} < {doctor.ZERO_NORMAL_SQ:.0e})",
                symptom="phantom/sliver node — an invisible wall (collision where nothing renders)",
                fix="find the near-degenerate brush geometry that produced this node and give it "
                    "real area (or remove it)"))
    return out


def analyze_built(model: umodel.Model) -> list[Finding]:
    """Every located built-model defect, in `doctor`'s stable report order."""
    return doctor.sort_findings(_invisible_walls(model))

"""P0 feasibility-gate pins for the BSP-issue detector (`level doctor --built`).

Content-independent: parses a committed 8602-byte golden — the level `Model1`
body of the retail `99_Endgame4.dx` (smallest real built level BSP in the corpus)
— and pins the facts the go/no-go rests on. See
`spikes/2026-06-25-umodel-serialize-format.md` (P0 verdict section).

The retail-corpus sweep lives in `test_umodel_serialize.py` (needs the gitignored
install maps); this file needs none.
"""
from __future__ import annotations

import math
from pathlib import Path

import umodel_parser as P
import umodel_serialize as S

_GOLDEN = Path(__file__).parent / "fixtures" / "endgame4_model1.bin"

# Real UE1 EPolyFlags (from uedcli/doctor.py, query.py) — NOT the umodel_parser.py
# module-level PF_PORTAL=0x0080, which is actually PF_FakeBackdrop (see the finding
# in the spike doc; the raw poly_flags u32 itself parses correctly).
PF_NOTSOLID = 0x00000008
PF_SEMISOLID = 0x00000020
PF_PORTAL = 0x04000000


def _model() -> P.ParsedModel:
    data = _GOLDEN.read_bytes()
    return P.parse_model_serial(data, 0, len(data))


def _node_poly(m: P.ParsedModel, n: P.BspNode) -> list[tuple[float, float, float]]:
    lo = n.i_vert_pool
    return [m.points[m.verts[lo + j].i_vertex] for j in range(n.num_vertices)]


def test_it_parses_all_six_arrays_from_a_built_model() -> None:
    """P0-a: Vectors, Points, Nodes, Surfs, Verts, Leaves all populate and parse."""
    m = _model()
    assert (len(m.vectors), len(m.points), len(m.nodes), len(m.surfs),
            len(m.verts), len(m.leaves)) == (13, 73, 46, 31, 741, 17)
    assert (m.num_zones, m.num_shared_sides) == (2, 114)


def test_it_reconstructs_every_node_poly_planar_on_its_node_plane() -> None:
    """P0-b1: iVertPool -> Verts -> Points yields real world-space polys that lie on
    the node's own plane (max deviation ~float precision) — geometry is lossless."""
    m = _model()
    reconstructed = 0
    worst_dev = 0.0
    for n in m.nodes:
        if n.num_vertices < 3:
            continue
        pts = _node_poly(m, n)
        px, py, pz, pw = n.plane
        worst_dev = max(worst_dev, max(abs(px * x + py * y + pz * z - pw) for x, y, z in pts))
        reconstructed += 1
    assert reconstructed == 46
    assert worst_dev < 0.5, f"node polys not planar on their plane: {worst_dev}"


def test_it_finds_every_node_referenced_vert_in_bounds() -> None:
    """The iVertex-out-of-bounds verts (seen on large maps) are an UNUSED tail: every
    vert reachable from a node's iVertPool range indexes a real Point."""
    m = _model()
    for n in m.nodes:
        for j in range(n.i_vert_pool, n.i_vert_pool + n.num_vertices):
            assert 0 <= m.verts[j].i_vertex < len(m.points)


def test_it_computes_node_areas_for_near_zero_detection() -> None:
    """Invisible-wall viable row: node poly area is computable, so near-zero-area
    nodes are locatable. This golden has none; the computation must still run."""
    m = _model()
    areas = []
    for n in m.nodes:
        if n.num_vertices < 3:
            continue
        pts = _node_poly(m, n)
        nx = ny = nz = 0.0
        k = len(pts)
        for i in range(k):
            x0, y0, z0 = pts[i]
            x1, y1, z1 = pts[(i + 1) % k]
            nx += (y0 - y1) * (z0 + z1)
            ny += (z0 - z1) * (x0 + x1)
            nz += (x0 - x1) * (y0 + y1)
        areas.append(0.5 * math.sqrt(nx * nx + ny * ny + nz * nz))
    assert len(areas) == 46
    assert min(areas) > 1.0  # no degenerate node in this clean retail map
    assert len([a for a in areas if a < 1.0]) == 0


def test_it_filters_surfs_by_solidity_polyflags() -> None:
    """Fall-through viable row: per-surf PolyFlags parse as a raw u32, filterable by
    the real UE1 solidity bits."""
    m = _model()
    # every poly_flags is a plain u32 (no parse artifact in the high word)
    assert all(0 <= s.poly_flags <= 0xFFFFFFFF for s in m.surfs)
    notsolid = [i for i, s in enumerate(m.surfs) if s.poly_flags & PF_NOTSOLID]
    portal = [i for i, s in enumerate(m.surfs) if s.poly_flags & PF_PORTAL]
    # the filter runs and returns concrete index sets (this golden is all-solid)
    assert notsolid == []
    assert portal == []


def test_it_round_trips_the_golden_byte_exact() -> None:
    """The parse is faithful: re-serializing reproduces the original bytes."""
    data = _GOLDEN.read_bytes()
    ok, diff = S.validate_model(data, 0, len(data))
    assert ok, f"serialize mismatch at {diff}"

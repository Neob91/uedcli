"""Pin the `Mesh`/`LodMesh` vertex→world placement formula found by spike
`2026-09-07-mesh-origin-rotorigin-transform` (uedcli `dev/docs/rules/spikes.md` "pin the finding, or
it rots"). The formula, derived from UE1 v200's `UMesh::GetFrame` (`Source/Engine/Src/UnMesh.cpp`,
`fgsfdsfgs/UE1`) and cross-checked against a literal transliteration of its `FCoords` machinery:

    world = Location + PrePivot + R · Ro · diag(Scale · DrawScale) · (v - Origin)

with `R`/`Ro` from the actor's `Rotation` / the mesh's own `RotOrigin`, both via
`uedcli.rotation.euler_to_matrix_uu` (verified to be the SAME per-axis convention `UnMath.h`'s
`FCoords::operator*=(FRotator)` steps use).

Two things are pinned:
1. The closed form (`mesh_vertex_to_world`) agrees with the literal `FCoords`-operator
   transliteration (`mesh_vertex_to_world_literal`) — the algebraic simplification is not a
   hand-math mistake.
2. Applied to the REAL `DeusExDeco.ComputerPublic`/`ComputerSecurity` meshes (committed
   `uned/UED22/DeusExDeco.u`, `rot_origin=(0, 16384, 0)`, a 90-degree yaw — see board item
   `rotorigin-origin-prevalence-probe-mesh-local`), the formula predicts a WORLD footprint 90
   degrees rotated from the mesh-local box at identity actor Rotation, and back to the mesh-local
   orientation when the actor's own Rotation cancels RotOrigin — i.e. RotOrigin is a REAL,
   render-affecting reorientation, not inert data.
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest

_SPIKE_HARNESS = (Path(__file__).resolve().parents[2] / "dev" / "docs" / "spikes" /
                   "2026-09-07-mesh-origin-rotorigin-transform" / "harness")

sys.path.insert(0, str(_SPIKE_HARNESS))
try:
    from mesh_world_transform import mesh_vertex_to_world, mesh_vertex_to_world_literal
finally:
    sys.path.remove(str(_SPIKE_HARNESS))

from uedcli.upackage import load_package
from uedcli import umesh

UED22 = Path(__file__).resolve().parents[2] / "uned" / "UED22"


# ── 1. Closed form vs literal FCoords transliteration ───────────────────────────────────────────

def test_closed_form_matches_literal_fcoords_for_cardinal_rotations():
    """Every angle a multiple of 90 degrees (16384 uu): the two implementations must agree to
    float-noise precision (~1e-9), same as `rotation.euler_to_matrix_uu`'s own cardinal-exact
    guarantee — no ULP drift to hide behind."""
    cardinals = (0, 16384, 32768, 49152)
    v = (37.5, -12.25, 88.0)
    worst = 0.0
    for pitch in cardinals:
        for yaw in cardinals:
            for roll in cardinals:
                kw = dict(mesh_scale=(1.0, 1.0, 1.0), mesh_origin=(0.0, 0.0, 0.0),
                          mesh_rot_origin=(pitch, yaw, roll), actor_location=(100.0, 200.0, 300.0),
                          actor_rotation_uu=(0, 16384, 0), actor_prepivot=(5.0, -5.0, 0.0),
                          draw_scale=1.0)
                a = mesh_vertex_to_world(v, **kw)
                b = mesh_vertex_to_world_literal(v, **kw)
                worst = max(worst, max(abs(a[i] - b[i]) for i in range(3)))
    assert worst < 1e-6, f"cardinal-rotation disagreement {worst}uu — the derivation has a real bug"


def test_closed_form_matches_literal_fcoords_over_random_transforms():
    """Non-cardinal angles: the two implementations may drift by the same float32-table-vs-float64
    ULP noise `rotation.euler_to_matrix_uu` itself documents (up to ~1e-3uu for a genuinely
    non-cardinal multi-axis FRotator) — bound it generously, don't demand exactness."""
    rng = random.Random(7)
    worst = 0.0
    for _ in range(300):
        kw = dict(
            mesh_scale=tuple(rng.uniform(0.1, 4.0) for _ in range(3)),
            mesh_origin=tuple(rng.uniform(-50, 50) for _ in range(3)),
            mesh_rot_origin=tuple(rng.randrange(0, 65536) for _ in range(3)),
            actor_location=tuple(rng.uniform(-2000, 2000) for _ in range(3)),
            actor_rotation_uu=tuple(rng.randrange(0, 65536) for _ in range(3)),
            actor_prepivot=tuple(rng.uniform(-100, 100) for _ in range(3)),
            draw_scale=rng.uniform(0.2, 3.0),
        )
        v = tuple(rng.uniform(-500, 500) for _ in range(3))
        a = mesh_vertex_to_world(v, **kw)
        b = mesh_vertex_to_world_literal(v, **kw)
        worst = max(worst, max(abs(a[i] - b[i]) for i in range(3)))
    assert worst < 5e-2, f"random-transform disagreement {worst}uu exceeds the expected float-noise band"


# ── 2. RotOrigin is a real reorientation, measured on real corpus meshes ───────────────────────

def _computer_mesh(name: str):
    pkg = load_package(str(UED22 / "DeusExDeco.u"))
    for j, e in enumerate(pkg.exports):
        if pkg.names[e["nm"]] == name and pkg.name_of_ref(e["cls"]) == "LodMesh":
            return umesh.parse_mesh(pkg, j)
    pytest.fail(f"{name} LodMesh export not found in the committed uned/UED22/DeusExDeco.u")


@pytest.mark.parametrize("mesh_name", ["ComputerPublic", "ComputerSecurity"])
def test_rot_origin_is_a_cardinal_90_degree_yaw_on_the_real_corpus(mesh_name):
    """Ground the formula in real, committed data (not a synthetic fixture): both computer meshes
    carry `rot_origin=(0, 16384, 0)` — pins the `rotorigin-origin-prevalence-probe-mesh-local`
    board finding against a decoder/corpus drift."""
    m = _computer_mesh(mesh_name)
    assert m.rot_origin == (0, 16384, 0)
    assert m.origin == (0.0, 0.0, 0.0)


@pytest.mark.parametrize("mesh_name", ["ComputerPublic", "ComputerSecurity"])
def test_identity_actor_rotation_swaps_world_xy_footprint_vs_mesh_local(mesh_name):
    """At actor Rotation=identity, RotOrigin's 90-degree yaw must swap the mesh-local X/Y box
    extents in WORLD space — the formula's headline, testable prediction. Both computer meshes have
    a markedly asymmetric mesh-local box (wide X, narrow Y), so a swap is unambiguous."""
    m = _computer_mesh(mesh_name)
    (lx0, ly0, _lz0), (lx1, ly1, _lz1), _valid = m.box
    local_x_span, local_y_span = (lx1 - lx0) * m.scale[0], (ly1 - ly0) * m.scale[1]
    assert local_x_span > 1.5 * local_y_span, "fixture no longer asymmetric enough to test with"

    xs, ys = [], []
    for cx in (lx0, lx1):
        for cy in (ly0, ly1):
            wx, wy, _wz = mesh_vertex_to_world(
                (cx, cy, 0.0), mesh_scale=m.scale, mesh_origin=m.origin,
                mesh_rot_origin=m.rot_origin, actor_location=(0.0, 0.0, 0.0),
                actor_rotation_uu=(0, 0, 0))
            xs.append(wx); ys.append(wy)
    world_x_span, world_y_span = max(xs) - min(xs), max(ys) - min(ys)

    assert world_y_span > 1.5 * world_x_span, (
        f"{mesh_name}: expected the RotOrigin 90deg yaw to swap X/Y "
        f"(mesh-local X={local_x_span:.1f} Y={local_y_span:.1f}; "
        f"world X={world_x_span:.1f} Y={world_y_span:.1f})")
    # and the swap is a clean 90-degree rotation, not just "some" reorientation: spans trade places
    assert world_x_span == pytest.approx(local_y_span, rel=1e-3)
    assert world_y_span == pytest.approx(local_x_span, rel=1e-3)


@pytest.mark.parametrize("mesh_name", ["ComputerPublic", "ComputerSecurity"])
def test_actor_rotation_can_cancel_rot_origin(mesh_name):
    """An actor Rotation of -90deg yaw (the FRotator inverse of RotOrigin's +90deg yaw) must undo
    RotOrigin's reorientation exactly, since `R = Ro^-1` makes `R*Ro = Identity` — the world
    footprint returns to the mesh-local box's own orientation (no swap)."""
    m = _computer_mesh(mesh_name)
    (lx0, ly0, _lz0), (lx1, ly1, _lz1), _valid = m.box
    local_x_span, local_y_span = (lx1 - lx0) * m.scale[0], (ly1 - ly0) * m.scale[1]

    xs, ys = [], []
    for cx in (lx0, lx1):
        for cy in (ly0, ly1):
            wx, wy, _wz = mesh_vertex_to_world(
                (cx, cy, 0.0), mesh_scale=m.scale, mesh_origin=m.origin,
                mesh_rot_origin=m.rot_origin, actor_location=(0.0, 0.0, 0.0),
                actor_rotation_uu=(0, (-m.rot_origin[1]) % 65536, 0))
            xs.append(wx); ys.append(wy)
    world_x_span, world_y_span = max(xs) - min(xs), max(ys) - min(ys)

    assert world_x_span == pytest.approx(local_x_span, rel=1e-3)
    assert world_y_span == pytest.approx(local_y_span, rel=1e-3)

"""Live `actor rotate` parity round-trip on the dx-lum-uned substrate (integration, gated).

Deselected by default (pytest.ini: addopts = -m "not integration"). Run with:
    pytest uedctl/tests/test_rotate_integration.py -m integration -v

Closes the FRotator-convention loop end-to-end: rotate a brush model-side by a NON-cardinal
field (NOT a multiple of 4), drive the editor to capture its WORLD geometry, and confirm the
editor reproduces the SAME world geometry uedctl's `world_vertices` predicts. The editor applies
the stored `Rotation` field to the local PolyList via its GMath integer sine table; uedctl's
`rotation.py` drives the SAME table, so a non-multiple-of-4 field exercises the truncated
`(field>>2)&16383` index that a cardinal 90° field never does — 90°=16384 is a multiple of 4,
so `>>2` is lossless and even float `math.sin` would pass, so a cardinal test CANNOT detect the
table. Parity target ~1e-4uu (table float32 storage + 6-dp emit); the old float path is ~0.07uu
off, measured.

World-geometry readout = the spike's verified DEINTERSECTION capture:
  EDIT PASTE a CSG_Subtract box carrying Rotation (pre-shifted -32uu to cancel paste drift) ->
  MAP REBUILD (engine applies the field to the local PolyList -> world cavity) -> a large
  enclosing builder -> BRUSH FROM DEINTERSECTION -> BRUSH EXPORT = the world geometry. See
  dev/docs/spikes/2026-06-19-group-rotate-exact-parity.md ("DEINTERSECTION world-geometry
  readout") — this test re-runs that exact method live.

Orientation is compared by GEOMETRY (world corners), never the literal UU triple.
"""
import copy
import re
import subprocess
import uuid
from decimal import Decimal

import pytest

from uedctl.builders import cube, make_brush_actor
from uedctl.driver import Driver
from uedctl.emit import emit_map
from uedctl.rotation import world_vertices

pytestmark = pytest.mark.integration

CONTAINER = "dx-lum-uned"
PASTE_DRIFT = 32                       # EDIT PASTE adds +32uu on all axes (quirks.md)
PARITY_TOL = 1e-4                      # table-driven trig floor: float32 table + 6-dp emit
D = Decimal


@pytest.fixture(scope="module")
def driver():
    return Driver(container=CONTAINER)


def _container_path(tag: str) -> str:
    """A unique container-local /work path (the only writable exchange dir; no /repo mount)."""
    return f"/work/rotit_{tag}_{uuid.uuid4().hex}.t3d"


def _write_container_file(path: str, content: str) -> None:
    subprocess.run(["docker", "exec", "-i", CONTAINER, "tee", path],
                   input=content, text=True, capture_output=True, check=True)


def _read_container_file(path: str) -> str:
    return subprocess.run(["docker", "exec", CONTAINER, "cat", path],
                          text=True, capture_output=True, check=True).stdout


def _parse_world_verts(t3d: str) -> list[tuple[float, float, float]]:
    """Unique vertices from a BRUSH EXPORT t3d (the DEINTERSECTION readout)."""
    seen = set()
    for line in t3d.splitlines():
        m = re.match(r"\s*Vertex\s+([-+0-9.]+),([-+0-9.]+),([-+0-9.]+)", line)
        if m:
            seen.add(tuple(round(float(x), 6) for x in m.groups()))
    return sorted(seen)


def _worst_err(predicted, editor) -> float:
    """For each editor corner, the nearest predicted corner (max-norm); worst over all corners."""
    return max(min(max(abs(p[i] - e[i]) for i in range(3)) for p in predicted) for e in editor)


def test_non_cardinal_brush_world_geometry_matches_table_driven_world_vertices(driver):
    """A brush rotated by a NON-multiple-of-4 field: the editor's DEINTERSECTION world geometry
    matches uedctl's table-driven `world_vertices` to ~1e-4uu. This is the test that actually
    exercises the GMath table (a cardinal 90° does not); a residual above the tolerance means a
    sign/index/convention bug, NOT just float32 noise.

    SCOPE/CAVEATS (be honest about what this does and doesn't guard):
    - It is `@pytest.mark.integration`, so the DEFAULT suite does NOT run it — the continuous-parity
      claim (~1e-4uu) is verified only when run against the live container, not in CI. The
      CI-visible guards on the trig itself live in test_rotation.py (truncated-index, proper-rotation
      det=+1, signed handedness).
    - The box is origin-centred (point-inversion symmetric) and corners are matched nearest-neighbour
      (set match, not labelled), so a pure chirality flip whose image coincides with that symmetry
      could slip past THIS assertion alone — which is why the det=+1 / handedness checks in
      test_rotation.py exist as the CI-side sign guard. The convention is independently spike-verified
      (frotator-convention), so this remains defense-in-depth."""
    # ARRANGE — a long-armed (512x64x64) box at the origin carrying a combined non-cardinal
    # Pitch+Roll (BOTH not multiples of 4, so the editor's `>>2` index truncation is in play).
    rot_prop = "(Pitch=4095,Roll=2731)"
    box = make_brush_actor("UedctlRotIT", cube(512, 64, 64, texture="DefaultTexture"),
                           location=(D(0), D(0), D(0)), csg="subtract")
    box.props = [(k, v) for k, v in box.props if k != "Rotation"]
    box.props.append(("Rotation", rot_prop))
    predicted = sorted({tuple(round(c, 6) for c in w) for w in world_vertices(box)})
    assert predicted, "world_vertices must yield the rotated world geometry (precondition)"

    # Pre-shift the pasted box -32uu on all axes so the world cavity after REBUILD is exactly
    # R(field)*localvert at Location origin (cancels EDIT PASTE's +32uu drift).
    shifted = copy.deepcopy(box)
    lx, ly, lz = box.location
    shifted.location = (lx - PASTE_DRIFT, ly - PASTE_DRIFT, lz - PASTE_DRIFT)
    # A 768^3 origin-centred builder, big enough to enclose the rotated cavity on every axis
    # (an undersized builder silently CLIPS pitch/roll results — quirks/spike note).
    builder = make_brush_actor("UedctlBigBuilder",
                               cube(768, 768, 768, texture="DefaultTexture"),
                               location=(D(0), D(0), D(0)), csg="add")

    builder_path = _container_path("builder")
    deint_path = _container_path("deint")
    _write_container_file(builder_path, emit_map([builder]))

    # ACT — the spike's verified paste-carve + DEINTERSECTION capture.
    driver.map_new()
    driver.set_grid(1, 1, 1)
    driver.set_clipboard(emit_map([shifted]))
    driver.edit_paste()
    driver.rebuild()
    driver.brush_import(builder_path)
    driver.exec("BRUSH FROM DEINTERSECTION")
    driver.brush_export(deint_path)
    editor = _parse_world_verts(_read_container_file(deint_path))

    # ASSERT — same 8 corners, matched to ~1e-4uu (and far under the ~0.07uu the old float path gives).
    assert len(editor) == 8, f"expected 8 world corners, got {len(editor)}: {editor}"
    err = _worst_err(predicted, editor)
    assert err <= PARITY_TOL, (
        f"table-driven world_vertices vs editor DEINTERSECTION worst err {err:.6f}uu "
        f"exceeds {PARITY_TOL}uu for Rotation={rot_prop} — GMath table parity is broken")

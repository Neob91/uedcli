"""Regression: the native build's swept-box collision must land where UnrealEd's does.

The native BSP is built by CSG -> coplanar-merge -> ONE from-scratch partition, which (unlike the
editor's incremental `bspBrushCSG`) LEAKS: some solid terminal cells are reached with the live CSG
`outside` propagation reading EMPTY, so the game's swept-box trace (`FBoxLineCheckInfo::BoxLineCheck`
returns at `if Outside` BEFORE the hull read) never lands on them and the pawn sinks / falls through
(spike `80-bspbuild-topology.md`).  `build.rs::bound_leaked_solid_leaves` repairs this by inserting
a solid-bound node at each leaked cell.  This test proves the repair lands the box exactly where the
editor golden does — the acceptance case is the castle floor drop at (0,-250) (the "12-unit sink").

Requires the extension AND the castle acceptance assets (the `_scratch` trunk + the frozen editor
golden `Test_Castle.dx`); skips cleanly otherwise (CI without those assets, or a docs-only change).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from uedcli.tests.conftest import StubClassIndex

IDX = StubClassIndex()          # the offline class resolver `movers.is_mover` needs

uedcli_native = pytest.importorskip("uedcli_native")

_ROOT = Path("/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedcli")
_TRUNK = Path("/home/neob91/Games/LutrisDX/drive_c/DX/LUM/_scratch/castle/uedcli/maps/foobar")
_EDITOR = Path("/home/neob91/Games/LutrisDX/drive_c/DX/Maps/Test_Castle.dx")
_HARNESS = _ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"
_DECON = _ROOT / "dev/docs/spikes/2026-06-27-decontainerize-uedcli/harness"

pytestmark = pytest.mark.skipif(
    not (_TRUNK.exists() and _EDITOR.exists() and _HARNESS.exists()),
    reason="castle acceptance assets (scratch trunk + editor golden) not present",
)


def _load_native_model(tmp_path):
    """Build the castle trunk through the native materialize path, write a .dx, return its path."""
    from uedcli import trunk
    from uedcli.native import materialize as M

    lvl, _ = trunk.read_level(_TRUNK)
    out = tmp_path / "NativeCastle_test.dx"
    M.run_materialize_native(
        class_index=IDX,
        level=lvl, out_path=str(out), overwrite=True, version=68, no_light=True,
        pkg_dirs=[
            "/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Textures",
            "/home/neob91/Games/LutrisDX/drive_c/DX/Textures",
        ],
    )
    return out


def test_castle_floor_box_drop_matches_editor(tmp_path):
    for p in (str(_HARNESS), str(_DECON)):
        if p not in sys.path:
            sys.path.insert(0, p)
    import line_check as LC  # noqa: E402  (spike harness: the byte-anchored BoxLineCheck oracle)

    nat_path = _load_native_model(tmp_path)
    nat = LC.load_level_model(str(nat_path))
    ed = LC.load_level_model(str(_EDITOR))

    # The pawn-sized swept box dropped down the (0,-250) column — the exact acceptance probe.
    start, end, extent = (0.0, -250.0, 148.0), (0.0, -250.0, -52.0), (20.0, 20.0, 44.0)
    hn = LC.line_check(nat, start, end, extent)
    he = LC.line_check(ed, start, end, extent)
    assert hn is not None, "native box drop must land on the floor (not fall through)"
    assert he is not None, "editor golden box drop must land"
    zn, ze = hn["location"][2], he["location"][2]
    # Pre-fix native sank ~12 units below the editor (rest z 35 vs 47 live).  Require parity.
    assert abs(zn - ze) < 1.0, f"native floor contact z={zn:.2f} must match editor z={ze:.2f}"
    # And it must be the true stone floor, not the water sheet 12 uu below.
    assert zn > ze - 1.0, f"native landed {ze - zn:.1f} uu low (sank into the floor)"

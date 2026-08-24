"""Engine-fact regression for the native zone flood's BlockPortal barrier rule
(`uedcli-native/src/zones.rs`, spike `sections/70-zones-portalization.md §13`).

THE FACT this pins: a BSP leaf-pair is a ZONE boundary iff a `PF_Portal` node's REAL stored polygon
separates it (the editor's `MakePortals`/`BlockPortal`, §3) — NOT "any portal a PF_Portal node's
WORLD-sized infinite-quad face generates".  The infinite-quad rule over-marks: a small portal
surface (a water pane) in a large BSP cell had its whole cell-face flagged, wrongly separating
leaves that share open space.  On `10_Paris_Catacombs`'s OWN editor tree that over-marked 1084
within-zone faces as barriers, shattering the editor's 17 zones into 56; UNATCO 7->45, HK-Market
5->64.  The fix (`collect_zone_barriers`) reproduces the editor exactly.

Why the goldens and not a synthetic fixture: the two rules AGREE on `Test_Castle` (its portal
surfaces seal their whole cross-section, so the infinite quad == the real polygon) — the castle's
near-single-zone topology is exactly what masked the bug in the first place.  The discriminating
evidence is the real shipped levels, so this checks the flood against the editor's own zone count on
whichever shipped `.dx` goldens are present (skips cleanly when they are not — e.g. CI without the
game install).  The flood is deterministic from geometry, so the count IS a valid gate.

Coverage boundary (honest): this test pins the ALGORITHM via the committed harness oracle
(`zone_flood_oracle.blockportal_interior_zones`), a line-for-line Python port of `zones.rs`
Pass B/B'/C — NOT the shipped Rust directly (feeding an external tree through the Rust flood needs an
FFI entry point that does not yet exist; filed to `board/inbox/`).  The Rust `collect_zone_barriers`
is written as a mechanical copy of that same oracle (flat node enumeration + `head_of` chain-head
resolution), and is CONFIRMED to reproduce it on the discriminating real trees: the native builds
`NativeUnatco.dx` (45 zones) and `NativeCatacombs.dx` (43 zones) each equal
`blockportal_interior_zones(that native tree) + 1` (44+1, 42+1).  Additional coverage:
`test_water_portal_keeps_playerstart_out_of_water_zone` (non-discriminating — the old and new
rules agree on castle-topology sealing portals).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]  # Tools/uedcli
_HARNESS = _ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"
_DECON = _ROOT / "dev/docs/spikes/2026-06-27-decontainerize-uedcli/harness"
_MAPS = Path("/home/neob91/Games/LutrisDX/drive_c/DX/Maps")

# The shipped goldens and their editor NumZones (from `zone_ground_truth.py`).  Test_Castle rides in
# the repo-adjacent Maps dir; the three retail levels live in the game install.
_GOLDENS = {
    "Test_Castle.dx": 4,
    "03_NYC_UNATCOHQ.dx": 7,
    "06_HongKong_WanChai_Market.dx": 5,
    "10_Paris_Catacombs.dx": 17,
}


def _load_oracle():
    for p in (_HARNESS, _DECON):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    try:
        import zone_flood_oracle as ZFO  # noqa: E402
        import utexture_decode as UT  # noqa: E402
        from uedcli.native import umodel as UM  # noqa: E402
    except Exception as e:  # pragma: no cover - environment-dependent
        pytest.skip(f"zone-flood oracle deps unavailable: {e}")
    return ZFO, UT, UM


@pytest.mark.parametrize("mapname,editor_zones", list(_GOLDENS.items()))
def test_blockportal_flood_matches_editor_zone_count(mapname, editor_zones):
    path = _MAPS / mapname
    if not path.exists():
        pytest.skip(f"shipped golden not present: {path}")
    ZFO, UT, UM = _load_oracle()
    pkg = UT.load_package(str(path))
    mi = max((i for i in range(len(pkg.exports)) if pkg.class_of_export(i) == "Model"),
             key=lambda i: pkg.exports[i]["ssize"])
    e = pkg.exports[mi]
    model = UM.parse_model_body(pkg.buf, e["soff"], e["ssize"])
    interior = ZFO.blockportal_interior_zones(model)
    # NumZones = interior components + zone 0 (solid/outside).  Must equal the editor's shipped count
    # (leaf-pair-exact).  A regression to the infinite-quad zone-portal marking blows this up (e.g.
    # Catacombs 17 -> 56), so the assertion catches the over-fragmentation directly.
    got = min(interior + 1, 64)
    assert got == editor_zones, (
        f"{mapname}: BlockPortal flood NumZones={got} (interior={interior}) != editor "
        f"{editor_zones} — zone-portal over-marking regression?")

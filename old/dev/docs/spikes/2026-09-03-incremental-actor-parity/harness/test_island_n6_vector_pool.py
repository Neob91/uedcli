#!/usr/bin/env python3
"""Regression for Island N=6's world-`Model2` Vectors pool order.

The pool's on-disk order is the order `bspAddVector` first proposed each SURVIVING vector during
incremental CSG -- including proposals made by a surf that CSG later merged away. Island N=6's
`Brush1355` bottom face is such a surf: its `vTextureU` claims pool slot 8, the face is merged away,
and `Brush1353`'s oblique-face NORMAL later dedups into that same slot (they agree to 6e-7, inside
`THRESH_NORMALS_ARE_SAME` = 2e-5). Native therefore KEEPS the incremental Vectors pool across the
repartition instead of rebuilding it from the surviving surfs -- the retired `rebuild_vector_pool`,
which could only ever have put that vector at 16.

Builds native from the 6-actor subset trunk committed beside the spike and gates it against the
committed UED22 reference, so reverting the fix turns this red. Skips loudly when the game packages
the native build resolves textures/schema from are not installed on this host.

Spike: `dev/docs/spikes/2026-09-06-island-n6-vector-pool/`.
Run: python3 test_island_n6_vector_pool.py    (or via pytest)
"""
from __future__ import annotations

import sys
from pathlib import Path

HARNESS = Path(__file__).resolve().parent
ROOT = HARNESS.parents[4]
REPORT_HARNESS = ROOT / "dev/docs/spikes/2026-08-31-native-parity-report/harness"
SPIKE = ROOT / "dev/docs/spikes/2026-09-06-island-n6-vector-pool"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(REPORT_HARNESS))
sys.path.insert(0, str(HARNESS))

import model_dump as MD  # noqa: E402
import parity_gate as G  # noqa: E402

SUBSET = SPIKE / "golden/subset/maps/01_nyc_unatcoisland"
REF = SPIKE / "golden/ref_N6.dx"
BSPCSG = ROOT / "uedcli-native/src/bspcsg.rs"

# `Brush1355`'s bottom-face `vTextureU`, which claims the slot; `Brush1353`'s oblique-face normal
# dedups into it. As stored (float32 widened to double).
HOISTED = (0.24253599345684052, 0.9701420068740845, 0.0)
HOISTED_INDEX = 8


def test_pool_is_not_rebuilt_from_the_surviving_surfs():
    src = BSPCSG.read_text()
    assert "fn rebuild_vector_pool" not in src, (
        "the Vectors pool must be KEPT across the repartition, not rebuilt from the final surfs")


def _build_native(tmp_path: Path) -> Path:
    import parity_compare as pc
    dx, _warn = pc.build_native_lit_dx(SUBSET, SPIKE / "golden/subset")
    out = tmp_path / "native_N6.dx"
    out.write_bytes(dx)
    return out


def _model2(dx: Path) -> dict:
    p = G.load_package(str(dx))
    return MD.decode(p, MD.find(p, "Model2"))


def _native_or_skip(tmp_path: Path) -> Path:
    try:
        return _build_native(tmp_path)
    except Exception as ex:  # no uedcli_native, or the game packages are not installed here
        import pytest
        pytest.skip(f"native build unavailable on this host: {type(ex).__name__}: {ex}")


def test_native_n6_pool_hoists_the_merged_away_surfs_axis(tmp_path):
    nat, ref = _model2(_native_or_skip(tmp_path)), _model2(REF)
    assert ref["vectors"][HOISTED_INDEX] == HOISTED, "the committed ref no longer pins the slot"
    assert nat["vectors"] == ref["vectors"], "native's Vectors pool must match the editor's, in order"
    # surf tuple = (texture, flags, [pBase, vNormal, vTextureU, vTextureV, iLightMap, iBrushPoly],
    # lightmap, iActor). The texture ref and iActor are export/import indices, whose ORDER the parity
    # bar excludes; the vector/point refs in between are what this pins.
    assert [s[1:4] for s in nat["surfs"]] == [s[1:4] for s in ref["surfs"]], \
        "surf vector refs must follow the same pool"


def test_n6_gates_byte_exact(tmp_path):
    ok, fails = G.gate(str(_native_or_skip(tmp_path)), str(REF))
    assert ok, f"Island N=6 must gate byte-exact: {fails}"


if __name__ == "__main__":
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        for t in (test_pool_is_not_rebuilt_from_the_surviving_surfs,
                  test_native_n6_pool_hoists_the_merged_away_surfs_axis, test_n6_gates_byte_exact):
            try:
                t(Path(td)) if t.__code__.co_argcount else t()
            except BaseException as e:  # pytest.skip raises `Skipped`, a BaseException
                if type(e).__name__ != "Skipped":
                    raise
                print(f"SKIP {t.__name__}: {e}")
    print("OK")

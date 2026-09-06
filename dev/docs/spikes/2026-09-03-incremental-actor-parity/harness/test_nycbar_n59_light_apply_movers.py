#!/usr/bin/env python3
"""Regression for NYC_Bar N=59 — `LIGHT APPLY`'s moving-brush pass.

Once the world `Model` has nodes, `shadowIlluminateBsp` does three things to every mover, and all
three are stored: it allocates one `FLightMapIndex` per lightmappable poly (the poly's `iBrushPoly`
is the slot), the moving-brush tracker mirrors each poly into a transient world surf and writes that
surf index into the poly's `iLink`, and `UModel::PrecomputeSphereFilter` marks the world nodes each
mover's bounding sphere lies wholly in front of / behind. The node bits ACCUMULATE across the
movers, walked in reverse actor order.

Builds native from the 59-actor subset trunk committed beside the spike and gates it against the
committed UED22 reference, so reverting the fix turns this red. Skips loudly when the game packages
the native build resolves textures/schema from are not installed on this host.

Spike: `dev/docs/spikes/2026-09-06-nycbar-n59-light-apply-movers/`.
Run: python3 test_nycbar_n59_light_apply_movers.py    (or via pytest)
"""
from __future__ import annotations

import sys
from pathlib import Path

HARNESS = Path(__file__).resolve().parent
ROOT = HARNESS.parents[4]
REPORT_HARNESS = ROOT / "dev/docs/spikes/2026-08-31-native-parity-report/harness"
SPIKE = ROOT / "dev/docs/spikes/2026-09-06-nycbar-n59-light-apply-movers"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(REPORT_HARNESS))
sys.path.insert(0, str(HARNESS))

import model_dump as MD  # noqa: E402
import parity_gate as G  # noqa: E402

SUBSET = SPIKE / "golden/subset/maps/02_nyc_bar"
REF = SPIKE / "golden/ref_N59.dx"

# The world tree is a 6-node chain; the three descents leave these, last write wins.
WORLD_NODE_FLAGS = [0x40, 0x00, 0x80, 0x40, 0x40, 0x80]
# Movers in actor order, and the world-surf index range each one's 6 polys claim (world surfs = 6).
MOVER_ILINKS = {"Model_DeusExMover11": list(range(6, 12)),
                "Model_DeusExMover12": list(range(12, 18)),
                "Model_DeusExMover9": list(range(18, 24))}


_NATIVE: list = []


def _native_or_skip(tmp_path: Path) -> Path:
    """Build once per session. Only a MISSING host prerequisite skips -- a build that raises is the
    regression this test exists to catch, so it propagates."""
    if _NATIVE:
        return _NATIVE[0]
    import pytest
    pytest.importorskip("uedcli_native")
    import parity_compare as pc
    dx, _warn = pc.build_native_lit_dx(SUBSET, SPIKE / "golden/subset")
    out = tmp_path / "native_N59.dx"
    out.write_bytes(dx)
    _NATIVE.append(out)
    return out


def _polys_by_model(dx: Path) -> dict:
    """`{model name: [(iLink, iBrushPoly), ...]}` for every Model that owns a Polys export."""
    import struct

    from uedcli.native.saveorder import _model_polys_map
    from uedcli.upackage import read_compact_index, read_property_tags

    p = G.load_package(str(dx))
    owner = {v: k for k, v in _model_polys_map(p).items()}
    out = {}
    for i in range(len(p.exports)):
        nm = p.names[p.exports[i]["nm"]]
        if (p.object_class_name(i + 1) or "") != "Polys" or nm not in owner:
            continue
        e = p.exports[i]
        pos = read_property_tags(p, e["soff"], e["soff"] + e["ssize"])[1]
        num = struct.unpack_from("<i", p.buf, pos)[0]
        pos += 8
        rows = []
        for _ in range(num):
            nv, pos = read_compact_index(p.buf, pos)
            pos += 52 + 12 * nv
            for _k in range(3):
                _, pos = read_compact_index(p.buf, pos)
            i_link, pos = read_compact_index(p.buf, pos)
            i_brush_poly, pos = read_compact_index(p.buf, pos)
            pos += 4
            rows.append((i_link, i_brush_poly))
        out[owner[nm]] = rows
    return out


def test_ref_pins_the_editor_behaviour():
    """The committed reference must still show what this regression is about."""
    p = G.load_package(str(REF))
    assert [n[2] for n in MD.decode(p, MD.find(p, "Model2"))["nodes"]] == WORLD_NODE_FLAGS
    rows = _polys_by_model(REF)
    for model, links in MOVER_ILINKS.items():
        assert [r[0] for r in rows[model]] == links, f"{model} iLink"
        assert [r[1] for r in rows[model]] == list(range(6)), f"{model} iBrushPoly (lightmap slot)"
        assert len(MD.decode(p, MD.find(p, model))["lightmap"]) == 6, f"{model} LightMap"


def test_native_reproduces_the_mover_pass(tmp_path):
    nat = _native_or_skip(tmp_path)
    p = G.load_package(str(nat))
    assert [n[2] for n in MD.decode(p, MD.find(p, "Model2"))["nodes"]] == WORLD_NODE_FLAGS, \
        "world node NF_IsFront/NF_IsBack must accumulate over the movers' sphere descents"
    rows = _polys_by_model(nat)
    ref = G.load_package(str(REF))
    for model, links in MOVER_ILINKS.items():
        assert [r[0] for r in rows[model]] == links, f"{model} iLink"
        assert [r[1] for r in rows[model]] == list(range(6)), f"{model} iBrushPoly"
        assert MD.decode(p, MD.find(p, model))["lightmap"] == \
            MD.decode(ref, MD.find(ref, model))["lightmap"], f"{model} LightMap"


def test_n59_gates_byte_exact(tmp_path):
    ok, fails = G.gate(str(_native_or_skip(tmp_path)), str(REF))
    assert ok, f"NYC_Bar N=59 must gate byte-exact: {fails}"


if __name__ == "__main__":
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        for t in (test_ref_pins_the_editor_behaviour, test_native_reproduces_the_mover_pass,
                  test_n59_gates_byte_exact):
            try:
                t(Path(td)) if t.__code__.co_argcount else t()
            except BaseException as e:  # pytest.skip raises `Skipped`, a BaseException
                if type(e).__name__ != "Skipped":
                    raise
                print(f"SKIP {t.__name__}: {e}")
    print("OK")

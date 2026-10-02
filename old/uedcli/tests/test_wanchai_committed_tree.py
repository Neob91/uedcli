"""Pins the editor-side facts of the Wanchai BSP divergence against their committed captures.

Board item `wanchai-bsp-gap-localized-to-one-dropped` §4: on `06_HongKong_WanChai_Market`, native's
committed pre-repartition CSG tree carries one node the editor's does not — the bottom face of the
`CSG_Subtract` cube `Brush250` at world z=112. The editor half of that claim comes from live-gdb
captures that cost ~10 minutes of editor drive each, so it is pinned here against the logs those runs
committed, rather than re-derived. Nothing here builds anything or needs the editor; the NATIVE half
is not pinned (it needs the Rust extension and a 1304-brush build — the item's reproduce path covers
it).

If a future change makes native match, these numbers stay true: they describe the editor, which does
not change. A failure here means a committed capture was edited or truncated.
"""
import re
from pathlib import Path

import pytest

LOGS = (Path(__file__).resolve().parents[2]
        / "dev/docs/spikes/2026-07-15-native-materialize/harness/editor-tree-oracle/logs")
COMMITTED_TREE = LOGS / "wanchai-ed-committed-tree.log"
REPART_STAGE = LOGS / "wanchai-ed-repart-stage.log"
REPART_NUMPOLYS = LOGS / "wanchai-ed-repart-numpolys.log"

_ND = re.compile(r"^ND (\d+) plane=([-0-9.eE,]+) iF=(-?\d+) iB=(-?\d+) iP=(-?\d+) isurf=(-?\d+) "
                 r"nv=(-?\d+) nf=(\S+)")

# Brush250's five faces the editor keeps, by the surf each got, in the order the tree holds them.
# The sixth (world z=112, stored plane `(0,0,1,112)` after the Subtract winding reversal) is absent —
# that absence is the whole finding.
BRUSH250_KEPT = {
    5195: (-0.0, -0.0, -1.0, -144.0),
    5196: (-0.0, -1.0, -0.0, 912.0),
    5197: (-0.0, 1.0, -0.0, -1023.99994),
    5198: (-1.0, -0.0, -0.0, 16.0),
    5199: (1.0, -0.0, -0.0, -240.0),
}
DROPPED_FACE = (-0.0, -0.0, 1.0, 112.0)


@pytest.fixture(scope="module")
def nodes():
    """`{index: (plane, iF, iB, iP, isurf, nv)}` from the committed editor capture."""
    out = {}
    for line in COMMITTED_TREE.read_text().splitlines():
        if m := _ND.match(line):
            plane = tuple(float(x) for x in m[2].split(","))
            out[int(m[1])] = (plane, int(m[3]), int(m[4]), int(m[5]), int(m[6]), int(m[7]))
    return out


def test_the_capture_holds_the_whole_committed_tree(nodes):
    header = [ln for ln in COMMITTED_TREE.read_text().splitlines()
              if ln.startswith("TREEBEGIN")]
    assert header == ["TREEBEGIN num=21147"], "capture truncated or re-run against another level"
    assert len(nodes) == 21147
    assert sum(1 for v in nodes.values() if v[5] == 0) == 5114, "dead-node count"


def test_brush250_contributes_five_faces_not_six(nodes):
    # Identification is contiguity + consecutive fresh surfs, not plane equality: `(0,0,1,112)` alone
    # occurs at 14 unrelated nodes elsewhere in this level, and every one of Brush250's other planes
    # recurs dozens of times.
    block = {surf: plane for plane, _iF, _iB, _iP, surf, _nv in
             (nodes[i] for i in range(20445, 20458)) if surf in BRUSH250_KEPT}
    assert block == BRUSH250_KEPT
    assert DROPPED_FACE not in [nodes[i][0] for i in range(20445, 20458)]


def test_the_world_repartition_is_the_first_stage_group():
    groups = [ln.split() for ln in REPART_STAGE.read_text().splitlines() if "nodes=" in ln]
    first = {kv.split("=")[0]: kv.split("=")[1] for kv in groups[0][1:]}
    assert groups[0][0] == "A_entry"
    assert first["nodes"] == "21147", "the repartition's input is the committed tree above"
    after = [g for g in groups if g[0] == "E_bsprefresh"][0]
    assert dict(kv.split("=") for kv in after[1:])["nodes"] == "11011"


def test_the_repartition_soup_size():
    assert "num=8187 nonzero_nv=8187" in REPART_NUMPOLYS.read_text()

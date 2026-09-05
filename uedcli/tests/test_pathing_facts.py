"""Path-build facts pinned by the 2026-09-05 reverse engineering (`PATHING-BUILD.md`,
`dev/docs/spikes/2026-09-05-pathing-build-re/`). Offline: the committed UED22 binary, the committed
UED22-built goldens under the spike's `evidence/`, and (when the gitignored game install is present)
one retail Deus Ex map."""
from __future__ import annotations

import re
import struct
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPIKE = ROOT / "dev/docs/spikes/2026-09-05-pathing-build-re"
sys.path.insert(0, str(SPIKE / "harness"))

import simulate_bookkeeping as sim  # noqa: E402
from paths import GAME  # noqa: E402
from retail_stats import R_JUMP, R_SPECIAL, R_SWIM, R_WALK, analyze  # noqa: E402

ENGINE = ROOT / "uned/UED22/Engine.dll"


def _rdata(rva: int, n: int) -> bytes:
    """Bytes at an Engine.dll RVA (the .rdata section is not relocated: file offset == RVA - 0x400)."""
    data = ENGINE.read_bytes()
    pe = data.index(b"PE\0\0")
    coff = pe + 4
    n_sections = struct.unpack_from("<H", data, coff + 2)[0]
    sec = coff + 20 + struct.unpack_from("<H", data, coff + 16)[0]
    for i in range(n_sections):
        b = sec + 40 * i
        vsize, vaddr, raw = (struct.unpack_from("<I", data, b + k)[0] for k in (8, 12, 20))
        if vaddr <= rva < vaddr + vsize:
            return data[raw + rva - vaddr: raw + rva - vaddr + n]
    raise AssertionError(f"RVA {rva:#x} not in any section")


def test_ued22_path_build_constants():
    """`PATHING-BUILD.md` §3: the reachspec pair cutoff 1000² (`addReachSpecs 0x1772f0`), the Prune
    detour factor 1.2f (`0x1768fc`), createPaths' merge 128², neighbour 800², distant-pair 600² and
    the 1.3 f64 intermediate factor."""
    assert struct.unpack("<f", _rdata(0x20296c, 4))[0] == 1000000.0
    assert struct.unpack("<f", _rdata(0x212d5c, 4))[0] == pytest.approx(1.2)
    assert struct.unpack("<f", _rdata(0x212d84, 4))[0] == 16384.0
    assert struct.unpack("<f", _rdata(0x212d90, 4))[0] == 640000.0
    assert struct.unpack("<f", _rdata(0x212d8c, 4))[0] == 360000.0
    assert struct.unpack("<d", _rdata(0x212d68, 8))[0] == 1.3


def test_ued22_lift_and_teleporter_edges_are_hardcoded():
    """`addReachSpecs`: LiftCenter↔LiftExit specs are 500 / 60 / 60 / R_SPECIAL, Teleporter and
    WarpZoneMarker specs 100 / 150 / 150 / R_SPECIAL (live golden `pathlab2-define.dx`)."""
    r = analyze(str(SPIKE / "evidence/pathlab2-define.dx"))
    special = {(d, rad, h, fl, a, b) for d, rad, h, fl, a, b, pr in r["special"]}
    assert (500, 60, 60, "SPECIAL", "LiftCenter", "LiftExit") in special
    assert (500, 60, 60, "SPECIAL", "LiftExit", "LiftCenter") in special
    assert (100, 150, 150, "SPECIAL", "Teleporter", "Teleporter") in special
    assert r["flags"]["SWIM"] == 6 and r["dist_swim_2round"] + r["dist_swim_2x"] == 6   # water room: Distance = 2 × rounded straight line


def test_ued22_define_golden_shape():
    """`pathlab-define.dx` (PATHS DEFINE on the synthetic corridor/hall level): 281 specs, 184
    pruned; Distance rounded (94 specs differ from truncation); Paths/upstreamPaths sorted by
    descending Distance; Paths+PrunedPaths ≤ 16 with the longest specs dropped; every pruned spec
    has a two-hop detour ≤ 1.2×; sizes capped at 70/70; the 1000-uu cutoff (max WALK 922 < 1000
    while the level has 1000..1200-uu gaps)."""
    r = analyze(str(SPIKE / "evidence/pathlab-define.dx"))
    assert (r["specs"], r["pruned"]) == (281, 184)
    assert r["dist_eq_round"] == 94 and r["dist_other"] == []
    assert r["order_by_dist_desc"] == r["order_n"] == 28
    assert r["uorder_by_dist_desc"] == r["uorder_n"] == 28
    assert r["p_plus_pr_gt16"] == 0 and r["dropped_not_longest"] == 0
    assert r["prune_ok"] == 184 and r["prune_bad"] == []
    assert max(rad for rad, h in r["rh"]) == 70 and max(h for rad, h in r["rh"]) == 70
    assert r["maxdist"]["WALK"] == 922
    assert set(r["flags"]) == {"WALK", "WALK|JUMP"}


@pytest.mark.parametrize("golden", ["pathlab-define.dx", "pathlab-build.dx", "pathlab2-define.dx"])
def test_ued22_bookkeeping_and_prune_replay(golden):
    """`insertReachSpec` + `Prune` (`ued` constants, non-strict 1.2f) replayed from ReachSpecs and
    the roster reproduce every bPruned bit and every per-node array of a UED22 build."""
    sim.STRICT = False
    ok, bad, msg = sim.run(str(SPIKE / "evidence" / golden), "ued", False)
    arrays_ok, arrays_all = re.search(r"arrays (\d+)/(\d+) match", msg).groups()
    assert bad == 0 and arrays_ok == arrays_all, msg



RETAIL_BAR = GAME / "Maps/02_NYC_Bar.dx"


@pytest.mark.skipif(not RETAIL_BAR.exists(), reason="retail Deus Ex maps not installed")
def test_dx_builder_replay_on_retail_bar():
    """The Deus Ex 1112fm builder: same bookkeeping, strict 1.2 (double constant below 1.2 at
    64-bit x87 precision), BotOnlyPath < 12, MonsterPath 22/51 — reproduces `02_NYC_Bar.dx`
    exactly (889 specs, 497 pruned); with a non-strict compare spec 73 (165 vs 50+148) is
    mis-pruned."""
    sim.STRICT = True
    ok, bad, _ = sim.run(str(RETAIL_BAR), "dx", False)
    assert (ok, bad) == (889, 0)
    sim.STRICT = False
    ok, bad, _ = sim.run(str(RETAIL_BAR), "dx", False)
    assert (ok, bad) == (888, 1)
    r = analyze(str(RETAIL_BAR))
    assert r["dist_eq_trunc"] == 889 and r["dist_eq_round"] == 0        # dx truncates
    assert max(rad for rad, h in r["rh"]) == 115 and max(h for rad, h in r["rh"]) == 79
    assert r["maxdist"]["WALK"] < 1000

"""Pin: UCC's `Editor.ExecCommandlet` stdout carries the D0 BSP-build warning
channels, and the D0 parser (`bspspike/bsp_editorlog.parse_build_log`) consumes
it unchanged. The two fixtures are REAL captured `wine UCC.exe Editor.ExecCommandlet`
stdout from `dx-lum-uned:latest` (2026-08-03), not synthetic.

Verdict + full evidence: board item `bsp-issue-detector` overview (2026-08-03 GO).
`gen.py` regenerates the polylists + exec scripts. Run explicitly (not in the default suite):
    bin/test dev/docs/spikes/2026-08-03-ucc-log-bsp-warnings/test_ucc_log_d0_channels.py
"""
from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent / "bspspike"))

import bsp_editorlog as E  # noqa: E402

_FIX = _HERE / "fixtures"


def test_it_parses_unlinked_tpoints_from_ucc_open_box_stdout():
    log = E.parse_build_log((_FIX / "ucc_open_box.stdout.txt").read_text())
    # open cube (top face removed) → HoM crack: 20 T-point sides, 16 linked → 4 unlinked.
    assert log.unlinked_tpoints == 4
    assert log.has_holes_or_hom is True
    assert log.final_nodes == 5
    assert log.leaves == 1
    assert log.zero_area_drops == 0
    assert log.few_vert_drops == ()


def test_it_parses_dropped_face_from_ucc_degenerate_stdout():
    log = E.parse_build_log((_FIX / "ucc_degen.stdout.txt").read_text())
    # cube + one zero-area polygon → editor drops it: "Not enough vertices (0)".
    assert log.few_vert_drops == (0,)
    assert log.has_drops is True
    assert log.final_nodes == 6
    assert log.leaves == 1
    assert log.unlinked_tpoints == 0

#!/usr/bin/env python3
"""Print properties of 11_paris_underground's first 34 world-CSG brushes (search interpretation)."""
import os
import sys
from pathlib import Path

WT = Path(__file__).resolve().parents[5]  # harness/<slug>/spikes/docs/dev -> repo root
sys.path.insert(0, str(WT))
sys.path.insert(0, str(WT / "dev/docs/spikes/2026-07-15-native-materialize/harness"))
sys.path.insert(0, str(WT / "dev/docs/spikes/2026-09-03-built-parity-worst-tier/harness"))

TRUNK = Path("/workspace/uedcli/.claude/worktrees/breadth-parity-check/_scratch/uedcli-parity-cache"
             "/bdf66b5dc02df008a53f5018b5aeab950cf13481c2a49bd0f683dd714429c718/trunk")
os.environ.setdefault("UEDCLI_PROJECT", str(TRUNK))

from uedcli import trunk as TR
from uedcli.native import brush_marshal as BM
from spike_classindex import class_index
from attrib_props import brush_props

level, _ = TR.read_level(TRUNK / "maps/11_paris_underground")
ci = class_index()
names = [n for n in level.order
         if level.actors[n].brush is not None and BM._in_world_csg(level.actors[n], ci)]
for i, n in enumerate(names[:34]):
    print(i, n, brush_props(level.actors[n]))

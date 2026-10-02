#!/usr/bin/env python3
"""Spike 2 (flags half): are per-poly PolyFlags preserved through the EDIT PASTE add
path + REBUILD? If yes, surface flags (Masked/Translucent/FakeBackdrop/Two-Sided/…)
are a MODEL-SIDE edit (set poly.flags, re-emit, paste) — no live POLY verb needed.
"""
import copy
import subprocess
import sys
import select_matrix as M
from uedcli.driver import Driver
from uedcli.writes import add_actor
from uedcli.model import parse_t3d
from uedcli.normalize import normalize_level

TRANSLUCENT = 4   # PF_Translucent

for attempt in range(1, 4):
    try:
        M.restart_editor(); M.clear()
        drv = Driver()
        a = M.importadd_actor("FLAGBRUSH", (0, 0, 0))   # template brush (has texture vectors)
        a.brush.polys[0].flags = TRANSLUCENT            # flag ONE face
        add_actor(drv, a)                               # paste
        drv.rebuild()
        drv.map_export("/repo/Temp/flag_out.t3d")
        txt = subprocess.run(["docker", "exec", M.CONT, "cat", "/repo/Temp/flag_out.t3d"],
                             text=True, capture_output=True).stdout
        lvl = parse_t3d(txt)
        fb = lvl.actors.get("FLAGBRUSH")
        flags = sorted({p.flags for p in fb.brush.polys}) if fb and fb.brush else None
        print(f"\nFLAGBRUSH present: {fb is not None}", flush=True)
        print(f"poly flags after paste+rebuild: {flags}", flush=True)
        print(f"\nVERDICT: Translucent (flags=4) preserved on a face? "
              f"{bool(fb and fb.brush and any(p.flags == TRANSLUCENT for p in fb.brush.polys))}", flush=True)
        sys.exit(0)
    except M.EditorDead as e:
        print(f"*** {e} (attempt {attempt}) ***", flush=True)
        M.capture_crash("polyflag")
sys.exit(1)

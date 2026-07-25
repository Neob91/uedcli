#!/usr/bin/env python3
"""Spike: does surface selection (PF_Selected) appear in the exported brush T3D?
If yes, we could select a surface in-editor and read back which poly index it is.
If no, poly identification must be model-side (index) + a numbered-wireframe viewer.
Compares per-poly Flags before vs after ACTOR SELECT ALL + POLY SELECT ALL.
"""
import subprocess
import sys
import select_matrix as M
from uedctl.driver import Driver
from uedctl.writes import add_actor
from uedctl.model import parse_t3d


def export_flags(drv, tag):
    drv.map_export(f"/repo/Temp/pfsel_{tag}.t3d")
    txt = subprocess.run(["docker", "exec", M.CONT, "cat", f"/repo/Temp/pfsel_{tag}.t3d"],
                         text=True, capture_output=True).stdout
    lvl = parse_t3d(txt)
    b = lvl.actors.get("PFSEL")
    return [p.flags for p in b.brush.polys] if b and b.brush else None


for attempt in range(1, 4):
    try:
        M.restart_editor(); M.clear()
        drv = Driver()
        add_actor(drv, M.importadd_actor("PFSEL", (0, 0, 0)))   # selectable brush (paste)
        drv.rebuild()
        before = export_flags(drv, "before")
        print(f"poly flags BEFORE selection: {before}", flush=True)

        drv.exec("ACTOR SELECT ALL")
        drv.exec("POLY SELECT ALL")          # select all surfaces of selected brushes
        after = export_flags(drv, "after")
        print(f"poly flags AFTER  ACTOR+POLY SELECT ALL: {after}", flush=True)

        changed = before != after
        print("\n--- VERDICT ---", flush=True)
        print(f"  selection reflected in exported brush T3D (PF_Selected in Flags)? {changed}", flush=True)
        if not changed:
            print("  => NOT feasible via T3D export — poly id must be model-side + viewer.", flush=True)
        sys.exit(0)
    except M.EditorDead as e:
        print(f"*** {e} (attempt {attempt}) ***", flush=True)
        M.capture_crash("pfsel")
sys.exit(1)

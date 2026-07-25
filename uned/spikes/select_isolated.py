#!/usr/bin/env python3
"""Bulletproof isolated IMPORTADD test: clean brush (no live-level reference junk),
find where it ACTUALLY landed via export, box exactly there, then SELECT INSIDE.
Removes both the 'malformed template' and 'box in wrong place' confounds.
"""
import copy
import sys
import select_matrix as M
from uedctl.model import parse_t3d


def clean_ia_actor(name, loc):
    a = copy.deepcopy(M._TEMPLATE_BRUSH)
    a.name = name
    a.location = loc
    a.props = [("CsgOper", "CSG_Add")]   # strip Brush=/Level=/Region/Tag/scales
    return a


def actual_location(name):
    M.ex(r"MAP EXPORT FILE=Z:\repo\Temp\iso_state.t3d")
    import subprocess
    txt = subprocess.run(["docker", "exec", M.CONT, "cat", "/repo/Temp/iso_state.t3d"],
                         capture_output=True, text=True).stdout
    lvl = parse_t3d(txt)
    a = lvl.actors.get(name)
    return a.location if a else None


for attempt in range(1, 4):
    try:
        M.restart_editor(); M.clear()
        req = (1000, 0, 0)
        p = M.put(M.emit_map([clean_ia_actor("ISO", req)]), "iso")
        M.ex("MAP GRID X=1 Y=1 Z=1"); M.ex(f"MAP IMPORTADD FILE={p}")
        present = M.actors_present()
        loc = actual_location("ISO")
        print(f"\nrequested IMPORTADD location: {req}", flush=True)
        print(f"ACTUAL landed location:       {loc}", flush=True)
        print(f"present: {present}", flush=True)

        # box exactly where it actually landed (no rebuild yet)
        bloc = tuple(int(c) for c in (loc or req))
        _, sel_norebuild = M.probe("ISO", 160, bloc)
        print(f"\nSELECT INSIDE @ actual loc, NO rebuild -> {sel_norebuild}", flush=True)

        M.ex("MAP REBUILD");
        _, sel_rebuilt = M.probe("ISO", 160, bloc)
        print(f"SELECT INSIDE @ actual loc, REBUILT    -> {sel_rebuilt}", flush=True)

        M.ex("ACTOR SELECT NONE"); M.ex("ACTOR SELECT ALL")
        print(f"SELECT ALL                              -> {M.selection()}", flush=True)
        print("\nVERDICT: clean IMPORTADD brush INSIDE-selectable (no rb / rb): "
              f"{'ISO' in sel_norebuild} / {'ISO' in sel_rebuilt}", flush=True)
        sys.exit(0)
    except M.EditorDead as e:
        print(f"*** {e} (attempt {attempt}) ***", flush=True)
        M.capture_crash("iso")
sys.exit(1)

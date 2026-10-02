#!/usr/bin/env python3
"""Does EDIT PASTE yield an INSIDE-selectable brush (unlike MAP IMPORTADD)?

Set the X clipboard to a Begin Map…End Map brush, EDIT PASTE, then:
 - read the pasted actor's name + location (measures the ~32uu paste drift),
 - giant 4096^3 box SELECT INSIDE (offset-proof) with a BRUSH ADD control.
If the pasted brush shows up in the giant-box selection, PASTE is the add path
that produces selectable brushes.
"""
import subprocess
import sys
import select_matrix as M
from uedcli.model import parse_t3d


def set_clipboard(content):
    subprocess.run(["docker", "exec", "-i", "-e", "DISPLAY=:99", M.CONT,
                    "xclip", "-selection", "clipboard", "-i"],
                   input=content, text=True, capture_output=True)


def clipboard_raw():
    return subprocess.run(M.WCTL + ["edit-copy"], capture_output=True, text=True).stdout


for attempt in range(1, 4):
    try:
        M.restart_editor(); M.clear()
        # paste a brush emitted at the ORIGIN
        set_clipboard(M.emit_map([M.importadd_actor("PASTED", (0, 0, 0))]))
        M.ex("EDIT PASTE")
        # pasted actors are auto-selected — read them back to get name + landed location
        raw = clipboard_raw()
        plvl = parse_t3d(raw)
        print(f"\nafter EDIT PASTE, pasted selection: {sorted(plvl.actors)}", flush=True)
        for n, a in plvl.actors.items():
            print(f"  pasted {n}: location {a.location}  (emitted at (0,0,0) -> measures paste drift)", flush=True)

        # BRUSH ADD positive control at X=700
        M.place_builder(100, (700, 0, 0)); M.ex("BRUSH ADD")

        M.ex("ACTOR SELECT NONE"); M.ex("ACTOR SELECT ALL")
        allsel = M.selection()
        ba = next((n for n in allsel if n.startswith("Brush") and n != "Brush1"), "?")
        print(f"\nSELECT ALL: {allsel}   (BRUSH ADD control = {ba})", flush=True)

        # giant box covers ±2048 — encloses the pasted brush regardless of the 32uu drift
        _, giant = M.probe("PASTED", 2048, (0, 0, 0))
        print(f"\nGIANT 4096^3 box SELECT INSIDE: {giant}", flush=True)
        for n in allsel:
            if n != "LevelInfo0":
                tag = "BRUSH ADD" if n == ba else ("PASTED" if n in plvl.actors or n == "PASTED" else "?")
                print(f"  {n} ({tag}) selected by INSIDE? {n in giant}", flush=True)

        print("\n--- CONCLUSION ---", flush=True)
        pasted_names = [n for n in allsel if n != ba and n != "LevelInfo0"]
        any_pasted_sel = any(n in giant for n in pasted_names)
        print(f"  pasted brush INSIDE-selectable? {any_pasted_sel}", flush=True)
        print(f"  BRUSH ADD control INSIDE-selectable? {ba in giant}", flush=True)
        sys.exit(0)
    except M.EditorDead as e:
        print(f"*** {e} (attempt {attempt}) ***", flush=True)
        M.capture_crash("paste")
sys.exit(1)

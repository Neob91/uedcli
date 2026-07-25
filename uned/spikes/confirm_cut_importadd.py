#!/usr/bin/env python3
"""THE real test: take a genuine BRUSH ADD brush (known INSIDE-selectable), EDIT CUT
it (removes it + puts the editor's own perfect T3D on the clipboard), then MAP
IMPORTADD that exact text back and check INSIDE-selectability.

CUT (not COPY) => no name collision, no duplicate — a clean re-import of the same
brush with the editor's canonical format. Isolates the IMPORT VERB as the only
variable: if this isn't selectable, IMPORTADD itself is the culprit.
"""
import re
import subprocess
import sys
import select_matrix as M


def clipboard_out():
    return subprocess.run(["docker", "exec", "-e", "DISPLAY=:99", M.CONT,
                           "xclip", "-selection", "clipboard", "-o"],
                          capture_output=True, text=True).stdout


def names():
    M.ex("ACTOR SELECT NONE"); M.ex("ACTOR SELECT ALL")
    return sorted(M.selection())


for attempt in range(1, 4):
    try:
        M.restart_editor(); M.clear()
        # 1. genuine BRUSH ADD brush (auto-selected after add)
        M.place_builder(100, (0, 0, 0)); M.ex("BRUSH ADD")
        print(f"after BRUSH ADD, SELECT ALL: {names()}", flush=True)

        # 2. re-select it and EDIT CUT (cut = copy editor T3D to clipboard + remove)
        M.place_builder(2048, (0, 0, 0)); M.ex("ACTOR SELECT NONE"); M.ex("ACTOR SELECT INSIDE")
        sel_before_cut = M.selection()
        print(f"selected for cut: {sel_before_cut}", flush=True)
        M.ex("EDIT CUT")
        cut_t3d = clipboard_out()
        print(f"\nCUT clipboard ({len(cut_t3d)} bytes); after-cut SELECT ALL: {names()}", flush=True)
        m = re.search(r"Begin Actor .*?Name=(\S+)", cut_t3d)
        if not m:
            print("  EDIT CUT did not put a brush on the clipboard — abort this attempt", flush=True)
            raise M.EditorDead("no clipboard from CUT")
        orig = m.group(1)

        # 3. rename to unique, then MAP IMPORTADD the editor's own T3D back
        uniq = "CUTRE"
        re_t3d = cut_t3d.replace(f"Name={orig}", f"Name={uniq}").replace(f'Name="{orig}"', f'Name="{uniq}"')
        p = M.put(re_t3d, "cut_re")
        M.ex("MAP GRID X=1 Y=1 Z=1"); M.ex(f"MAP IMPORTADD FILE={p}")
        print(f"\nafter IMPORTADD of cut brush, SELECT ALL: {names()}", flush=True)
        M.ex("MAP REBUILD")
        _, giant = M.probe(uniq, 2048, (0, 0, 0))
        print(f"giant box after IMPORTADD+REBUILD: {giant}", flush=True)

        print("\n===== VERDICT =====", flush=True)
        print(f"  genuine BRUSH ADD brush, CUT then MAP IMPORTADD'd back,", flush=True)
        print(f"  INSIDE-selectable? {uniq in giant}", flush=True)
        print(f"  (orig name {orig!r}, re-imported as {uniq!r}; clipboard format = editor's own)", flush=True)
        sys.exit(0)
    except M.EditorDead as e:
        print(f"*** {e} (attempt {attempt}) ***", flush=True)
        M.capture_crash("cutia")
sys.exit(1)

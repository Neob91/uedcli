#!/usr/bin/env python3
"""Clean side-by-side: is an IMPORTADD'd brush selectable vs a BRUSH ADD'd one?

Both in ONE fresh session, at distinct locations, no clear() confound:
  IA_BRUSH  -> MAP IMPORTADD (uedctl's add path) at X=-300
  (auto)    -> BRUSH ADD (editor's own) at X=+300
Then: SELECT ALL read-back, and an enclosing SELECT INSIDE box at each.
"""
import select_matrix as M


def run():
    M.restart_editor()          # guaranteed-empty fresh map, no leftovers
    M.clear()
    # IMPORTADD brush at X=-300 (uedctl add_actor path: parse->emit->IMPORTADD)
    p = M.put(M.emit_map([M.importadd_actor("IA_BRUSH", (-300, 0, 0))]), "cmp_ia")
    M.ex("MAP GRID X=1 Y=1 Z=1"); M.ex(f"MAP IMPORTADD FILE={p}")
    # BRUSH ADD brush at X=+300 (editor's own add)
    M.place_builder(100, (300, 0, 0)); M.ex("BRUSH ADD")
    M.ex("MAP REBUILD")

    present = M.actors_present()
    ba = next((n for n in present if n.startswith("Brush") and n != "Brush1"), "?")
    print(f"\npresent after both adds + rebuild: {present}")
    print(f"  IMPORTADD brush = IA_BRUSH @ X=-300   |   BRUSH ADD brush = {ba} @ X=+300")

    M.ex("ACTOR SELECT NONE"); M.ex("ACTOR SELECT ALL")
    print(f"\nACTOR SELECT ALL read-back: {M.selection()}")

    _, ia_sel = M.probe("IA_BRUSH", 128, (-300, 0, 0))
    print(f"256^3 box @ X=-300 (over IMPORTADD brush) -> read-back: {ia_sel}")
    _, ba_sel = M.probe(ba, 128, (300, 0, 0))
    print(f"256^3 box @ X=+300 (over BRUSH ADD brush) -> read-back: {ba_sel}")

    print("\n--- VERDICT ---")
    print(f"  IMPORTADD brush selectable by SELECT ALL?    {'IA_BRUSH' in M_all}")
    print(f"  IMPORTADD brush selectable by SELECT INSIDE? {'IA_BRUSH' in ia_sel}")
    print(f"  BRUSH ADD brush selectable by SELECT INSIDE? {ba in ba_sel}")


M_all = []
if __name__ == "__main__":
    import sys
    for attempt in range(1, 4):
        try:
            M.restart_editor(); M.clear()
            p = M.put(M.emit_map([M.importadd_actor("IA_BRUSH", (-300, 0, 0))]), "cmp_ia")
            M.ex("MAP GRID X=1 Y=1 Z=1"); M.ex(f"MAP IMPORTADD FILE={p}")
            M.place_builder(100, (300, 0, 0)); M.ex("BRUSH ADD")
            M.ex("MAP REBUILD")
            present = M.actors_present()
            ba = next((n for n in present if n.startswith("Brush") and n != "Brush1"), "?")
            print(f"\npresent after both adds + rebuild: {present}", flush=True)
            print(f"  IMPORTADD = IA_BRUSH @ -300 | BRUSH ADD = {ba} @ +300", flush=True)
            M.ex("ACTOR SELECT NONE"); M.ex("ACTOR SELECT ALL")
            M_all = M.selection()
            print(f"\nACTOR SELECT ALL read-back: {M_all}", flush=True)
            _, ia_sel = M.probe("IA_BRUSH", 128, (-300, 0, 0))
            print(f"256^3 box @ -300 (IMPORTADD) -> {ia_sel}", flush=True)
            _, ba_sel = M.probe(ba, 128, (300, 0, 0))
            print(f"256^3 box @ +300 (BRUSH ADD) -> {ba_sel}", flush=True)
            print("\n--- VERDICT ---", flush=True)
            print(f"  IMPORTADD selectable by SELECT ALL?    {'IA_BRUSH' in M_all}", flush=True)
            print(f"  IMPORTADD selectable by SELECT INSIDE? {'IA_BRUSH' in ia_sel}", flush=True)
            print(f"  BRUSH ADD selectable by SELECT INSIDE? {ba in ba_sel}", flush=True)
            sys.exit(0)
        except M.EditorDead as e:
            print(f"*** {e} (attempt {attempt}) ***", flush=True)
            M.capture_crash("compare")
    sys.exit(1)

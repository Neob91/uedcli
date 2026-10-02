#!/usr/bin/env python3
"""Rule out the 'IMPORTADD moved the brush, so the box missed it' explanation.

Box a GIANT 4096^3 volume (encloses anywhere from -2048..+2048 — covers any
plausible IMPORTADD mislocation) with a BRUSH ADD brush as positive control.
If the giant box selects the BRUSH ADD brush but NOT the IMPORTADD brush, then
location is NOT the cause — IMPORTADD brushes are genuinely INSIDE-unselectable.
Uses SELECT ALL + EDIT COPY for presence (avoids the crashy MAP EXPORT).
"""
import sys
import select_matrix as M

for attempt in range(1, 4):
    try:
        M.restart_editor(); M.clear()
        # IMPORTADD brush (full template — survives import better than stripped)
        p = M.put(M.emit_map([M.importadd_actor("IA", (0, 0, 0))]), "loc_ia")
        M.ex("MAP GRID X=1 Y=1 Z=1"); M.ex(f"MAP IMPORTADD FILE={p}")
        # BRUSH ADD positive control at X=500
        M.place_builder(100, (500, 0, 0)); M.ex("BRUSH ADD")

        # presence WITHOUT MAP EXPORT: SELECT ALL + clipboard
        M.ex("ACTOR SELECT NONE"); M.ex("ACTOR SELECT ALL")
        allsel = M.selection()
        ba = next((n for n in allsel if n.startswith("Brush") and n != "Brush1"), "?")
        print(f"\nSELECT ALL (both present?): {allsel}", flush=True)
        print(f"  IMPORTADD brush = IA   |   BRUSH ADD brush = {ba}", flush=True)

        # GIANT box covering ±2048 — encloses the brush wherever IMPORTADD put it
        _, giant = M.probe("IA", 2048, (0, 0, 0))
        print(f"\nGIANT 4096^3 box @ origin, SELECT INSIDE (no rebuild): {giant}", flush=True)
        print(f"  IA (IMPORTADD) selected? {'IA' in giant}", flush=True)
        print(f"  {ba} (BRUSH ADD) selected? {ba in giant}", flush=True)

        M.ex("MAP REBUILD")
        _, giant2 = M.probe("IA", 2048, (0, 0, 0))
        print(f"\nGIANT box after REBUILD: {giant2}", flush=True)
        print(f"  IA selected? {'IA' in giant2}   {ba} selected? {ba in giant2}", flush=True)

        print("\n--- CONCLUSION ---", flush=True)
        if ba in giant and "IA" not in giant:
            print("  Location RULED OUT: giant box selects BRUSH ADD but not IMPORTADD,", flush=True)
            print("  so IMPORTADD brushes are INSIDE-unselectable regardless of position.", flush=True)
        elif "IA" in giant:
            print("  Location WAS the cause: IA selectable once the box truly encloses it.", flush=True)
        else:
            print("  Inconclusive (giant box selected neither — possible size limit).", flush=True)
        sys.exit(0)
    except M.EditorDead as e:
        print(f"*** {e} (attempt {attempt}) ***", flush=True)
        M.capture_crash("loc")
sys.exit(1)

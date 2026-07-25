#!/usr/bin/env python3
"""End-to-end: the REAL uedctl add_actor (now paste-based for brushes) must produce
an ACTOR SELECT INSIDE-selectable brush. Uses the actual Driver + add_actor.
"""
import sys
import select_matrix as M
from uedctl.driver import Driver
from uedctl.writes import add_actor

for attempt in range(1, 4):
    try:
        M.restart_editor(); M.clear()
        drv = Driver()
        a = M.importadd_actor("UEDADD", (500, 0, 0))   # template brush, has Brush= prop
        add_actor(drv, a)                              # brush -> EDIT PASTE path
        drv.rebuild()
        M.ex("ACTOR SELECT NONE"); M.ex("ACTOR SELECT ALL")
        print(f"after add_actor, SELECT ALL: {M.selection()}", flush=True)
        _, giant = M.probe("UEDADD", 2048, (0, 0, 0))
        print(f"giant box SELECT INSIDE: {giant}", flush=True)
        print(f"\nVERDICT: real add_actor brush INSIDE-selectable? {'UEDADD' in giant}", flush=True)
        sys.exit(0)
    except M.EditorDead as e:
        print(f"*** {e} (attempt {attempt}) ***", flush=True)
        M.capture_crash("adde2e")
sys.exit(1)

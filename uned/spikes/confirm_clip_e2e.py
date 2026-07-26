#!/usr/bin/env python3
"""End-to-end: add a brush (paste), then CLIP it via the real uedcli path
(select_by_name bounds-box -> modify_actor delete+paste). Verify the brush's
Z-extent is halved by a Z=0 clip and it's still present + selectable.
"""
import subprocess
import sys
import select_matrix as M
from uedcli.driver import Driver
from uedcli.model import parse_t3d
from uedcli.normalize import normalize_level
from uedcli.writes import add_actor, modify_actor, actor_bounds
from uedcli.clip import clip_brush, axis_plane
import copy


def load_level(drv):
    drv.map_export("/repo/Temp/clip_ctx.t3d")
    txt = subprocess.run(["docker", "exec", M.CONT, "cat", "/repo/Temp/clip_ctx.t3d"],
                         text=True, capture_output=True).stdout
    lvl = parse_t3d(txt); normalize_level(lvl); return lvl


for attempt in range(1, 4):
    try:
        M.restart_editor(); M.clear()
        drv = Driver()
        a = M.importadd_actor("UEDCLIP", (0, 0, 0))   # template brush (±100), has Brush= ref
        add_actor(drv, a)                              # paste -> selectable
        drv.rebuild()

        lvl = load_level(drv)
        assert "UEDCLIP" in lvl.actors, f"add failed; present={list(lvl.actors)}"
        lo0, hi0 = actor_bounds(lvl.actors["UEDCLIP"])
        print(f"before clip: UEDCLIP Z-extent [{lo0[2]:.0f}, {hi0[2]:.0f}]", flush=True)

        # clip by world Z=0, keep below (z<=0). brush at origin so local==world.
        target = copy.deepcopy(lvl.actors["UEDCLIP"])
        pt, nm = axis_plane("z", 0)
        target.brush = clip_brush(target.brush, pt, nm, keep_negative=True)
        modify_actor(drv, lvl, target)                 # select(bbox)->delete->paste clipped
        drv.rebuild()

        lvl2 = load_level(drv)
        present = "UEDCLIP" in lvl2.actors
        if present:
            lo1, hi1 = actor_bounds(lvl2.actors["UEDCLIP"])
            print(f"after clip:  UEDCLIP Z-extent [{lo1[2]:.0f}, {hi1[2]:.0f}]", flush=True)
        print("\n--- VERDICT ---", flush=True)
        print(f"  brush still present after clip? {present}", flush=True)
        if present:
            print(f"  top half removed (hi Z ~0, was ~100)? {abs(hi1[2]) < 20 and hi1[2] < hi0[2] - 50}", flush=True)
        sys.exit(0)
    except M.EditorDead as e:
        print(f"*** {e} (attempt {attempt}) ***", flush=True)
        M.capture_crash("clipe2e")
    except Exception as e:
        print(f"*** non-editor error: {type(e).__name__}: {e}", flush=True)
        raise
sys.exit(1)

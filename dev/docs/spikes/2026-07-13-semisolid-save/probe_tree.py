#!/usr/bin/env python3
r"""Capture the FULL indented `OBJ DEPENDENCIES PACKAGE=MyLevel` tree for a 2-brush
level, so the world-BSP `Model` `Engine.Polys` block (the aggregate that makes
qualify_level_textures off-by-one) can be identified STRUCTURALLY (tree depth /
parent object) rather than by fragile position. Dumps every raw line with its
original indentation to _scratch/semisolid/tree.txt.

    UEDCLI_REUSE_EDITOR=uned-<uuid> PYTHONPATH=. python3 .../probe_tree.py
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
import uuid

from uedcli import builders, writes
from uedcli.driver import Driver, to_z_path
from uedcli.qualify import dump_obj_dependencies
from uedcli.uuid7 import uuid7
from uedcli.editor import ensure_editor, stop_editor

TEX_HOST = "/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Textures/LUM_CoreTex.utx"
TEXNAME = "LUM_CoreTex.grey_stone_tile"
OUT = "/home/neob91/Games/LutrisDX/drive_c/DX/LUM/_scratch/semisolid/tree.txt"


def log(*a):
    print(*a, flush=True)


def settle(ed, s=2.0):
    time.sleep(s)
    try:
        ed.dismiss_blocking_dialog()
    except Exception:
        pass


def main():
    reuse = os.environ.get("UEDCLI_REUSE_EDITOR")
    ed_id = None
    if reuse:
        container = reuse; log(f"REUSING {container}")
    else:
        ed_id = uuid7(); container = ensure_editor(ed_id, ready_timeout=120.0)
    ed = Driver(container=container)
    try:
        cwork = f"/work/LUM_CoreTex_{uuid.uuid4().hex}.utx"
        subprocess.run(["docker", "cp", TEX_HOST, f"{ed.container}:{cwork}"],
                       check=True, capture_output=True, text=True)
        ed.exec(f"OBJ LOAD FILE={to_z_path(cwork)} PACKAGE=LUM_CoreTex"); settle(ed)
        ed.map_new(); settle(ed)
        room = builders.make_brush_actor("Room", builders.cube(1024, 1024, 512, texture=TEXNAME),
                                         location=(0, 0, 0), csg="subtract")
        cube = builders.make_brush_actor("Cube", builders.cube(128, 128, 128, texture=TEXNAME),
                                         location=(300, 0, 0), csg="add")
        writes._re_add(ed, [room, cube]); settle(ed)
        ed.rebuild(); settle(ed, 3.0)
        raw = dump_obj_dependencies(ed)
        with open(OUT, "w") as f:
            f.write(raw)
        log(f"wrote {len(raw)} bytes to {OUT}")
        log("--- FULL TREE (indentation preserved, repr) ---")
        for l in raw.splitlines():
            if l.strip():
                log(repr(l))
    finally:
        if ed_id is not None:
            stop_editor(ed_id); log("editor torn down")
        else:
            log("(reused editor left running)")


if __name__ == "__main__":
    sys.exit(main())

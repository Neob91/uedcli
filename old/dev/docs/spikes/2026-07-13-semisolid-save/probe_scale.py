#!/usr/bin/env python3
r"""Spike harness part 2: a LONE semisolid saves fine (probe.py), so the MAP SAVE
failure is an INTERACTION at scale. This reproduces it by trying several
16-semisolid configurations, each vs a solid control on identical geometry — the
ONLY difference is PolyFlags. Whichever semisolid config fails to save (while its
solid twin saves) is the reproduction; we capture the editor log across that save.

Reuse the booted editor:
    UEDCLI_REUSE_EDITOR=uned-<uuid> PYTHONPATH=. python3 .../probe_scale.py

Container /work for EXPORT/SAVE, docker cp out, container-side existence check
(see probe.py header for why host paths don't work).
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

from uedcli import builders, writes
from uedcli.driver import Driver, to_z_path
from uedcli.uuid7 import uuid7
from uedcli.editor import ensure_editor, stop_editor

SCRATCH = Path("/home/neob91/Games/LutrisDX/drive_c/DX/LUM/_scratch/semisolid")
SCRATCH.mkdir(parents=True, exist_ok=True)


def log(*a):
    print(*a, flush=True)


def dexec(container, *cmd):
    return subprocess.run(["docker", "exec", container, *cmd],
                          capture_output=True, text=True, check=False)


def csize(container, cpath):
    r = dexec(container, "stat", "-c", "%s", cpath)
    return int(r.stdout.strip()) if r.returncode == 0 else None


def settle(ed, secs=2.0):
    time.sleep(secs)
    try:
        if ed.dismiss_blocking_dialog():
            log("  [dismissed GC dialog]"); time.sleep(1.0)
    except Exception as e:
        log(f"  [dismiss failed: {e}]")


def add(ed, actors):
    writes._re_add(ed, actors); settle(ed)


def save_probe(ed, tag):
    cwork = f"/work/{tag}_{uuid.uuid4().hex}.dx"
    off = ed.log_size()
    try:
        ed.exec(f"MAP SAVE FILE={to_z_path(cwork)}")
    except Exception as e:
        log(f"  MAP SAVE exec raised: {e}")
    settle(ed, 2.0)
    try:
        ed.exec("MAP GRID X=16 Y=16 Z=16")
    except Exception:
        pass
    time.sleep(1.0)
    tail = ed.read_log_since(off)
    size = csize(ed.container, cwork)
    log(f"  [{tag}] MAP SAVE exists={size is not None} size={size}")
    if tail.strip():
        log("  --- log across save ---")
        for l in tail.splitlines():
            if l.strip():
                log("   |", l)
        log("  --- end ---")
    return size is not None


def cube_actor(name, solidity, at, w=128):
    b = builders.cube(w, w, w, texture=None)
    return builders.make_brush_actor(name, b, location=at, csg="add",
                                     poly_flags=builders.SOLIDITY_FLAGS[solidity])


def room():
    b = builders.cube(2048, 2048, 1024, texture=None)
    return builders.make_brush_actor("Room", b, location=(0, 0, 0), csg="subtract")


def solid_wall():
    b = builders.cube(2048, 128, 512, texture=None)
    return builders.make_brush_actor("Wall", b, location=(0, 0, 0), csg="add")


def scenario(ed, tag, extra_solids, cubes):
    """Fresh level: room (+optional solids), then `cubes`; rebuild; save."""
    log(f"\n===== {tag} =====")
    ed.map_new(); settle(ed)
    add(ed, [room()])
    if extra_solids:
        add(ed, extra_solids)
    ed.rebuild(); settle(ed)
    add(ed, cubes)
    ed.rebuild(); settle(ed)
    return save_probe(ed, tag)


def n_cubes(solidity, n=16, *, overlap=False, embed_in_wall=False):
    out = []
    for k in range(n):
        if overlap:
            # tightly clustered so cubes overlap each other (coincident faces)
            at = ((k % 4) * 64 - 96, (k // 4) * 64 - 96, 0)
        elif embed_in_wall:
            # merlons sitting half-embedded on top of the solid wall (y=0 wall)
            at = (k * 128 - 960, 0, 256)   # straddle wall top at z=256
        else:
            at = ((k % 4) * 256 - 384, (k // 4) * 256 - 384, 0)  # spread, disjoint
        out.append(cube_actor(f"{'SS' if solidity=='semisolid' else 'SO'}{k}", solidity, at))
    return out


def main():
    reuse = os.environ.get("UEDCLI_REUSE_EDITOR")
    ed_id = None
    if reuse:
        container = reuse; log(f"REUSING {container}")
    else:
        ed_id = uuid7(); container = ensure_editor(ed_id, ready_timeout=120.0)
        log(f"editor {container} ready")
    ed = Driver(container=container)
    res = {}
    try:
        # D1: 16 disjoint semisolids (pure count) vs solid control
        res["D1_semi_disjoint"] = scenario(ed, "D1_semi_disjoint", [], n_cubes("semisolid"))
        res["D1_solid_disjoint"] = scenario(ed, "D1_solid_disjoint", [], n_cubes("solid"))
        # D2: 16 OVERLAPPING semisolids (coincident faces) vs solid control
        res["D2_semi_overlap"] = scenario(ed, "D2_semi_overlap", [], n_cubes("semisolid", overlap=True))
        res["D2_solid_overlap"] = scenario(ed, "D2_solid_overlap", [], n_cubes("solid", overlap=True))
        # D3: 16 semisolids EMBEDDED in a solid wall vs solid control
        res["D3_semi_embed"] = scenario(ed, "D3_semi_embed", [solid_wall()], n_cubes("semisolid", embed_in_wall=True))
        res["D3_solid_embed"] = scenario(ed, "D3_solid_embed", [solid_wall()], n_cubes("solid", embed_in_wall=True))

        log("\n===== SUMMARY =====")
        for k, v in res.items():
            log(f"  {k}: saved={v}")
    finally:
        if ed_id is not None:
            stop_editor(ed_id); log("editor torn down")
        else:
            log("(reused editor left running)")


if __name__ == "__main__":
    sys.exit(main())

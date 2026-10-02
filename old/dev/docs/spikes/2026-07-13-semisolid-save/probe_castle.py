#!/usr/bin/env python3
r"""Spike harness part 3: a FAITHFUL replica of the castle's 16-semisolid detail
pass (from _scratch/castle/build_detail.sh BATCH 3+4) on top of a solid keep +
towers, vs the SAME 16 as solid. The only difference between the two runs is the
solidity flag. Whichever fails MAP SAVE is the reproduction; capture the log.

The 16 semisolids:
  * 4 keep buttresses   20x20x264  @ (+-57,+-57,132)   embedded in the keep walls
  * 4 tower buttresses  22x22x240  @ (+-160,+-160,120) embedded in tower walls
  * 4 brazier pedestals 24x24x44   @ (+-240,+-240,22)
  * 4 brazier bowls     40x40x10   @ (+-240,+-240,49)  coincident on pedestal tops

Reuse the booted editor:
    UEDCLI_REUSE_EDITOR=uned-<uuid> PYTHONPATH=. python3 .../probe_castle.py
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


def log(*a):
    print(*a, flush=True)


def dexec(c, *cmd):
    return subprocess.run(["docker", "exec", c, *cmd], capture_output=True, text=True, check=False)


def csize(c, p):
    r = dexec(c, "stat", "-c", "%s", p)
    return int(r.stdout.strip()) if r.returncode == 0 else None


def settle(ed, s=2.0):
    time.sleep(s)
    try:
        if ed.dismiss_blocking_dialog():
            log("  [dismissed GC dialog]"); time.sleep(1.0)
    except Exception as e:
        log(f"  [dismiss failed: {e}]")


def add(ed, actors):
    writes._re_add(ed, actors); settle(ed)


def cube(name, solidity, at, w, b, h, csg="add"):
    br = builders.cube(w, b, h, texture=None)
    return builders.make_brush_actor(name, br, location=at, csg=csg,
                                     poly_flags=builders.SOLIDITY_FLAGS[solidity])


def solids_base():
    """A hollow bailey + a solid keep block + 4 solid corner towers the buttresses embed into."""
    out = [builders.make_brush_actor("Bailey", builders.cube(1200, 1200, 600, texture=None),
                                     location=(0, 0, 0), csg="subtract")]
    out.append(cube("Keep", "solid", (0, 0, 132), 128, 128, 264))
    for x, y in [(160, 160), (-160, 160), (160, -160), (-160, -160)]:
        out.append(cube(f"Tower{x}_{y}", "solid", (x, y, 120), 64, 64, 240))
    return out


def detail_16(solidity):
    out = []
    for x, y in [(57, 57), (-57, 57), (57, -57), (-57, -57)]:
        out.append(cube(f"Butt{x}_{y}", solidity, (x, y, 132), 20, 20, 264))
    for x, y in [(160, 160), (-160, 160), (160, -160), (-160, -160)]:
        out.append(cube(f"TButt{x}_{y}", solidity, (x, y, 120), 22, 22, 240))
    for x, y in [(240, 240), (-240, 240), (240, -240), (-240, -240)]:
        out.append(cube(f"Brazier{x}_{y}", solidity, (x, y, 22), 24, 24, 44))
        out.append(cube(f"BrazBowl{x}_{y}", solidity, (x, y, 49), 40, 40, 10))
    return out


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


def run(ed, tag, solidity):
    log(f"\n===== {tag} ({solidity}) =====")
    ed.map_new(); settle(ed)
    add(ed, solids_base())
    ed.rebuild(); settle(ed)
    add(ed, detail_16(solidity))
    ed.rebuild(); settle(ed)
    return save_probe(ed, tag)


def main():
    reuse = os.environ.get("UEDCLI_REUSE_EDITOR")
    ed_id = None
    if reuse:
        container = reuse; log(f"REUSING {container}")
    else:
        ed_id = uuid7(); container = ensure_editor(ed_id, ready_timeout=120.0)
    ed = Driver(container=container)
    try:
        s = run(ed, "CASTLE_semisolid", "semisolid")
        c = run(ed, "CASTLE_solid", "solid")
        log("\n===== SUMMARY =====")
        log(f"  CASTLE semisolid saved: {s}")
        log(f"  CASTLE solid     saved: {c}")
    finally:
        if ed_id is not None:
            stop_editor(ed_id); log("editor torn down")
        else:
            log("(reused editor left running)")


if __name__ == "__main__":
    sys.exit(main())

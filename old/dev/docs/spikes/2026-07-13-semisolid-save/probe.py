#!/usr/bin/env python3
"""Spike harness: root-cause why a `--solidity semisolid` brush makes `level
materialize`'s MAP SAVE silently write no `.dx`.

Run on the HOST (Python 3.12, direct docker) from the uedcli dir:
    PYTHONPATH=. python3 dev/docs/spikes/2026-07-13-semisolid-save/probe.py

Reuse an already-booted editor (skip the ~90s boot) with:
    UEDCLI_REUSE_EDITOR=uned-<uuid> PYTHONPATH=. python3 .../probe.py

CRITICAL: the ephemeral editor container's filesystem is NOT the host. MAP
EXPORT/SAVE must write to the container's own `/work` (POSIX) path, which we then
`docker cp` out to host scratch to inspect — exactly as production (apply.py /
xfer) does. Writing `FILE=Z:\home\...` lands inside the CONTAINER's /home and is
invisible to the host (that mistake made even the SOLID control look "failed").

Cases, each: re-add brush(es) the way materialize does (writes._re_add), MAP
REBUILD, MAP EXPORT (container /work -> host, to see what the editor holds), MAP
SAVE (container /work), then check CONTAINER-SIDE whether the .dx exists +
capture the editor log across the save.

  A. one SOLID cube          -> control (must save)
  B. one SEMISOLID cube      -> minimal repro? (uedcli emits PolyFlags=32 on actor)
  C. editor-native semisolid -> paste SOLID cube, flip via MAP SETBRUSH SETFLAGS=32,
                                EXPORT to see the editor's OWN representation.

All host scratch under _scratch (gitignored). Editor torn down in finally unless
reused. Waits bounded.
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
from uedcli.editor import ensure_editor, stop_editor
from uedcli.emit import emit_actor
from uedcli.uuid7 import uuid7

SCRATCH = Path("/home/neob91/Games/LutrisDX/drive_c/DX/LUM/_scratch/semisolid")
SCRATCH.mkdir(parents=True, exist_ok=True)


def log(*a):
    print(*a, flush=True)


def dexec(container, *cmd):
    return subprocess.run(["docker", "exec", container, *cmd],
                          capture_output=True, text=True, check=False)


def container_file_size(container, cpath):
    """Container-side size of cpath, or None if it does not exist."""
    r = dexec(container, "stat", "-c", "%s", cpath)
    if r.returncode != 0:
        return None
    return int(r.stdout.strip())


def settle(ed, secs=2.0):
    time.sleep(secs)
    try:
        if ed.dismiss_blocking_dialog():
            log("  [dismissed a blocking GC dialog]")
            time.sleep(1.0)
    except Exception as e:
        log(f"  [dismiss failed: {e}]")


def add_brushes(ed, actors):
    writes._re_add(ed, actors)
    settle(ed)


def export_probe(ed, tag):
    """MAP EXPORT to container /work, copy out to host, return text."""
    cwork = f"/work/{tag}_{uuid.uuid4().hex}.t3d"
    ed.exec(f"MAP EXPORT FILE={to_z_path(cwork)}")
    settle(ed, 1.5)
    size = container_file_size(ed.container, cwork)
    if not size:
        log(f"  MAP EXPORT -> container {cwork}: MISSING/empty (size={size})")
        return ""
    host = SCRATCH / f"{tag}.t3d"
    subprocess.run(["docker", "cp", f"{ed.container}:{cwork}", str(host)], check=True,
                   capture_output=True, text=True)
    text = host.read_text(errors="replace")
    log(f"  MAP EXPORT -> {host.name} (container size={size})")
    return text


def save_probe(ed, tag):
    """MAP SAVE to container /work; report container-side existence + editor log."""
    cwork = f"/work/{tag}_{uuid.uuid4().hex}.dx"
    off = ed.log_size()
    try:
        ed.exec(f"MAP SAVE FILE={to_z_path(cwork)}")
    except Exception as e:
        log(f"  MAP SAVE exec raised: {e}")
    settle(ed, 2.0)
    # noisy trailing command flushes the buffered log so read_log_since sees it
    try:
        ed.exec("MAP GRID X=16 Y=16 Z=16")
    except Exception:
        pass
    time.sleep(1.0)
    tail = ed.read_log_since(off)
    size = container_file_size(ed.container, cwork)
    exists = size is not None
    log(f"  MAP SAVE -> container {cwork}: exists={exists} size={size}")
    if exists and size:
        subprocess.run(["docker", "cp", f"{ed.container}:{cwork}", str(SCRATCH / f'{tag}.dx')],
                       check=False, capture_output=True, text=True)
    log("  --- editor log across save ---")
    for line in tail.splitlines():
        if line.strip():
            log("   |", line)
    log("  --- end log ---")
    return exists


def emit_polyflag_lines(text):
    for line in text.splitlines():
        s = line.strip()
        if (s.startswith("Begin Actor") or s.startswith("CsgOper")
                or s.startswith("PolyFlags") or (s.startswith("Begin Polygon"))):
            log("     >", s)


def show_uedcli_emit(actor, label):
    log(f"  uedcli emits for the {label} actor (key lines):")
    for l in emit_actor(actor).splitlines():
        s = l.strip()
        if s.startswith("Begin Actor") or "PolyFlags" in s or "CsgOper" in s or s.startswith("Begin Polygon"):
            log("     uedcli>", s)


def build_room():
    room = builders.cube(1024, 1024, 512, texture=None)
    return builders.make_brush_actor("Room", room, location=(0, 0, 0), csg="subtract")


def build_cube(name, solidity, at):
    b = builders.cube(128, 128, 128, texture=None)
    pf = builders.SOLIDITY_FLAGS[solidity]
    return builders.make_brush_actor(name, b, location=at, csg="add", poly_flags=pf)


def main():
    reuse = os.environ.get("UEDCLI_REUSE_EDITOR")
    ed_id = None
    if reuse:
        container = reuse
        log(f"REUSING editor container {container}")
    else:
        ed_id = uuid7()
        log(f"editor id {ed_id}")
        container = ensure_editor(ed_id, ready_timeout=120.0)
        log(f"editor container {container} ready")
    ed = Driver(container=container)
    try:
        # -------- CASE A: solid control --------
        log("\n===== CASE A: one SOLID cube in a subtracted room =====")
        ed.map_new(); settle(ed)
        add_brushes(ed, [build_room()])
        ed.rebuild(); settle(ed)
        solid = build_cube("SolidCube", "solid", (0, 0, 0))
        show_uedcli_emit(solid, "SOLID")
        add_brushes(ed, [solid])
        ed.rebuild(); settle(ed)
        emit_polyflag_lines(export_probe(ed, "A_solid_export"))
        okA = save_probe(ed, "A_solid")

        # -------- CASE B: one semisolid --------
        log("\n===== CASE B: one SEMISOLID cube in a subtracted room =====")
        ed.map_new(); settle(ed)
        add_brushes(ed, [build_room()])
        ed.rebuild(); settle(ed)
        semi = build_cube("SemiCube", "semisolid", (0, 0, 0))
        show_uedcli_emit(semi, "SEMISOLID")
        add_brushes(ed, [semi])
        ed.rebuild(); settle(ed)
        emit_polyflag_lines(export_probe(ed, "B_semi_export"))
        okB = save_probe(ed, "B_semi")

        # -------- CASE C: editor-native semisolid --------
        log("\n===== CASE C: editor-native semisolid (MAP SETBRUSH SETFLAGS=32) =====")
        ed.map_new(); settle(ed)
        add_brushes(ed, [build_room()])
        ed.rebuild(); settle(ed)
        add_brushes(ed, [build_cube("PlainAdd", "solid", (0, 0, 0))])
        ed.rebuild(); settle(ed)
        ed.selectname("PlainAdd"); settle(ed, 1.0)
        off = ed.log_size()
        ed.exec("MAP SETBRUSH SETFLAGS=32"); settle(ed, 1.0)
        log("  MAP SETBRUSH SETFLAGS=32 log:")
        for l in ed.read_log_since(off).splitlines():
            if l.strip():
                log("   |", l)
        ed.rebuild(); settle(ed)
        emit_polyflag_lines(export_probe(ed, "C_native_export"))
        okC = save_probe(ed, "C_native")

        log("\n===== SUMMARY =====")
        log(f"  A solid     saved: {okA}")
        log(f"  B semisolid saved: {okB}")
        log(f"  C native    saved: {okC}")
    finally:
        if ed_id is not None:
            stop_editor(ed_id)
            log("editor torn down")
        else:
            log("(reused editor left running)")


if __name__ == "__main__":
    sys.exit(main())

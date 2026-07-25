#!/usr/bin/env python3
"""Spike driver for LevelInfo update mechanisms. Runs on the HOST, drives the
ephemeral `uned-liupdate` container's UnrealEd via docker exec wine_ctl.py.

Liveness-checked; aborts (EditorDead) the instant the editor dies, naming the op.
"""
import re
import subprocess
import sys
import time

CONT = "uned-liupdate"
WCTL = ["docker", "exec", CONT, "python3", "/repo/Tools/uedctl/uned/wine_ctl.py"]
DELAY = 1.2


class EditorDead(RuntimeError):
    pass


def alive():
    r = subprocess.run(WCTL + ["status"], capture_output=True, text=True)
    return "alive=True" in r.stdout and "unresolved" not in r.stdout


def ex(line, check=True, settle=DELAY):
    r = subprocess.run(WCTL + ["exec", line], capture_output=True, text=True)
    time.sleep(settle)
    if check and not alive():
        raise EditorDead(f"editor died after: {line}\nstderr={r.stderr}")
    return r


def put(content, tag):
    """Write a T3D file into the container's /repo/Temp and return its Z: path."""
    path = f"/repo/Temp/li_{tag}.t3d"
    subprocess.run(["docker", "exec", "-i", CONT, "tee", path],
                   input=content, text=True, capture_output=True, check=True)
    return "Z:\\repo\\Temp\\li_" + tag + ".t3d"


def export(tag):
    """MAP EXPORT to a file, cat it back out as text."""
    zp = f"Z:\\repo\\Temp\\liexp_{tag}.t3d"
    ex(f"MAP EXPORT FILE={zp}")
    r = subprocess.run(["docker", "exec", CONT, "cat", f"/repo/Temp/liexp_{tag}.t3d"],
                       capture_output=True, text=True)
    return r.stdout


def levelinfo_block(t3d):
    """Extract the first LevelInfo/DeusExLevelInfo Begin Actor..End Actor block."""
    m = re.search(r"(Begin Actor Class=(?:DeusEx)?LevelInfo .*?End Actor)", t3d, re.S)
    return m.group(1) if m else "<no LevelInfo block found>"


def all_actor_headers(t3d):
    return re.findall(r"Begin Actor Class=(\S+) Name=(\S+)", t3d)

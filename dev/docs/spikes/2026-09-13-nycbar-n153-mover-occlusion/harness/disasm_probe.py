#!/usr/bin/env python3
r"""Dump live disassembly of `render.dll` ranges around `URender::GetVisibleSurfs`/`OccludeBsp`
(0x100187b0..0x1001a400, per-node filter steps documented in
`port-urender-getvisiblesurfs-so-each-light-gets/overview.md`), to pin the EXACT register holding
the current node's `iSurf` (FBspNode+0x1c) at each filter checkpoint -- needed before a targeted
breakpoint probe can log per-node outcomes for NYC_Bar N=153's tread surfaces (95/97/67) during
Light5's gather pass.

No MAP command is run -- render.dll is already mapped at editor idle (viewport init loads it), so a
static `disas` under a live-attached gdb is enough. `--out` gets the raw disassembly text.

Usage: disasm_probe.py [--out log]
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
OLD_HARNESS = ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"
OLD_ORACLE = OLD_HARNESS / "editor-tree-oracle"
LADDER = ROOT / "dev/docs/spikes/2026-09-03-incremental-actor-parity/harness"
UNBUILT = ROOT / "dev/docs/spikes/2026-09-02-unbuilt-structure-parity/harness"
HERE = Path(__file__).resolve().parent
for p in (ROOT, OLD_HARNESS, OLD_ORACLE, LADDER, UNBUILT):
    sys.path.insert(0, str(p))

import editor_tree_oracle as O  # noqa: E402
from uedcli import config  # noqa: E402
from build_ued_golden import _scratch_project  # noqa: E402

CONTAINER = "uned-n153-disasm"
RENDER_PREF = 0x10000000

# (label, start RVA, length bytes) -- ranges bracketing each documented filter step.
RANGES = [
    ("gvs_entry", 0x100187b0, 0x200),
    ("occludebsp_top", 0x10018e10, 0x200),
    ("zonemask_prune", 0x100192e0, 0x100),
    ("movingbrush_filter", 0x10019320, 0x60),
    ("box_occlusion", 0x10019380, 0x1a0),
    ("isfront_frustum", 0x10019680, 0x200),
    ("backface_portal_pawn", 0x100198a0, 0x100),
    ("zone_reach_emit", 0x10019940, 0x100),
    ("adduniqueitem_call", 0x100120a0, 0x40),
]


def remap(addr: int, live_base: int) -> int:
    return live_base + (addr - RENDER_PREF)


def _find_render_base(container: str, pid: int) -> int:
    maps = subprocess.run(["docker", "exec", container, "cat", f"/proc/{pid}/maps"],
                          capture_output=True, text=True, check=True).stdout
    for line in maps.splitlines():
        if "render.dll" in line.lower():
            return int(line.split("-", 1)[0], 16)
    raise RuntimeError("render.dll not found")


def main() -> int:
    out = HERE.parent / "logs" / "disasm.log"
    for i, a in enumerate(sys.argv):
        if a == "--out":
            out = Path(sys.argv[i + 1]).resolve()

    trunk_dir = ROOT / "_scratch/actor-parity/02_nyc_bar/N153/maps/02_nyc_bar"
    project = _scratch_project(trunk_dir, "deusex")
    search_dirs = config.composed_search_dirs(project, config.load_user_config())
    from uedcli.container_assets import resource_mounts
    mounts = resource_mounts(search_dirs)

    O._ensure_dbg_image()
    state_dir = config.state_dir(project.root, create=True)
    O.stop_dbg_editor(CONTAINER, state_dir)
    print(f"[disasm] starting {CONTAINER}", flush=True)
    O.start_dbg_editor(CONTAINER, mounts, state_dir)
    try:
        pid = O._editor_pid(CONTAINER)
        # give the viewport a moment to init and load render.dll
        render_base = None
        for _ in range(60):
            try:
                render_base = _find_render_base(CONTAINER, pid)
                break
            except RuntimeError:
                time.sleep(1.0)
        if render_base is None:
            raise RuntimeError("render.dll never appeared")
        print(f"[disasm] render.dll live base = {render_base:#x}", flush=True)

        cmds = ["set pagination off", "set confirm off", "set height 0", "set width 0",
                f"attach {pid}",
                "handle SIGSEGV nostop noprint pass", "handle SIGUSR1 nostop noprint pass",
                "handle SIGUSR2 nostop noprint pass", "handle SIGPIPE nostop noprint pass"]
        for label, rva, length in RANGES:
            va = remap(rva, render_base)
            cmds.append(f'printf "=== {label} @ {va:#x} ===\\n"')
            cmds.append(f"x/{length // 1}xb {va:#x}")
            cmds.append(f"disassemble {va:#x}, {va+length:#x}")
        cmds.append("detach")
        cmds.append("quit")
        script = "\n".join(cmds) + "\n"
        subprocess.run(["docker", "exec", "-i", CONTAINER, "bash", "-c", "cat > /tmp/disasm.gdb"],
                       input=script, text=True, check=True)
        r = subprocess.run(["docker", "exec", CONTAINER, "bash", "-c",
                            "gdb -batch -x /tmp/disasm.gdb 2>&1"],
                           capture_output=True, text=True, timeout=120)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(f"render.dll live base = {render_base:#x}\n\n" + r.stdout)
        print(f"[disasm] wrote {out}", flush=True)
    finally:
        O.stop_dbg_editor(CONTAINER, state_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

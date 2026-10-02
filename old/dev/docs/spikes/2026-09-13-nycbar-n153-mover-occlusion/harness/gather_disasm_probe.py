#!/usr/bin/env python3
r"""Disassemble Editor.dll's gather routine (`0x100a4ba0`..`0x100a5010`, the caller of
`URender::GetVisibleSurfs` that decides which (surf, light) pairs `illuminateSurf` actually
raytraces) to find the per-(light,surf) filter applied AFTER `GetVisibleSurfs` returns its iSurfs
set but BEFORE a surf's light list is committed. Editor.dll does not relocate under Wine (keeps its
preferred 0x10000000 base), so no live-base remap is needed.

Context: `mover_occlusion_probe.py` proved `GetVisibleSurfs` DOES add NYC_Bar N=153's world tread
surfs 95/97/67 to `Light5`'s visible set; `illuminate_ray_probe.py` then proved `illuminateSurf`'s
per-lumel `LineCheck` (`0x100a5a04`) is NEVER CALLED for these 3 surfs at all (zero hits despite
`illuminateSurf` itself being entered once per surf) -- meaning something between the two drops
Light5 from these surfs' per-surface light list before the per-lumel raytrace ever runs. The known
plane-distance cull (`0x100a4ec6`, `WorldLightRadius >= |Plane.PlaneDot(light.Location)|`) was
already ruled out by measurement (145-161 uu << Light5's 325 uu radius). This dump is to find what
else is between GetVisibleSurfs's return and the commit.

Usage: gather_disasm_probe.py [--out log]
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
OLD_HARNESS = ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"
OLD_ORACLE = OLD_HARNESS / "editor-tree-oracle"
HERE = Path(__file__).resolve().parent
for p in (ROOT, OLD_HARNESS, OLD_ORACLE):
    sys.path.insert(0, str(p))

import editor_tree_oracle as O  # noqa: E402
from uedcli import config  # noqa: E402
from build_ued_golden import _scratch_project  # noqa: E402

CONTAINER = "uned-n153-gather-disasm"

RANGES = [
    ("gather_top", 0x100a4ba0, 0x400),
    ("plane_dist_filter", 0x100a4d00, 0x400),
    ("after_gvs_call", 0x100a5000, 0x20),
]


def main() -> int:
    out = HERE.parent / "logs" / "gather-disasm.log"
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
    print(f"[gather-disasm] starting {CONTAINER}", flush=True)
    O.start_dbg_editor(CONTAINER, mounts, state_dir)
    try:
        pid = O._editor_pid(CONTAINER)
        cmds = ["set pagination off", "set confirm off", "set height 0", "set width 0",
                f"attach {pid}",
                "handle SIGSEGV nostop noprint pass", "handle SIGUSR1 nostop noprint pass",
                "handle SIGUSR2 nostop noprint pass", "handle SIGPIPE nostop noprint pass"]
        for label, va, length in RANGES:
            cmds.append(f'printf "=== {label} @ {va:#x} ===\\n"')
            cmds.append(f"disassemble {va:#x}, {va+length:#x}")
        cmds.append("detach")
        cmds.append("quit")
        script = "\n".join(cmds) + "\n"
        subprocess.run(["docker", "exec", "-i", CONTAINER, "bash", "-c", "cat > /tmp/gd.gdb"],
                       input=script, text=True, check=True)
        r = subprocess.run(["docker", "exec", CONTAINER, "bash", "-c",
                            "gdb -batch -x /tmp/gd.gdb 2>&1"],
                           capture_output=True, text=True, timeout=120)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(r.stdout)
        print(f"[gather-disasm] wrote {out}", flush=True)
    finally:
        O.stop_dbg_editor(CONTAINER, state_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
r"""Disassemble render.dll around RVA 0x10019a40..0x10019b40 (right after the ClipBspSurf call site
0x10019987, `2026-09-06-raster-clipbspsurf-port/spike.md`'s documented scanline-setup call site
"0x10019a6c") to find the EXACT `call` instruction inside `URender::OccludeBsp` that invokes the raw
scanline setup (`render.dll 0x1001b470`, documented to crash the container when breakpointed at its
own entry -- shared with real-time viewport rendering).

The goal: breakpoint the CALL SITE inside OccludeBsp instead of the callee's entry. OccludeBsp itself
is gather-exclusive (confirmed working for full LIGHT APPLY runs by
`2026-09-13-nycbar-n153-mover-occlusion/harness/raster_order_probe.py`'s 0x10019c1c breakpoint) --
only the shared low-level routine's OWN body is unsafe to trap. A breakpoint on the call instruction
(and on call+5, its return point) sees the same NumPts/Pts/Span/Frame->Y arguments (cdecl, already on
the stack) and the same output globals (G_MINX etc.) once it returns, without ever placing a trap
inside the hot shared body.

No MAP command is run -- render.dll is already mapped at editor idle. `--out` gets the raw text.
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

CONTAINER = "uned-n201-disasm-callsite"
RENDER_PREF = 0x10000000
START = 0x10019940
LENGTH = 0x200


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
    out = HERE.parent / "logs" / "disasm-callsite.log"
    for i, a in enumerate(sys.argv):
        if a == "--out":
            out = Path(sys.argv[i + 1]).resolve()

    trunk_dir = ROOT / "_scratch/actor-parity/06_hongkong_wanchai_market/N201/maps/06_hongkong_wanchai_market"
    project = _scratch_project(trunk_dir, "deusex")
    search_dirs = config.composed_search_dirs(project, config.load_user_config())
    from uedcli.container_assets import resource_mounts
    mounts = resource_mounts(search_dirs)

    O._ensure_dbg_image()
    state_dir = config.state_dir(project.root, create=True)
    O.stop_dbg_editor(CONTAINER, state_dir)
    print(f"[disasm-cs] starting {CONTAINER}", flush=True)
    O.start_dbg_editor(CONTAINER, mounts, state_dir)
    try:
        pid = O._editor_pid(CONTAINER)
        render_base = None
        for _ in range(60):
            try:
                render_base = _find_render_base(CONTAINER, pid)
                break
            except RuntimeError:
                time.sleep(1.0)
        if render_base is None:
            raise RuntimeError("render.dll never appeared")
        print(f"[disasm-cs] render.dll live base = {render_base:#x}", flush=True)

        va = remap(START, render_base)
        cmds = ["set pagination off", "set confirm off", "set height 0", "set width 0",
                f"attach {pid}",
                "handle SIGSEGV nostop noprint pass", "handle SIGUSR1 nostop noprint pass",
                "handle SIGUSR2 nostop noprint pass", "handle SIGPIPE nostop noprint pass",
                f'printf "=== callsite_window @ {va:#x} ===\\n"',
                f"disassemble {va:#x}, {va+LENGTH:#x}",
                "detach", "quit"]
        script = "\n".join(cmds) + "\n"
        subprocess.run(["docker", "exec", "-i", CONTAINER, "bash", "-c", "cat > /tmp/dcs.gdb"],
                       input=script, text=True, check=True)
        r = subprocess.run(["docker", "exec", CONTAINER, "bash", "-c",
                            "gdb -batch -x /tmp/dcs.gdb 2>&1"],
                           capture_output=True, text=True, timeout=120)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(f"render.dll live base = {render_base:#x}\n\n" + r.stdout)
        print(f"[disasm-cs] wrote {out}", flush=True)
    finally:
        O.stop_dbg_editor(CONTAINER, state_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
r"""Round 8 (2026-09-15): static disassembly to FIND the real call site(s) that reach
`TArray<INT>::AddUniqueItem` (`render.dll 0x100120b0`) from `URender::GetVisibleSurfs`/`OccludeBsp`,
so a later live probe can break AT THE CALL SITE (still in the CALLER's own frame -- no inheritance
ambiguity) instead of the callee entry (which round 7 found inherits an unidentified caller frame).

Round 7 left this exact gap: `mover_occlusion_probe.py`'s `ADD_ENTRY` breakpoint sits at the callee's
own entry (before `push %ebp`), so `$ebp` there is still the CALLER's frame -- reading a light origin
from it needs first knowing which caller and which slot. This probe widens the disassembly net to
find that caller:

  - `gvs_body`: `URender::GetVisibleSurfs` (0x100187b0) for 0x700 bytes -- `disasm_probe.py`'s
    original `gvs_entry` range only covered the first 0x200 bytes (the 6-cube-face `FSceneNode` setup
    switch); this widens past it into the actual per-face dispatch loop (the `call *0x64(%eax)` at
    RVA ~0x100187e4 body, live 0x015c8994, already seen) and whatever runs after each face's call
    returns.
  - `occludebsp_tail`: 0x1001a430 (the round-7-identified "commit new record" write site, RVA
    0x1001a43e writes `iSurf` into the output record) for 0x600 bytes -- the natural place to look
    for an immediately-following `iSurfs.AddUniqueItem(iSurf)` call, if OccludeBsp itself makes it
    rather than its caller.

No MAP command is run -- render.dll is already mapped at editor idle (viewport init loads it), so a
static `disas` under a live-attached gdb is enough, same method as `disasm_probe.py`.

Usage: disasm_wide_probe.py [--out log]
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
LADDER = ROOT / "dev/docs/spikes/2026-09-03-incremental-actor-parity/harness"
OLD_HARNESS = ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"
OLD_ORACLE = OLD_HARNESS / "editor-tree-oracle"
HERE = Path(__file__).resolve().parent
for p in (ROOT, OLD_HARNESS, OLD_ORACLE, LADDER):
    sys.path.insert(0, str(p))

import editor_tree_oracle as O  # noqa: E402
from uedcli import config  # noqa: E402
from build_ued_golden import _scratch_project  # noqa: E402

CONTAINER = "uned-n153-disasm-wide"
RENDER_PREF = 0x10000000

RANGES = [
    ("gvs_body", 0x100187b0, 0x700),
    ("occludebsp_tail", 0x1001a430, 0x600),
    # AddUniqueItem's own callee body -- confirm the TArray<INT> shape (element size 4, the
    # duplicate-scan loop, the append) so the caller's argument-setup code is recognizable.
    ("adduniqueitem_body", 0x100120a0, 0x120),
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
    out = HERE.parent / "logs" / "disasm-wide.log"
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
    print(f"[disasm-wide] starting {CONTAINER}", flush=True)
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
        print(f"[disasm-wide] render.dll live base = {render_base:#x}", flush=True)

        cmds = ["set pagination off", "set confirm off", "set height 0", "set width 0",
                f"attach {pid}",
                "handle SIGSEGV nostop noprint pass", "handle SIGUSR1 nostop noprint pass",
                "handle SIGUSR2 nostop noprint pass", "handle SIGPIPE nostop noprint pass"]
        for label, rva, length in RANGES:
            va = remap(rva, render_base)
            cmds.append(f'printf "=== {label} @ {va:#x} (rva {rva:#x}) ===\\n"')
            cmds.append(f"disassemble {va:#x}, {va+length:#x}")
        cmds.append("detach")
        cmds.append("quit")
        script = "\n".join(cmds) + "\n"
        subprocess.run(["docker", "exec", "-i", CONTAINER, "bash", "-c", "cat > /tmp/disasm_wide.gdb"],
                       input=script, text=True, check=True)
        r = subprocess.run(["docker", "exec", CONTAINER, "bash", "-c",
                            "gdb -batch -x /tmp/disasm_wide.gdb 2>&1"],
                           capture_output=True, text=True, timeout=120)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(f"render.dll live base = {render_base:#x}\n\n" + r.stdout)
        print(f"[disasm-wide] wrote {out}", flush=True)
    finally:
        O.stop_dbg_editor(CONTAINER, state_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

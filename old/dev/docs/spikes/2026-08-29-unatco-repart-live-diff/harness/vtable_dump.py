#!/usr/bin/env python3
r"""Live GDB capture: `UModel`'s vtable pointer and the 4 virtual-function addresses
`bspRepartition` dispatches through (`bspBuildFPolys`/`bspMergeCoplanars`/`bspBuild`/`bspRefresh`,
vtable slots `+0x20c`/`+0x210`/`+0x1fc`/`+0x200`), captured at `bspRepartition`'s own entry
(`0x10049fc0`) via `$ecx` (confirmed via disassembly, 2026-08-30, to be the real "this" — see the
board item's "calling-convention hypothesis ... REFUTED" section).

WHY: `unatco-verts-points-residual-after-the-zone` — disassembling `bspRepartition`'s own body
(2026-08-30) found it is SHORT (just the 4 sequential virtual calls, no extra "commit" logic after
`bspRefresh`), and that `bspBuild` (vtable `+0x1fc`) unexpectedly takes `iChild` as an EXPLICIT
argument (not just `ctx/opt/balance`) — meaning any "graft this subtree in at iChild" logic most
likely lives INSIDE `bspBuild` itself, not in `bspRepartition`'s caller. This dumps the real function
addresses so `bspBuild`/`bspRefresh` can be disassembled directly (no live process needed for that
step — Editor.dll is loaded at its natural image base under Wine in this container, ASLR off, so a
live VA converts straight to a DLL-file RVA via `rdis.py`).

Usage:  vtable_dump.py [golden.dx]
"""
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
OLD_HARNESS = ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"
OLD_ORACLE = OLD_HARNESS / "editor-tree-oracle"
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(OLD_HARNESS))
sys.path.insert(0, str(OLD_ORACLE))
import editor_tree_oracle as O  # noqa: E402
from uedcli import config  # noqa: E402
from uedcli.container_assets import resource_mounts  # noqa: E402
from uedcli.driver import Driver, to_z_path  # noqa: E402

GOLDEN = Path(sys.argv[1]) if len(sys.argv) > 1 else (
    ROOT / "_scratch/bsp-parity-proj/golden_unatco_control.dx")
PROJECT_DIR = ROOT / "_scratch/oracle-project"

GDB = r"""
set pagination off
set confirm off
set height 0
set width 0
attach {pid}
handle SIGSEGV nostop noprint pass
handle SIGUSR1 nostop noprint pass
handle SIGUSR2 nostop noprint pass
handle SIGPIPE nostop noprint pass
break *0x10049fc0
commands
silent
set $vtbl = *(unsigned int *)($ecx)
printf "VTDUMP model=%#x vtbl=%#x bspBuildFPolys=%#x bspMergeCoplanars=%#x bspBuild=%#x bspRefresh=%#x slot208=%#x slot218=%#x\n", $ecx, $vtbl, *(unsigned int*)($vtbl+0x20c), *(unsigned int*)($vtbl+0x210), *(unsigned int*)($vtbl+0x1fc), *(unsigned int*)($vtbl+0x200), *(unsigned int*)($vtbl+0x208), *(unsigned int*)($vtbl+0x218)
detach
quit
end
printf "ORACLE_ATTACHED\n"
continue
"""


def main() -> int:
    if not PROJECT_DIR.exists():
        PROJECT_DIR.mkdir(parents=True, exist_ok=True)
        (PROJECT_DIR / "uedcli.toml").write_text('game = "deusex"\n')

    O._ensure_dbg_image()
    project = config.load_project(str(PROJECT_DIR))
    user_config = config.load_user_config()
    mounts = resource_mounts(config.composed_search_dirs(project, user_config))
    state_dir = config.state_dir(project.root, create=True)

    container = "uned-vtdump"
    O.stop_dbg_editor(container, state_dir)
    print(f"[vtdump] golden={GOLDEN}", flush=True)
    print(f"[vtdump] starting {container} ...", flush=True)
    O.start_dbg_editor(container, mounts, state_dir)
    try:
        drv = Driver(container=container)
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /work/golden.dx"],
                       input=GOLDEN.read_bytes(), check=True)
        drv.exec(f"MAP LOAD FILE={to_z_path('/work/golden.dx')}")
        time.sleep(3.0)
        pid = O._editor_pid(container)
        print(f"[vtdump] editor pid {pid}; attaching gdb ...", flush=True)
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /tmp/vtd.gdb"],
                       input=GDB.format(pid=pid), text=True, check=True)
        subprocess.run(["docker", "exec", "-d", container, "bash", "-c",
                        "exec gdb -batch -x /tmp/vtd.gdb > /tmp/vtd.log 2>&1"], check=True)
        for _ in range(120):
            out = subprocess.run(["docker", "exec", container, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/vtd.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if out and out != "0":
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("gdb did not attach")
        print("[vtdump] attached; MAP REBUILD ...", flush=True)
        drv.exec("MAP REBUILD")
        for _ in range(120):
            done = subprocess.run(["docker", "exec", container, "bash", "-c",
                                   "grep -c '^VTDUMP' /tmp/vtd.log 2>/dev/null || true"],
                                  capture_output=True, text=True).stdout.strip()
            if done and done != "0":
                break
            time.sleep(1.0)
        out = HERE.parent / "logs" / "vtable-dump.log"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(subprocess.run(["docker", "exec", container, "cat", "/tmp/vtd.log"],
                                       capture_output=True).stdout)
        print(f"[vtdump] wrote {out}", flush=True)
        for line in out.read_text(errors="replace").splitlines():
            if line.startswith("VTDUMP"):
                print("  " + line)
    finally:
        O.stop_dbg_editor(container, state_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

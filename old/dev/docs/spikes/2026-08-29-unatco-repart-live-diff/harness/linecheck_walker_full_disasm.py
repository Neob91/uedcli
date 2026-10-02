#!/usr/bin/env python3
r"""Live GDB capture, round 6: full disassembly of the REAL recursive shadow-ray walker
`0x17ce190`, found live in round 3 (`linecheck_singlestep_rec14_v3.py`) and confirmed the actual
function real per-lumel shadow rays reach (unlike `target+0x5b0`, which rounds 1-2 mistakenly
decoded -- see `linecheck-target-disasm.log`, which is a full dump of the WRONG function).

Rounds 3-5 only ever set breakpoints at known offsets from `0x17ce190` (`+0x24`=CALL_ENTRY,
`+0xb9`=EARLY_RETURN_A, `+0x10c`=EARLY_RETURN_B, `+0x11e`=CROSS_ENTRY, `+0x156`=CROSS_T,
`+0x1f7`=MID, `+0x224`=RECURSE_CALL) -- reverse-engineered by trial, never a full disassembly dump.
This round captures a full `x/400i 0x17ce190` (the function is known small, spanning at most from
0x17ce190 to a bit past 0x17ce3b4+RECURSE_CALL's own tail) straight from live process memory (no
RVA/base-address translation needed -- this address is directly breakpointable and has been STABLE
across every restart in rounds 3-5), to resolve round 5's open question: the per-node loop/child-
select mechanics, and whether a second (near-side) recursive call ever happens or the walk is a
single self-call in tail position (i.e. compiler-tail-call-optimized loop) for every case.

Usage: linecheck_walker_full_disasm.py [golden.dx]
  -> logs/linecheck-walker-full-disasm.log
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
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(OLD_HARNESS))
sys.path.insert(0, str(OLD_ORACLE))
import editor_tree_oracle as O  # noqa: E402
from uedcli import config  # noqa: E402
from uedcli.container_assets import resource_mounts  # noqa: E402
from uedcli.driver import Driver, to_z_path  # noqa: E402

GOLDEN = Path(sys.argv[1]) if len(sys.argv) > 1 else (
    ROOT / "_scratch/wanchai-relight-2026-08-29/golden.dx")

PROJECT_DIR = ROOT / "_scratch/oracle-project"
CONTAINER = "uned-linecheck-walker-disasm"
LOGF = HERE.parent / "logs" / "linecheck-walker-full-disasm.log"

GDB = r"""
set pagination off
set confirm off
set height 0
set width 0
attach __PID__
handle SIGSEGV nostop noprint pass
handle SIGUSR1 nostop noprint pass
handle SIGUSR2 nostop noprint pass
handle SIGPIPE nostop noprint pass
printf "DISASM_START\n"
x/400i 0x17ce190
printf "DISASM_END\n"
detach
quit
"""


def main() -> int:
    if not GOLDEN.exists():
        print(f"[walker-disasm] golden not found: {GOLDEN}", file=sys.stderr)
        return 2
    if not PROJECT_DIR.exists():
        PROJECT_DIR.mkdir(parents=True, exist_ok=True)
        (PROJECT_DIR / "uedcli.toml").write_text('game = "deusex"\n')

    O._ensure_dbg_image()
    project = config.load_project(str(PROJECT_DIR))
    user_config = config.load_user_config()
    mounts = resource_mounts(config.composed_search_dirs(project, user_config))
    state_dir = config.state_dir(project.root, create=True)

    O.stop_dbg_editor(CONTAINER, state_dir)
    print(f"[walker-disasm] golden={GOLDEN}", flush=True)
    print(f"[walker-disasm] starting {CONTAINER} ...", flush=True)
    O.start_dbg_editor(CONTAINER, mounts, state_dir)
    try:
        drv = Driver(container=CONTAINER)
        subprocess.run(["docker", "exec", "-i", CONTAINER, "bash", "-c", "cat > /work/golden.dx"],
                       input=GOLDEN.read_bytes(), check=True)
        drv.exec(f"MAP LOAD FILE={to_z_path('/work/golden.dx')}")
        time.sleep(3.0)
        pid = O._editor_pid(CONTAINER)
        print(f"[walker-disasm] editor pid {pid}; attaching gdb ...", flush=True)
        gdb_script = GDB.replace("__PID__", str(pid))
        subprocess.run(["docker", "exec", "-i", CONTAINER, "bash", "-c", "cat > /tmp/lwd.gdb"],
                       input=gdb_script, text=True, check=True)
        result = subprocess.run(
            ["docker", "exec", CONTAINER, "bash", "-c", "gdb -batch -x /tmp/lwd.gdb"],
            capture_output=True, timeout=120)
        LOGF.parent.mkdir(parents=True, exist_ok=True)
        LOGF.write_bytes(result.stdout + b"\n--- STDERR ---\n" + result.stderr)
        print(f"[walker-disasm] wrote {LOGF} ({len(result.stdout)} bytes stdout)", flush=True)
    finally:
        O.stop_dbg_editor(CONTAINER, state_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

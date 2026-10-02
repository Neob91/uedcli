#!/usr/bin/env python3
r"""Live GDB capture: resolve the REAL virtual-call target of the editor's shadow-ray `LineCheck`
during a genuine Wanchai `LIGHT APPLY`, then disassemble it live (raw memory, no static-file
assumptions about which DLL/base it lives in).

Static disassembly this session (fresh, `rdis.py dis Editor 0x100a5900 0x160`, current tree) located
the exact call site inside `illuminateSurf`'s per-lumel loop:

    0x100a59f3  mov ecx, [eax+0x98]        ; ecx = Level->Model
    0x100a59f9  mov eax, [ecx]             ; eax = Model's vtable
    0x100a59fb  push 0
    0x100a59fd  lea edx, [ebp-0x1e4]
    0x100a5a03  push edx
    0x100a5a04  call dword ptr [eax + 0x58]  ; UModel::LineCheck virtual slot

This matches (and freshly re-derives, independent of the pre-2026-08-14 `20-lighting-bake.md` note)
the "Model vtable slot +0x58" claim. `line_clear_algorithm_check.py` found `linecheck.rs::line_clear`
disagrees with the editor's REAL bit even when fed the editor's own real BSP tree and ray endpoints,
predominantly (16/20 sampled) with native/the port reporting BLOCKED where the editor reports CLEAR,
localized (one manual trace) to a ray origin sitting ~0.0002uu off a splitting plane, where native's
strict `ds >= 0.0` sign test takes a spurious near-zero "crossing" split that a tolerant editor test
would not. This script checks that directly: what IS the editor's real near-plane classification
rule, at the true call target, on the current tree?

Usage: linecheck_target_disasm.py [golden.dx] [--hits N]
  -> logs/linecheck-target-disasm.log
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

GOLDEN = Path(sys.argv[1]) if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else (
    ROOT / "_scratch/wanchai-relight-2026-08-29/golden.dx")
HITS = 3
for i, a in enumerate(sys.argv):
    if a == "--hits":
        HITS = int(sys.argv[i + 1])

PROJECT_DIR = ROOT / "_scratch/oracle-project"
CONTAINER = "uned-linecheck-target"
LOGF = HERE.parent / "logs" / "linecheck-target-disasm.log"

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
set $n = 0
break *0x100a5a04
commands
silent
set $model = $ecx
set $vtbl = *(int *)$model
set $target = *(int *)($vtbl + 0x58)
printf "HIT n=%d model=0x%x vtbl=0x%x target=0x%x\n", $n, $model, $vtbl, $target
set $inner = $target + 0x5b0
printf "INNER=0x%x\n", $inner
printf "DISASM_START\n"
x/900i $inner
printf "DISASM_END\n"
set $n = $n + 1
if $n >= __HITS__
  printf "TARGET_DONE\n"
  detach
  quit
end
continue
end
printf "ORACLE_ATTACHED\n"
continue
"""


def main() -> int:
    if not GOLDEN.exists():
        print(f"[linecheck-target] golden not found: {GOLDEN}", file=sys.stderr)
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
    print(f"[linecheck-target] golden={GOLDEN} hits={HITS}", flush=True)
    print(f"[linecheck-target] starting {CONTAINER} ...", flush=True)
    O.start_dbg_editor(CONTAINER, mounts, state_dir)
    try:
        drv = Driver(container=CONTAINER)
        subprocess.run(["docker", "exec", "-i", CONTAINER, "bash", "-c", "cat > /work/golden.dx"],
                       input=GOLDEN.read_bytes(), check=True)
        drv.exec(f"MAP LOAD FILE={to_z_path('/work/golden.dx')}")
        time.sleep(3.0)
        pid = O._editor_pid(CONTAINER)
        print(f"[linecheck-target] editor pid {pid}; attaching gdb ...", flush=True)
        gdb_script = GDB.replace("__PID__", str(pid)).replace("__HITS__", str(HITS))
        subprocess.run(["docker", "exec", "-i", CONTAINER, "bash", "-c", "cat > /tmp/lt.gdb"],
                       input=gdb_script, text=True, check=True)
        subprocess.run(["docker", "exec", "-d", CONTAINER, "bash", "-c",
                        "exec gdb -batch -x /tmp/lt.gdb > /tmp/lt.log 2>&1"], check=True)
        for _ in range(120):
            out = subprocess.run(["docker", "exec", CONTAINER, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/lt.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if out and out != "0":
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("gdb did not attach")
        print("[linecheck-target] attached; LIGHT APPLY ...", flush=True)
        drv.exec("LIGHT APPLY")
        deadline = time.monotonic() + 1800.0
        while time.monotonic() < deadline:
            done = subprocess.run(["docker", "exec", CONTAINER, "bash", "-c",
                                   "grep -c '^TARGET_DONE' /tmp/lt.log 2>/dev/null || true"],
                                  capture_output=True, text=True).stdout.strip()
            if done and done != "0":
                print("[linecheck-target] TARGET_DONE seen", flush=True)
                break
            time.sleep(2.0)
        else:
            print("[linecheck-target] WARNING: gave up waiting", flush=True)
        LOGF.parent.mkdir(parents=True, exist_ok=True)
        LOGF.write_bytes(subprocess.run(["docker", "exec", CONTAINER, "cat", "/tmp/lt.log"],
                                        capture_output=True).stdout)
        print(f"[linecheck-target] wrote {LOGF}", flush=True)
    finally:
        O.stop_dbg_editor(CONTAINER, state_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
r"""EXPLORATORY, one-off: dump raw memory around the CTX object's `Polys` member (`CTX+0x54`) at
the world-level bspBuildFPolys-return breakpoint (`0x1004a00d`), to find the real FArray
{Data,Count,Max} field offsets -- the `[[CTX+0x54]+0x2c]` guess from an earlier (REFUTED-elsewhere,
but this specific structural sub-fact was never independently re-verified) findings-ledger entry
produced garbage (`data=0x535 count=1449 max=91422268`) when tried live this round
(`fpolys_stage_order.py`). Not meant to be a reusable harness tool -- throwaway probe, not committed
to the ledger as a fact until the real offsets are confirmed.

Usage: ctx_polys_struct_probe.py <golden.dx>
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

GOLDEN = Path(sys.argv[1])
PROJECT_DIR = ROOT / "_scratch/oracle-project"

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
set $callidx = 0
break *0x10049fc0
commands
silent
set $callidx = $callidx + 1
continue
end
break *0x1004a00d
commands
silent
if $callidx == 1
  set $eax = *(unsigned int *)($edi + 0xa8)
  set $ctx = *(unsigned int *)($eax + 0x98)
  set $polysobj = *(unsigned int *)($ctx + 0x54)
  printf "PROBE edi=%#x ctx=%#x polysobj=%#x\n", $edi, $ctx, $polysobj
  printf "CTX_DWORDS:"
  set $i = 0
  while $i < 0x30
    printf " [%#x]=%#x", $i, *(unsigned int*)($ctx+$i)
    set $i = $i + 4
  end
  printf "\n"
  printf "POLYSOBJ_DWORDS:"
  set $i = 0
  while $i < 0x50
    printf " [%#x]=%#x", $i, *(unsigned int*)($polysobj+$i)
    set $i = $i + 4
  end
  printf "\n"
  detach
  quit
end
continue
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

    container = "uned-ctxprobe"
    O.stop_dbg_editor(container, state_dir)
    print(f"[ctxprobe] golden={GOLDEN}", flush=True)
    O.start_dbg_editor(container, mounts, state_dir)
    try:
        drv = Driver(container=container)
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /work/golden.dx"],
                       input=GOLDEN.read_bytes(), check=True)
        drv.exec(f"MAP LOAD FILE={to_z_path('/work/golden.dx')}")
        time.sleep(3.0)
        pid = O._editor_pid(container)
        print(f"[ctxprobe] editor pid {pid}; attaching gdb ...", flush=True)
        gdb_script = GDB.replace("__PID__", str(pid))
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /tmp/cp.gdb"],
                       input=gdb_script, text=True, check=True)
        subprocess.run(["docker", "exec", "-d", container, "bash", "-c",
                        "exec gdb -batch -x /tmp/cp.gdb > /tmp/cp.log 2>&1"], check=True)
        for _ in range(120):
            out = subprocess.run(["docker", "exec", container, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/cp.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if out and out != "0":
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("gdb did not attach")
        print("[ctxprobe] attached; MAP REBUILD ...", flush=True)
        drv.exec("MAP REBUILD")
        deadline = time.monotonic() + 600.0
        while time.monotonic() < deadline:
            done = subprocess.run(["docker", "exec", container, "bash", "-c",
                                   "grep -c '^PROBE' /tmp/cp.log 2>/dev/null || true"],
                                  capture_output=True, text=True).stdout.strip()
            if done and done != "0":
                print("[ctxprobe] PROBE seen", flush=True)
                break
            time.sleep(2.0)
        else:
            print("[ctxprobe] WARNING: gave up", flush=True)
        out = HERE.parent / "logs" / "ctx-polys-struct-probe.log"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(subprocess.run(["docker", "exec", container, "cat", "/tmp/cp.log"],
                                       capture_output=True).stdout)
        print(f"[ctxprobe] wrote {out}", flush=True)
        for line in out.read_text(errors="replace").splitlines():
            if line.startswith(("PROBE", "CTX_DWORDS", "POLYSOBJ_DWORDS")):
                print(line)
    finally:
        O.stop_dbg_editor(container, state_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

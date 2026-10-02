#!/usr/bin/env python3
r"""EXPLORATORY round 2: `ctx_polys_struct_probe.py`'s raw dword dump of the `Polys` UObject found
`[0x2c]=0x535(1333)` `[0x30]=0x5a9(1449)` (Count<Max, plausible pair) but no obvious Data pointer at
`+0x2c` (that offset holds the small int, not a pointer) -- the array layout is NOT the
`{Data@+0x2c}` guess from the earlier ledger entry. This probe tests CANDIDATE data-pointer dwords
(`+0x24`, `+0x28`, `+0x34`, `+0x38`) by dereferencing each as an FPoly* and printing the first
poly's normal/iLink/nv -- a real FPoly normal is unit-length-ish (components in [-1,1]), iLink is a
small int, nv is 3-16. Garbage memory will not look like that.

Usage: ctx_polys_struct_probe2.py <golden.dx>
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

CANDIDATES = ["0x24", "0x28", "0x34", "0x38", "0x3c"]

CAND_BLOCK = "\n".join(f'''
  set $cand = *(unsigned int *)($polysobj + {off})
  set $ok = 1
  set $nx = 0.0
  set $ny = 0.0
  set $nz = 0.0
  set $ilink = 0
  set $nv = 0
  printf "CAND off={off} ptr=%#x", $cand
  printf "\\n"
''' for off in CANDIDATES)

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
  printf "PROBE2 polysobj=%#x\n", $polysobj
  set $c24 = *(unsigned int *)($polysobj + 0x24)
  set $c28 = *(unsigned int *)($polysobj + 0x28)
  set $c34 = *(unsigned int *)($polysobj + 0x34)
  set $c38 = *(unsigned int *)($polysobj + 0x38)
  set $c3c = *(unsigned int *)($polysobj + 0x3c)
  printf "CAND24 ptr=%#x nv=%d ilink=%d N=%.4f,%.4f,%.4f\n", $c24, *(int*)($c24+0x1c0), *(int*)($c24+0x1c4), *(float*)($c24+0xc), *(float*)($c24+0x10), *(float*)($c24+0x14)
  printf "CAND28 ptr=%#x nv=%d ilink=%d N=%.4f,%.4f,%.4f\n", $c28, *(int*)($c28+0x1c0), *(int*)($c28+0x1c4), *(float*)($c28+0xc), *(float*)($c28+0x10), *(float*)($c28+0x14)
  printf "CAND34 ptr=%#x nv=%d ilink=%d N=%.4f,%.4f,%.4f\n", $c34, *(int*)($c34+0x1c0), *(int*)($c34+0x1c4), *(float*)($c34+0xc), *(float*)($c34+0x10), *(float*)($c34+0x14)
  printf "CAND38 ptr=%#x nv=%d ilink=%d N=%.4f,%.4f,%.4f\n", $c38, *(int*)($c38+0x1c0), *(int*)($c38+0x1c4), *(float*)($c38+0xc), *(float*)($c38+0x10), *(float*)($c38+0x14)
  printf "CAND3c ptr=%#x nv=%d ilink=%d N=%.4f,%.4f,%.4f\n", $c3c, *(int*)($c3c+0x1c0), *(int*)($c3c+0x1c4), *(float*)($c3c+0xc), *(float*)($c3c+0x10), *(float*)($c3c+0x14)
  printf "DONE2\n"
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

    container = "uned-ctxprobe2"
    O.stop_dbg_editor(container, state_dir)
    print(f"[ctxprobe2] golden={GOLDEN}", flush=True)
    O.start_dbg_editor(container, mounts, state_dir)
    try:
        drv = Driver(container=container)
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /work/golden.dx"],
                       input=GOLDEN.read_bytes(), check=True)
        drv.exec(f"MAP LOAD FILE={to_z_path('/work/golden.dx')}")
        time.sleep(3.0)
        pid = O._editor_pid(container)
        print(f"[ctxprobe2] editor pid {pid}; attaching gdb ...", flush=True)
        gdb_script = GDB.replace("__PID__", str(pid))
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /tmp/cp2.gdb"],
                       input=gdb_script, text=True, check=True)
        subprocess.run(["docker", "exec", "-d", container, "bash", "-c",
                        "exec gdb -batch -x /tmp/cp2.gdb > /tmp/cp2.log 2>&1"], check=True)
        for _ in range(120):
            out = subprocess.run(["docker", "exec", container, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/cp2.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if out and out != "0":
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("gdb did not attach")
        print("[ctxprobe2] attached; MAP REBUILD ...", flush=True)
        drv.exec("MAP REBUILD")
        deadline = time.monotonic() + 600.0
        while time.monotonic() < deadline:
            done = subprocess.run(["docker", "exec", container, "bash", "-c",
                                   "grep -c '^DONE2' /tmp/cp2.log 2>/dev/null || true"],
                                  capture_output=True, text=True).stdout.strip()
            if done and done != "0":
                print("[ctxprobe2] DONE2 seen", flush=True)
                break
            time.sleep(2.0)
        else:
            print("[ctxprobe2] WARNING: gave up", flush=True)
        out = HERE.parent / "logs" / "ctx-polys-struct-probe2.log"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(subprocess.run(["docker", "exec", container, "cat", "/tmp/cp2.log"],
                                       capture_output=True).stdout)
        print(f"[ctxprobe2] wrote {out}", flush=True)
        for line in out.read_text(errors="replace").splitlines():
            if line.startswith(("PROBE2", "CAND")):
                print(line)
    finally:
        O.stop_dbg_editor(container, state_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
r"""Live GDB capture: the editor's FULL `Model->Nodes` tree at the exact checkpoint
`repartition_frontier`'s 119 Wanchai calls are about to consume — Wanchai sibling of
`prepart_tree_unatco.py` (identical mechanism/offsets, different golden). See that script's
docstring for the full rationale; this is the Wanchai leg of
`wanchai-verts-points-residual-independently`'s "identify the specific ~8 calls" follow-up.

Usage:  prepart_tree_wanchai.py [golden.dx]   ->  logs/prepart-tree-wanchai.log
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
    ROOT / "_scratch/golden_wanchai_world.dx")
PROJECT_DIR = ROOT / "_scratch/oracle-project"
DEADLINE = 2400.0

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
set $callidx = 0
break *0x10049fc0
commands
silent
set $callidx = $callidx + 1
if $callidx == 2
  set $m = *(unsigned int *)($esp + 4)
  set $nd = *(unsigned int *)($m + 0x58)
  set $nn = *(int *)($m + 0x5c)
  set $sn = *(int *)($m + 0x9c)
  printf "TREEBEGIN nodes=%d surfs=%d\n", $nn, $sn
  set $i = 0
  while $i < $nn
    set $n = $nd + $i * 0x40
    printf "PRNODE %d isurf=%d nv=%d iB=%d iF=%d iP=%d nf=%d plane=%.5f,%.5f,%.5f,%.5f\n", $i, *(int *)($n + 0x1c), *(unsigned char *)($n + 0x36), *(int *)($n + 0x20), *(int *)($n + 0x24), *(int *)($n + 0x28), *(unsigned char *)($n + 0x37), *(float *)($n), *(float *)($n + 4), *(float *)($n + 8), *(float *)($n + 12)
    set $i = $i + 1
  end
  printf "TREEEND\n"
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

    container = "uned-prepart-wanchai"
    O.stop_dbg_editor(container, state_dir)
    print(f"[prepart] golden={GOLDEN}", flush=True)
    print(f"[prepart] starting {container} ...", flush=True)
    O.start_dbg_editor(container, mounts, state_dir)
    try:
        drv = Driver(container=container)
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /work/golden.dx"],
                       input=GOLDEN.read_bytes(), check=True)
        drv.exec(f"MAP LOAD FILE={to_z_path('/work/golden.dx')}")
        time.sleep(3.0)
        pid = O._editor_pid(container)
        print(f"[prepart] editor pid {pid}; attaching gdb ...", flush=True)
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /tmp/pptw.gdb"],
                       input=GDB.format(pid=pid), text=True, check=True)
        subprocess.run(["docker", "exec", "-d", container, "bash", "-c",
                        "exec gdb -batch -x /tmp/pptw.gdb > /tmp/pptw.log 2>&1"], check=True)
        for _ in range(120):
            out = subprocess.run(["docker", "exec", container, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/pptw.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if out and out != "0":
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("gdb did not attach")
        print("[prepart] attached; MAP REBUILD ...", flush=True)
        drv.exec("MAP REBUILD")
        deadline = time.monotonic() + DEADLINE
        while time.monotonic() < deadline:
            done = subprocess.run(["docker", "exec", container, "bash", "-c",
                                   "grep -c '^TREEEND' /tmp/pptw.log 2>/dev/null || true"],
                                  capture_output=True, text=True).stdout.strip()
            if done and done != "0":
                break
            time.sleep(2.0)
        else:
            print(f"[prepart] WARNING: gave up after {DEADLINE:.0f}s", flush=True)
        out = HERE.parent / "logs" / "prepart-tree-wanchai.log"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(subprocess.run(["docker", "exec", container, "cat", "/tmp/pptw.log"],
                                       capture_output=True).stdout)
        print(f"[prepart] wrote {out}", flush=True)
        text = out.read_text(errors="replace")
        n = text.count("\nPRNODE ")
        print(f"[prepart] {n} PRNODE lines captured", flush=True)
    finally:
        O.stop_dbg_editor(container, state_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

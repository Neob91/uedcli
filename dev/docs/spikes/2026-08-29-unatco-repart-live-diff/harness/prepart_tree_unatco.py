#!/usr/bin/env python3
r"""Live GDB capture: the editor's FULL `Model->Nodes` tree at the exact checkpoint
`repartition_frontier`'s 209 calls are about to consume — i.e. right as the FIRST of the ~209
per-subtree `bspRepartition` calls begins (the second `bspRepartition` entry overall: the first is
the WORLD repartition).  Pairs with native's `UEDCLI_BSPCSG_PREPART_NODES` dump (`bspcsg.rs`, "PRE-
REPARTITION-FRONTIER NODE DUMP") for a structural (not just aggregate-count) diff.

WHY. `unatco-verts-points-residual-after-the-zone`: applying `bsp_merge_coplanars` to every one of
the 209 `repartition_frontier` calls is proven correct PER CALL (7/7 live-verified against the real
editor, including the single biggest reduction and several large no-growth controls) yet still
undershoots the aggregate node total by ~625-634.  Both native and editor already agree EXACTLY on
the total node count at this checkpoint (6314=6314) — but the same count could still hide a
different SHAPE (different nodes acting as "frontier" leaves feeding into different subtree
rebuilds).  This dump lets `prepart_tree_diff.py` test that directly.

MECHANISM: `bspRepartition` entry is `Editor.dll 0x10049fc0`, `esp+4`=Model, `esp+8`=iChild.  The
FIRST call (idx=1) is the world repartition (iChild=0); its own `bspRefresh` (`0x1004a05f`) already
returns and its result becomes the post-detail-loop-eligible tree.  Nothing else changes `Model`
between the world repartition finishing and the SECOND `bspRepartition` entry (idx=2) firing — that
second entry point is exactly "right before consuming the pre-detail-loop frontier's first grown
subtree", matching native's `STAGE post-pass2` / `UEDCLI_BSPCSG_PREPART_NODES` checkpoint.  So: break
on idx==2, dump `Model->Nodes` (same `FBspNode` layout as `repart_tree_unatco.py`), detach — do NOT
let the call proceed (avoids perturbing anything downstream; we only need the read).

`FBspNode`: stride 0x40, Plane at +0x00 (x,y,z,w), iVertPool +0x18, iSurf +0x1c, iBack +0x20,
iFront +0x24, iPlane +0x28, NumVertices +0x36 (byte), NodeFlags +0x37 (byte).  Model fields:
Nodes.Data +0x58 / Num +0x5c ; Surfs.Num +0x9c.

Usage:  prepart_tree_unatco.py [golden.dx]   ->  logs/prepart-tree-unatco.log
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

    container = "uned-prepart-unatco"
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
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /tmp/pptu.gdb"],
                       input=GDB.format(pid=pid), text=True, check=True)
        subprocess.run(["docker", "exec", "-d", container, "bash", "-c",
                        "exec gdb -batch -x /tmp/pptu.gdb > /tmp/pptu.log 2>&1"], check=True)
        for _ in range(120):
            out = subprocess.run(["docker", "exec", container, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/pptu.log 2>/dev/null || true"],
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
                                   "grep -c '^TREEEND' /tmp/pptu.log 2>/dev/null || true"],
                                  capture_output=True, text=True).stdout.strip()
            if done and done != "0":
                break
            time.sleep(2.0)
        else:
            print(f"[prepart] WARNING: gave up after {DEADLINE:.0f}s", flush=True)
        out = HERE.parent / "logs" / "prepart-tree-unatco.log"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(subprocess.run(["docker", "exec", container, "cat", "/tmp/pptu.log"],
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

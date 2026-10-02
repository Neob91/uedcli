#!/usr/bin/env python3
"""Parameterized editor committed-incremental-tree dump for UNATCO at ARBITRARY N (§92 §53 bisect).

Generalizes editor_struct_unatco.py (hardcoded N=8) / editor_struct_unatco_bits.py (N=105) to any N,
for the (105,213] committed-tree bisection.  Dumps the editor's incremental Model->Nodes at
bspBuildFPolys ENTRY (= the committed, POST-rollback incremental tree, BEFORE repartition — the §40
raw-vs-kept-safe stage), with plane x,y,z,w HEX BITS so a 1-ULP node-w twin is distinguishable from a
structural divergence.

Auto-builds the cached golden{N}.dx if absent (target.golden -> unatco_subset.build_editor_subset,
which drives the editor with the generous --quiet-reads 30 barrier §92 stage 0 requires).

GUARDRAIL: bounded waits, unconditional gdb logging (per-call position filters CRASH the rebuild §52),
container torn down in finally.  Writes logs/editor-struct-unatco-<N>.log (the tree_struct_diff /
committed_tree_diff canonical location).

Usage:  editor_struct_unatco_n.py N [--out PATH]
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[6]      # Tools/uedcli (editor-tree-oracle/ -> harness/ -> spike/ -> spikes/ -> docs/ -> dev/ -> root)
HARNESS = ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"
HERE = HARNESS / "editor-tree-oracle"
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(HARNESS)); sys.path.insert(0, str(HERE))
import editor_tree_oracle as O
from uedcli.driver import Driver, to_z_path

VA = 0x10036090  # bspBuildFPolys

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
break *{va:#x}
commands
silent
set $model = *(unsigned int *)($esp + 4)
set $nodes = *(unsigned int *)($model + 0x58)
set $num = *(int *)($model + 0x5c)
printf "TREEBEGIN num=%d\n", $num
set $i = 0
while $i < $num
  set $n = $nodes + $i * 0x40
  printf "ND %d plane=%.5f,%.5f,%.5f,%.5f iF=%d iB=%d iP=%d isurf=%d nv=%d pbits=%#010x,%#010x,%#010x,%#010x\n", $i, *(float *)($n), *(float *)($n+4), *(float *)($n+8), *(float *)($n+0xc), *(int *)($n+0x24), *(int *)($n+0x20), *(int *)($n+0x28), *(int *)($n+0x1c), *(unsigned char *)($n+0x36), *(unsigned int *)($n), *(unsigned int *)($n+4), *(unsigned int *)($n+8), *(unsigned int *)($n+0xc)
  set $i = $i + 1
end
printf "TREEEND\n"
detach
quit
end
printf "ORACLE_ATTACHED\n"
continue
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("n", type=int)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    N = args.n
    OUT = args.out or (HERE / "logs" / f"editor-struct-unatco-{N}.log")
    OUT.parent.mkdir(parents=True, exist_ok=True)

    O._ensure_dbg_image()
    target = O.resolve_target("unatco")
    golden = target.golden(N)  # builds the cached golden{N}.dx if absent (drives the editor)
    project = target.project_dir
    mounts = O._composed_mounts(project)
    state_dir = O._state_dir(project)
    container = f"uned-estruct-unatco-n{N}"
    O.stop_dbg_editor(container, state_dir)
    print(f"starting {container} (golden={golden}) ...", flush=True)
    O.start_dbg_editor(container, mounts, state_dir)
    try:
        drv = Driver(container=container)
        try:
            ref = target.ref_pkgs(N)
            if ref:
                print(f"OBJ LOAD {len(ref)} referenced packages ...", flush=True)
                for p in ref:
                    try:
                        drv.exec(f"OBJ LOAD FILE={to_z_path(str(p))}")
                    except Exception as exc:
                        print(f"  WARN OBJ LOAD {p}: {exc}", flush=True)
        except Exception as exc:
            print(f"WARN ref_pkgs: {exc}", flush=True)
        # `docker cp` (either direction) remounts every one of the container's mounts read-only,
        # which rootless docker cannot do for the `:ro` /stubs bind mount ("remount-ro … operation
        # not permitted") — stream via `docker exec cat` instead (xfer.cp_out's fix, mirrored here
        # since this predates that fix and both directions hit it).
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /work/golden.dx"],
                       input=golden.read_bytes(), check=True)
        drv.exec(f"MAP LOAD FILE={to_z_path('/work/golden.dx')}")
        time.sleep(3.0)
        pid = O._editor_pid(container)
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /tmp/es.gdb"],
                       input=GDB.format(pid=pid, va=VA), text=True, check=True)
        subprocess.run(["docker", "exec", "-d", container, "bash", "-c",
                        "exec gdb -batch -x /tmp/es.gdb > /tmp/es.log 2>&1"], check=True)
        for _ in range(120):
            out = subprocess.run(["docker", "exec", container, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/es.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if out and out != "0":
                break
            time.sleep(0.5)
        print("attached; MAP REBUILD ...", flush=True)
        drv.exec("MAP REBUILD")
        for _ in range(900):
            done = subprocess.run(["docker", "exec", container, "bash", "-c",
                                   "grep -c TREEEND /tmp/es.log 2>/dev/null || true"],
                                  capture_output=True, text=True).stdout.strip()
            if done and done != "0":
                break
            time.sleep(1.0)
        with open(OUT, "wb") as f:
            subprocess.run(["docker", "exec", container, "cat", "/tmp/es.log"], check=True, stdout=f)
        nd = subprocess.run(["bash", "-c", f"grep -c '^ND ' {OUT}"], capture_output=True, text=True).stdout.strip()
        print(f"wrote {OUT} ({nd} ND lines)", flush=True)
    finally:
        O.stop_dbg_editor(container, state_dir)


if __name__ == "__main__":
    main()

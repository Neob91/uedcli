#!/usr/bin/env python3
"""Live gdb trace of the EDITOR's AddBrushToWorldFunc (Editor.dll RVA 0x31770, disassembly-confirmed
2026-09-01 against this tree's own uned/UED22/Editor.dll: args at ebp+8=Model ebp+c=iNode
ebp+0x10=EdPoly ebp+0x14=Filter ebp+0x18=Place; adds via bspAddNode only when Filter==0(Outside),
==2(CoplanarOutside), or ==5(CospatialFacingOut) with EdPoly->PolyFlags bit 0x20 (PF_Semisolid,
byte offset +0x1b0) clear -- byte-identical to uedcli-native's `leaf_func` LeafFunc::Add arm) during
MAP REBUILD of an Area51 Entrance N-brush subset. Every terminal classification the world-CSG Add
leaf callback receives, kept or discarded -- the ground truth for WHY a fragment survives or not.

Usage: area51_addfunc_oracle.py N   -> logs/area51-addfunc-N.log
"""
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
HARNESS = ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"
ORACLE_DIR = HARNESS / "editor-tree-oracle"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(ORACLE_DIR))
sys.path.insert(0, str(ROOT / "_scratch"))

import editor_tree_oracle as O  # noqa: E402
from uedcli.driver import Driver, to_z_path  # noqa: E402
import area51_subset  # noqa: E402

OUT_DIR = ROOT / "_scratch/area51-oracle-logs"

ADDFUNC_VA = 0x10031770

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
set $inode = *(int *)($esp + 8)
set $ed = *(unsigned int *)($esp + 0xc)
set $filter = *(int *)($esp + 0x10)
set $place = *(int *)($esp + 0x14)
set $pf = *(unsigned int *)($ed + 0x1b0)
printf "AFUNC model=%#x inode=%d filter=%d place=%d ilink=%d nv=%d pf=%#x N=%.5f,%.5f,%.5f B=%.5f,%.5f,%.5f\n", $model, $inode, $filter, $place, *(int *)($ed + 0x1c4), *(int *)($ed + 0x1c0), $pf, *(float *)($ed + 0xc), *(float *)($ed + 0x10), *(float *)($ed + 0x14), *(float *)($ed), *(float *)($ed + 4), *(float *)($ed + 8)
continue
end
printf "ORACLE_ATTACHED\n"
continue
"""


def _launch_gdb(container, pid):
    script = GDB.format(pid=pid, va=ADDFUNC_VA)
    subprocess.run(["docker", "exec", "-i", container, "bash", "-c",
                    "cat > /tmp/oracle.gdb"], input=script, text=True, check=True)
    subprocess.run(["docker", "exec", "-d", container, "bash", "-c",
                    "exec gdb -batch -x /tmp/oracle.gdb > /tmp/oracle.log 2>&1"], check=True)


def _wait_attached(container, timeout=60.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        out = subprocess.run(["docker", "exec", container, "bash", "-c",
                              "grep -c ORACLE_ATTACHED /tmp/oracle.log 2>/dev/null || true"],
                             capture_output=True, text=True).stdout.strip()
        if out and out != "0":
            return
        time.sleep(0.5)
    diag = subprocess.run(["docker", "exec", container, "cat", "/tmp/oracle.log"],
                          capture_output=True, text=True).stdout
    raise RuntimeError(f"gdb did not attach within {timeout}s. gdb log:\n{diag[:2000]}")


def _log_line_count(container):
    out = subprocess.run(["docker", "exec", container, "bash", "-c",
                          "grep -c '^AFUNC ' /tmp/oracle.log 2>/dev/null || true"],
                         capture_output=True, text=True).stdout.strip()
    return int(out) if out and out.isdigit() else 0


def _wait_quiescent(container, quiet_secs, hard_timeout=1200.0):
    deadline = time.monotonic() + hard_timeout
    last = -1
    last_change = time.monotonic()
    while time.monotonic() < deadline:
        n = _log_line_count(container)
        now = time.monotonic()
        if n != last:
            last, last_change = n, now
        elif n > 0 and (now - last_change) >= quiet_secs:
            return n
        time.sleep(1.0)
    return last


def run(n: int, quiet_secs: float = 6.0) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    O._ensure_dbg_image()
    golden = area51_subset.build_editor_subset(n)
    print(f"[a51-addfunc] golden N={n}: {golden}")

    project_dir = area51_subset.SUBSET_ROOT / f"trunk{n}"
    mounts = O._composed_mounts(project_dir)
    state_dir = O._state_dir(project_dir)
    container = f"uned-a51-addfunc-n{n}"
    O.stop_dbg_editor(container, state_dir)
    print(f"[a51-addfunc] starting {container} ...")
    O.start_dbg_editor(container, mounts, state_dir)
    try:
        drv = Driver(container=container)
        # `docker cp` (both directions) fails in this sandbox: rootless dockerd cannot remount the
        # container's `/stubs:ro` bind mount, which `docker cp`'s implementation touches regardless
        # of destination path ("remount-ro .../stubs: operation not permitted"). `docker exec -i cat`
        # bypasses it entirely (verified live 2026-09-01) -- use it for BOTH directions here.
        golden_bytes = golden.read_bytes()
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /work/golden.dx"],
                       input=golden_bytes, check=True)
        print("[a51-addfunc] MAP LOAD golden.dx ...")
        drv.exec(f"MAP LOAD FILE={to_z_path('/work/golden.dx')}")
        time.sleep(3.0)

        pid = O._editor_pid(container)
        print(f"[a51-addfunc] attaching gdb to editor pid {pid} ...")
        _launch_gdb(container, pid)
        _wait_attached(container)
        print("[a51-addfunc] gdb attached; issuing MAP REBUILD ...")
        drv.exec("MAP REBUILD")
        n_hits = _wait_quiescent(container, quiet_secs)
        print(f"[a51-addfunc] rebuild quiescent: {n_hits} AddBrushToWorldFunc calls logged")

        out = OUT_DIR / f"area51-addfunc-{n}.log"
        r = subprocess.run(["docker", "exec", container, "cat", "/tmp/oracle.log"],
                           capture_output=True, check=True)
        out.write_bytes(r.stdout)
        print(f"[a51-addfunc] wrote {out}")
        return out
    finally:
        O.stop_dbg_editor(container, state_dir)


if __name__ == "__main__":
    n = int(sys.argv[1])
    run(n)

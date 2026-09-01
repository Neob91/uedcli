#!/usr/bin/env python3
"""Live gdb trace of the EDITOR's AddBrushToWorldFunc (Editor.dll RVA 0x31770, disassembly-confirmed
against uned/UED22/Editor.dll: args at esp+4=Model esp+8=iNode esp+0xc=EdPoly esp+0x10=Filter
esp+0x14=Place -- byte-identical to `uedcli-native`'s `leaf_func` LeafFunc::Add arm) during
`MAP REBUILD` of an NSFHQ04 structural-only N-brush prefix golden. Same technique as Area51's
`area51_addfunc_oracle.py`, repointed at NSFHQ04's `Brush842` investigation (n=512 exact prefix,
n=513 adds Brush842, `d_nodes=+131 d_surfs=+0 d_leaves=+38`).

Reuses the ALREADY-BUILT prefix goldens under `_scratch/nsfhq04-prefix2/n{n:04d}/golden_n{n:04d}.dx`
(from `nsfhq04_prefix_search2.py`) rather than rebuilding -- `MAP LOAD` + `MAP REBUILD` replays the
SAME full incremental Pass-1 fold (csgRebuild EmptyModels then rebuilds purely from Actors[] order),
so tracing during the REBUILD of golden_n0513 reproduces the exact same AddBrushToWorldFunc call
sequence that BUILT it -- taking the tail past golden_n0512's own call count isolates Brush842's own
contribution (`nsfhq04_compare_tail.py`), same assumption `area51_compare_tail.py` relies on (Pass 1
is a strict per-brush sequential fold, confirmed independently in this investigation thread).

Usage: nsfhq04_addfunc_oracle.py N   -> _scratch/nsfhq04-oracle-logs/nsfhq04-addfunc-N.log
"""
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]  # harness/ -> spike/ -> spikes/ -> docs/ -> dev/ -> ROOT
HARNESS = ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"
ORACLE_DIR = HARNESS / "editor-tree-oracle"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(ORACLE_DIR))

import editor_tree_oracle as O  # noqa: E402
from uedcli.driver import Driver, to_z_path  # noqa: E402

OUT_DIR = ROOT / "_scratch/nsfhq04-oracle-logs"
PREFIX_ROOT = ROOT / "_scratch/nsfhq04-prefix2"

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
    project_dir = PREFIX_ROOT / f"n{n:04d}"
    golden = project_dir / f"golden_n{n:04d}.dx"
    if not golden.exists():
        raise SystemExit(f"golden not found: {golden} -- run nsfhq04_prefix_search2.py {n} first")
    print(f"[nsfhq04-addfunc] golden N={n}: {golden}")

    mounts = O._composed_mounts(project_dir)
    state_dir = O._state_dir(project_dir)
    container = f"uned-nsfhq04-addfunc-n{n}"
    O.stop_dbg_editor(container, state_dir)
    print(f"[nsfhq04-addfunc] starting {container} ...")
    O.start_dbg_editor(container, mounts, state_dir)
    try:
        drv = Driver(container=container)
        golden_bytes = golden.read_bytes()
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /work/golden.dx"],
                       input=golden_bytes, check=True)
        print("[nsfhq04-addfunc] MAP LOAD golden.dx ...")
        drv.exec(f"MAP LOAD FILE={to_z_path('/work/golden.dx')}")
        time.sleep(3.0)

        pid = O._editor_pid(container)
        print(f"[nsfhq04-addfunc] attaching gdb to editor pid {pid} ...")
        _launch_gdb(container, pid)
        _wait_attached(container)
        print("[nsfhq04-addfunc] gdb attached; issuing MAP REBUILD ...")
        drv.exec("MAP REBUILD")
        n_hits = _wait_quiescent(container, quiet_secs)
        print(f"[nsfhq04-addfunc] rebuild quiescent: {n_hits} AddBrushToWorldFunc calls logged")

        out = OUT_DIR / f"nsfhq04-addfunc-{n}.log"
        r = subprocess.run(["docker", "exec", container, "cat", "/tmp/oracle.log"],
                           capture_output=True, check=True)
        out.write_bytes(r.stdout)
        print(f"[nsfhq04-addfunc] wrote {out}")
        return out
    finally:
        O.stop_dbg_editor(container, state_dir)


if __name__ == "__main__":
    n = int(sys.argv[1])
    run(n)

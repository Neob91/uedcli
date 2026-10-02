#!/usr/bin/env python3
"""Live gdb trace of the EDITOR's FilterEdPoly (0x32bf0) LOOP HEAD (0x10032cb6, the same address
`editor_descent.py` validated live 2026-07 -- confirmed still correct against this tree's own
uned/UED22/Editor.dll by the sane, monotonic `editor-descent-33.log` trace it already produced),
scoped to Brush1852's `i_brush_poly=4` for the Area51 Entrance n=507 prefix (the SAME brush/poly
`area51_dist_threshold_probe.py` traces on the native side).

Unlike `editor_descent.py` (which conditions on EdPoly->iLink, a value `bspcsg.rs`'s own doc comments
call out as UNSTABLE across unrelated brushes within one rebuild -- `smuggler-4-surf-delta-traced-
to-4-pf-semisolid`, 2026-08-30), this scopes on EdPoly->Normal (offset +0xc) instead: the poly's own
face normal is INVARIANT across every split fragment of one original poly (splitting changes the
vertex ring, never the plane), so it is a reliable per-poly identity within one gdb run, and it is
the one correlator available on the editor side (EdPoly carries no actor/i_brush_poly bookkeeping --
that is native's own struct extension). The target normal, `(-0.707107, -0.707107, 0.0)`, comes
from the SAME field (`edpoly.normal`) `bspcsg.rs`'s DESCENT TRACE now also prints (added this round),
confirmed constant across all 47 of native's own descent lines for this poly.

Every printed line's `inode` is one stop in the actual node sequence FilterEdPoly visits for this
poly + all its split fragments. `inode` itself is NOT directly comparable to native's `node=` --
node insertion order/numbering can differ even where the underlying tree agrees (`area51_frag_diff.py`
already established "match by rounded Base/Normal, not index" for the same reason). `nodeN` (the
node's own classify plane, all 4 floats, offset +0..+0xc of the FBspNode/`FPlane`) is the
cross-side-comparable identity: pair each line by its `nodeN` against native's own per-step `N=`
(same offsets/quantity, just Base+Normal split instead of one packed plane) to see whether the two
sides visit the SAME SEQUENCE of planes before diverging.

Usage: area51_filteredpoly_descent.py [N=507] -> _scratch/area51-oracle-logs/area51-fep-descent-N.log
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

import editor_tree_oracle as O  # noqa: E402
from uedcli.driver import Driver, to_z_path  # noqa: E402
import area51_subset  # noqa: E402

OUT_DIR = ROOT / "_scratch/area51-oracle-logs"

# FilterEdPoly (0x32bf0) loop head -- every FilterLoop iteration (goto SP_Front/SP_Back included)
# falls through here.  Confirmed live-valid this round: reproduces `editor-descent-33.log`'s sane,
# monotonic node sequence against this same tree's dbg image.
LOOPHEAD_VA = 0x10032CB6

# Target EdPoly->Normal (offset +0xc,+0x10,+0x14) for Brush1852 i_brush_poly=4, from native's own
# `edpoly.normal` (constant across all 47 DESC lines this round).
TARGET_N = (-0.707107, -0.707107, 0.0)
TOL = 0.001

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
set $ed = *(unsigned int *)($ebp - 0x5ac)
set $model = *(unsigned int *)($ebp - 0x5b4)
set $inode = *(int *)($ebp - 0x5a4)
set $edX = *(float *)($ed + 0xc)
set $edY = *(float *)($ed + 0x10)
set $edZ = *(float *)($ed + 0x14)
if $edX > {nx0} && $edX < {nx1} && $edY > {ny0} && $edY < {ny1} && $edZ > {nz0} && $edZ < {nz1}
set $nodes = *(unsigned int *)($model + 0x58)
set $np = $nodes + $inode * 0x40
set $nf = *(unsigned char *)($np + 0x37)
set $nverts = *(unsigned char *)($np + 0x36)
printf "FEP inode=%d nf=%#x nnv=%d nodeN=%.5f,%.5f,%.5f,%.5f iF=%d iB=%d ednv=%d edN=%.6f,%.6f,%.6f out=%d\n", $inode, $nf, $nverts, *(float *)($np), *(float *)($np+4), *(float *)($np+8), *(float *)($np+0xc), *(int *)($np+0x24), *(int *)($np+0x20), *(int *)($ed + 0x1c0), $edX, $edY, $edZ, *(int *)($ebp - 0x5a0)
end
continue
end
printf "ORACLE_ATTACHED\n"
continue
"""


def _launch_gdb(container, pid):
    nx0, nx1 = TARGET_N[0] - TOL, TARGET_N[0] + TOL
    ny0, ny1 = TARGET_N[1] - TOL, TARGET_N[1] + TOL
    nz0, nz1 = TARGET_N[2] - TOL, TARGET_N[2] + TOL
    script = GDB.format(pid=pid, va=LOOPHEAD_VA, nx0=nx0, nx1=nx1, ny0=ny0, ny1=ny1, nz0=nz0, nz1=nz1)
    subprocess.run(["docker", "exec", "-i", container, "bash", "-c",
                    "cat > /tmp/fepdesc.gdb"], input=script, text=True, check=True)
    subprocess.run(["docker", "exec", "-d", container, "bash", "-c",
                    "exec gdb -batch -x /tmp/fepdesc.gdb > /tmp/fepdesc.log 2>&1"], check=True)


def _wait_attached(container, timeout=60.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        out = subprocess.run(["docker", "exec", container, "bash", "-c",
                              "grep -c ORACLE_ATTACHED /tmp/fepdesc.log 2>/dev/null || true"],
                             capture_output=True, text=True).stdout.strip()
        if out and out != "0":
            return
        time.sleep(0.5)
    diag = subprocess.run(["docker", "exec", container, "cat", "/tmp/fepdesc.log"],
                          capture_output=True, text=True).stdout
    raise RuntimeError(f"gdb did not attach within {timeout}s. gdb log:\n{diag[:2000]}")


def _log_line_count(container):
    out = subprocess.run(["docker", "exec", container, "bash", "-c",
                          "grep -c '^FEP ' /tmp/fepdesc.log 2>/dev/null || true"],
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
    print(f"[a51-fepdesc] golden N={n}: {golden}")

    project_dir = area51_subset.SUBSET_ROOT / f"trunk{n}"
    mounts = O._composed_mounts(project_dir)
    state_dir = O._state_dir(project_dir)
    container = f"uned-a51-fepdesc-n{n}"
    O.stop_dbg_editor(container, state_dir)
    print(f"[a51-fepdesc] starting {container} ...")
    O.start_dbg_editor(container, mounts, state_dir)
    try:
        drv = Driver(container=container)
        # `docker cp` fails in this sandbox whenever a `:ro` mount is present (rootless dockerd can't
        # remount `/stubs:ro`); `docker exec -i cat` bypasses it (area51_addfunc_oracle.py, 2026-09-01).
        golden_bytes = golden.read_bytes()
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /work/golden.dx"],
                       input=golden_bytes, check=True)
        print("[a51-fepdesc] MAP LOAD golden.dx ...")
        drv.exec(f"MAP LOAD FILE={to_z_path('/work/golden.dx')}")
        time.sleep(3.0)

        pid = O._editor_pid(container)
        print(f"[a51-fepdesc] attaching gdb to editor pid {pid} ...")
        _launch_gdb(container, pid)
        _wait_attached(container)
        print("[a51-fepdesc] gdb attached; issuing MAP REBUILD ...")
        drv.exec("MAP REBUILD")
        n_hits = _wait_quiescent(container, quiet_secs)
        print(f"[a51-fepdesc] rebuild quiescent: {n_hits} FEP lines logged")

        out = OUT_DIR / f"area51-fep-descent-{n}.log"
        r = subprocess.run(["docker", "exec", container, "cat", "/tmp/fepdesc.log"],
                           capture_output=True, check=True)
        out.write_bytes(r.stdout)
        print(f"[a51-fepdesc] wrote {out}")
        return out
    finally:
        O.stop_dbg_editor(container, state_dir)


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 507
    run(n)

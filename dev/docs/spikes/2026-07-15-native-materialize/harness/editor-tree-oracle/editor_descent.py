#!/usr/bin/env python3
"""Log the EDITOR's FilterEdPoly (0x32bf0) FULL descent path for one poly's iLink, at N brushes.

Reuses editor_tree_oracle's container machinery but breakpoints the FilterEdPoly LOOP HEAD
(0x10032cb6 — every FilterLoop iteration, `goto SP_Front/SP_Back` included, falls through here),
conditional on EdPoly->iLink==<target>.  Prints the node visited (index + plane + iF/iB + nv) and the
descending fragment's normal/nv/outside — i.e. the exact tree path the poly (and its split fragments)
takes, the ground truth for a per-poly emit-order divergence (§10.8).

Usage:  editor_descent.py [N=33] [ILINK=155]   -> logs/editor-descent-N.log
"""
import subprocess, sys, time
from pathlib import Path

ROOT = Path("/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedcli")
HARNESS = ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"
HERE = HARNESS / "editor-tree-oracle"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(HERE))

import editor_tree_oracle as O
from uedcli.driver import Driver, to_z_path
import subset_diff

N = int(sys.argv[1]) if len(sys.argv) > 1 else 33
ILINK = int(sys.argv[2]) if len(sys.argv) > 2 else 155
# Loop head of FilterEdPoly (0x32bf0): every FilterLoop iteration passes 0x10032cb6 (goto targets
# 0x32c50/0x32c56 fall through here). ebp set up. iNode=[ebp-0x5a4], EdPoly=[ebp-0x5ac],
# Model=[ebp-0x5b4]. Captures the FULL descent path (goto SP_Front/Back + recursion entries).
LOOPHEAD_VA = 0x10032CB6

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
break *{va:#x} if *(int *)(*(unsigned int *)($ebp - 0x5ac) + 0x1c4) == {ilink}
commands
silent
set $ed = *(unsigned int *)($ebp - 0x5ac)
set $model = *(unsigned int *)($ebp - 0x5b4)
set $inode = *(int *)($ebp - 0x5a4)
set $nodes = *(unsigned int *)($model + 0x58)
set $np = $nodes + $inode * 0x40
set $nf = *(unsigned char *)($np + 0x37)
set $nverts = *(unsigned char *)($np + 0x36)
printf "FEP inode=%d nf=%#x nnv=%d nodeN=%.5f,%.5f,%.5f,%.5f iF=%d iB=%d ednv=%d edN=%.5f,%.5f,%.5f out=%d\n", $inode, $nf, $nverts, *(float *)($np), *(float *)($np+4), *(float *)($np+8), *(float *)($np+0xc), *(int *)($np+0x24), *(int *)($np+0x20), *(int *)($ed + 0x1c0), *(float *)($ed + 0xc), *(float *)($ed + 0x10), *(float *)($ed + 0x14), *(int *)($ebp - 0x5a0)
continue
end
printf "ORACLE_ATTACHED\n"
continue
"""


def main():
    O._ensure_dbg_image()
    golden = subset_diff.build_editor_subset(N)
    mounts = O._composed_mounts(subset_diff.CASTLE_PROJECT)
    state_dir = O._state_dir(subset_diff.CASTLE_PROJECT)
    container = f"uned-descent-n{N}"
    O.stop_dbg_editor(container, state_dir)
    print(f"starting {container} ...")
    O.start_dbg_editor(container, mounts, state_dir)
    try:
        drv = Driver(container=container)
        subprocess.run(["docker", "cp", str(golden), f"{container}:/work/golden.dx"], check=True)
        drv.exec(f"MAP LOAD FILE={to_z_path('/work/golden.dx')}")
        time.sleep(3.0)
        pid = O._editor_pid(container)
        script = GDB.format(pid=pid, va=LOOPHEAD_VA, ilink=ILINK)
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /tmp/desc.gdb"],
                       input=script, text=True, check=True)
        subprocess.run(["docker", "exec", "-d", container, "bash", "-c",
                        "exec gdb -batch -x /tmp/desc.gdb > /tmp/desc.log 2>&1"], check=True)
        # wait attached
        for _ in range(120):
            out = subprocess.run(["docker", "exec", container, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/desc.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if out and out != "0":
                break
            time.sleep(0.5)
        print("attached; MAP REBUILD ...")
        drv.exec("MAP REBUILD")
        # wait quiescence on FEP lines
        last = -1; stable = 0
        for _ in range(600):
            n = subprocess.run(["docker", "exec", container, "bash", "-c",
                                "grep -c '^FEP ' /tmp/desc.log 2>/dev/null || true"],
                               capture_output=True, text=True).stdout.strip()
            n = int(n) if n.isdigit() else 0
            if n == last and n > 0:
                stable += 1
                if stable >= 6:
                    break
            else:
                stable = 0
            last = n
            time.sleep(1.0)
        out = HERE / "logs" / f"editor-descent-{N}.log"
        subprocess.run(["docker", "cp", f"{container}:/tmp/desc.log", str(out)], check=True)
        print(f"wrote {out} ({last} FEP lines)")
    finally:
        O.stop_dbg_editor(container, state_dir)


if __name__ == "__main__":
    main()

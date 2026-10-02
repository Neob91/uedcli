#!/usr/bin/env python3
"""§92 §52 — the DECISIVE rebuild capture, via the PROVEN oracle path (`editor_tree_oracle.run`).

The oracle (MAP LOAD golden105 + MAP REBUILD, break bspAddNode 0x10034e80, UNCONDITIONAL single
printf) works reliably (5878 calls, no crash).  My per-call dome-position filter block (float reads +
if + while on every hit) CRASHED the rebuild 3x.  So we keep the oracle's UNCONDITIONAL pattern and
only ENRICH the printf: full-bit hex Normal + all polygon Verts.  Filter to Brush755's dome facets
OFFLINE (by non-axis normal).  Monkeypatches O._GDB_SCRIPT, then calls O.run — 100% proven path.

Writes _scratch/normfin/rebuild_full/oracle-105.log.
"""
import sys
from pathlib import Path

ROOT = Path("/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedcli")
HARNESS = ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"
HERE = HARNESS / "editor-tree-oracle"
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(HARNESS)); sys.path.insert(0, str(HERE))
import editor_tree_oracle as O  # noqa: E402

ENRICHED = r"""
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
set $e = *(unsigned int *)($esp + 0x14)
set $nv = *(int *)($e + 0x1c0)
if $nv < 0
  set $nv = 0
end
if $nv > 24
  set $nv = 24
end
printf "ADD ret=%#x nv=%d N=%#010x,%#010x,%#010x B=%#010x,%#010x,%#010x", *(unsigned int *)($esp), $nv, *(unsigned int *)($e + 0xc), *(unsigned int *)($e + 0x10), *(unsigned int *)($e + 0x14), *(unsigned int *)($e), *(unsigned int *)($e + 4), *(unsigned int *)($e + 8)
set $j = 0
while $j < $nv
  set $v = $e + 0x30 + $j * 0xc
  printf " V=%#010x,%#010x,%#010x", *(unsigned int *)($v), *(unsigned int *)($v + 4), *(unsigned int *)($v + 8)
  set $j = $j + 1
end
printf "\n"
continue
end
printf "ORACLE_ATTACHED\n"
continue
"""


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 105
    O._GDB_SCRIPT = ENRICHED
    out = O.run(n, quiet_secs=8.0, out_dir=ROOT / "_scratch/normfin/rebuild_full", target_name="unatco")
    print(f"DONE: {out}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""§92 §52 — capture CalcNormal INPUT verts + OUTPUT normal DURING MAP REBUILD, via the PROVEN oracle
path, with UNCONDITIONAL breakpoints (the per-call position FILTER crashed the rebuild 3x; the
oracle's unconditional pattern is stable).

Breakpoints (all unconditional — no per-call float filter):
  * bspAddNode 0x10034e80 -> "ADD" (drives O.run's quiescence; also the stored-normal reference).
  * CalcNormal entry (Engine 0x150510, ecx=this always valid) -> "CN this nv V=..." (nv<24 only, an
    integer guard, not a memory-read filter).
  * CalcNormal tail  (0x150620, edi=this) -> "NR this N=..." (the normalized output).

Match CN->NR by `this`, filter to Brush755 dome facets offline (verts in dome box).  This gives the
EXACT verts the editor's rebuild CalcNormal consumed to produce the twin normal.

Writes _scratch/normfin/rebuild_cn/oracle-105.log.
"""
import sys
from pathlib import Path

ROOT = Path("/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedctl")
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
set $fin = *(unsigned int *)0x100cee9c
set $engbase = $fin - 0x150ac0
break *{va:#x}
commands
silent
printf "ADD .\n"
continue
end
break *($engbase + 0x150510)
commands
silent
set $t = $ecx
set $nv = *(int *)($t + 0x1c0)
if $nv >= 3 && $nv < 24
  printf "CN this=%#x nv=%d", $t, $nv
  set $j = 0
  while $j < $nv
    set $v = $t + 0x30 + $j * 0xc
    printf " V=%#010x,%#010x,%#010x", *(unsigned int *)($v), *(unsigned int *)($v + 4), *(unsigned int *)($v + 8)
    set $j = $j + 1
  end
  printf "\n"
end
continue
end
break *($engbase + 0x150620)
commands
silent
printf "NR this=%#x N=%#010x,%#010x,%#010x\n", $edi, *(unsigned int *)($edi + 0xc), *(unsigned int *)($edi + 0x10), *(unsigned int *)($edi + 0x14)
continue
end
printf "ORACLE_ATTACHED\n"
continue
"""


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 105
    O._GDB_SCRIPT = ENRICHED
    out = O.run(n, quiet_secs=10.0, out_dir=ROOT / "_scratch/normfin/rebuild_cn", target_name="unatco")
    print(f"DONE: {out}")


if __name__ == "__main__":
    main()

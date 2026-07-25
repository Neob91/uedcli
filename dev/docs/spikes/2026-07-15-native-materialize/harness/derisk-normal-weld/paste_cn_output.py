#!/usr/bin/env python3
"""Break INSIDE Engine.dll FPoly::CalcNormal (RVA 0x150510) during Brush755 paste and dump the ACTUAL
Vertex[] + NumVertices CalcNormal reads (edi/ecx=this) AND the Normal it writes (at the tail 0x150643).
Engine.dll runtime base is derived from Editor IAT slot 0x100cee9c (= Finalize @ eng_base+0x150ac0),
so CalcNormal = *(0x100cee9c) - 0x150ac0 + 0x150510, tail = *(0x100cee9c) - 0x150ac0 + 0x150643.
Two breakpoints share the pass. Writes _scratch/normfin/paste_cn_output.log."""
import subprocess, sys, time
from pathlib import Path
ROOT = Path("/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedctl")
HARNESS = ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"
HERE = HARNESS / "editor-tree-oracle"
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(HARNESS)); sys.path.insert(0, str(HERE))
import editor_tree_oracle as O
import unatco_subset as U
from uedctl import trunk, config
from uedctl.driver import Driver
from uedctl.materialize import levelinfo_first_order, _short_class
from uedctl.writes import _re_add
from uedctl.packages import editor_search_dirs, ensure_load
from uedctl.container_assets import resource_mounts
from uedctl.apply import _level_referenced_packages

BRUSH = sys.argv[1] if len(sys.argv) > 1 else "Brush755"
OUT = ROOT / "_scratch/normfin/paste_cn_output.log"

# CalcNormal entry: ecx=this. Vertex[i]=+0x30+i*12, NumVertices=+0x1c0, Normal=+0xc.
# Tail 0x150643: edi=this, Normal computed.
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
set $fin = *(unsigned int *)0x100cee9c
set $cn = $fin - 0x150ac0 + 0x150510
set $tail = $fin - 0x150ac0 + 0x150620
break *$cn
commands
silent
set $t = $ecx
set $nv = *(int *)($t + 0x1c0)
if $nv < 0
  set $nv = 0
end
if $nv > 24
  set $nv = 24
end
printf "CN this=%#x nv=%d", $t, $nv
set $j = 0
while $j < $nv
  set $v = $t + 0x30 + $j * 0xc
  printf " V=%#010x,%#010x,%#010x", *(unsigned int *)($v), *(unsigned int *)($v + 4), *(unsigned int *)($v + 8)
  set $j = $j + 1
end
printf "\n"
continue
end
break *$tail
commands
silent
printf "NR this=%#x N=%#010x,%#010x,%#010x\n", $edi, *(unsigned int *)($edi + 0xc), *(unsigned int *)($edi + 0x10), *(unsigned int *)($edi + 0x14)
continue
end
printf "ORACLE_ATTACHED\n"
continue
"""


def main():
    O._ensure_dbg_image()
    lvl, _ = trunk.read_level(U.FULL_TRUNK)
    keep = [n for n in lvl.order if _short_class(lvl.actors[n].cls) in ("Brush", "LevelInfo")]
    keep = [n for n in keep if _short_class(lvl.actors[n].cls) == "LevelInfo" or n == BRUSH]
    classes = {n: lvl.actors[n].cls for n in keep}
    has_brush = {n: lvl.actors[n].brush is not None for n in keep}
    imp = levelinfo_first_order(keep, classes, has_brush)
    actors = [lvl.actors[n] for n in imp]
    project = O.resolve_target("unatco").project_dir
    proj = config.load_project(str(project)); uc = config.load_user_config()
    sdirs = config.composed_search_dirs(proj, uc)
    mounts = resource_mounts(sdirs); state_dir = O._state_dir(project)
    container = "uned-cn-out"
    O.stop_dbg_editor(container, state_dir)
    print(f"starting {container} ...", flush=True)
    O.start_dbg_editor(container, mounts, state_dir)
    try:
        drv = Driver(container=container)
        ref = _level_referenced_packages(type("L", (), {"actors": {n: lvl.actors[n] for n in imp}})())
        try:
            ensure_load(drv, ref, search_dirs=editor_search_dirs(sdirs), mounts=mounts)
        except Exception as exc:
            print(f"WARN ensure_load: {exc}", flush=True)
        drv.map_new(); time.sleep(2.0)
        pid = O._editor_pid(container)
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /tmp/cn.gdb"],
                       input=GDB.format(pid=pid), text=True, check=True)
        subprocess.run(["docker", "exec", "-d", container, "bash", "-c",
                        "exec gdb -batch -x /tmp/cn.gdb > /tmp/cno.log 2>&1"], check=True)
        for _ in range(240):
            out = subprocess.run(["docker", "exec", container, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/cno.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if out and out != "0":
                break
            time.sleep(0.5)
        else:
            diag = subprocess.run(["docker", "exec", container, "cat", "/tmp/cno.log"],
                                  capture_output=True, text=True).stdout
            raise RuntimeError(f"attach failed:\n{diag[:2000]}")
        print("attached; EDIT PASTE ...", flush=True)
        _re_add(drv, actors)
        last, lc = -1, time.monotonic(); dl = time.monotonic() + 240.0
        while time.monotonic() < dl:
            n = int(subprocess.run(["docker", "exec", container, "bash", "-c",
                                    "grep -c '^CN ' /tmp/cno.log 2>/dev/null || true"],
                                   capture_output=True, text=True).stdout.strip() or "0")
            now = time.monotonic()
            if n != last:
                last, lc = n, now
            elif n > 0 and (now - lc) >= 6.0:
                break
            time.sleep(1.0)
        subprocess.run(["docker", "cp", f"{container}:/tmp/cno.log", str(OUT)], check=True)
        nd = subprocess.run(["bash", "-c", f"grep -c '^CN ' {OUT}"], capture_output=True, text=True).stdout.strip()
        print(f"wrote {OUT} ({nd} CN lines)", flush=True)
    finally:
        O.stop_dbg_editor(container, state_dir)


if __name__ == "__main__":
    main()

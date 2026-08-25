#!/usr/bin/env python3
r"""Live single-call trace of `FPoly::TryToMerge` (Editor.dll 0x34b10) for the small set of
`iLink`s whose post-merge fragment count/shape diverges from native's (see
`findbestsplit-divergence-forensic-dive-17-real`). Breaks at TryToMerge's two exit points --
the FAIL path (`xor eax,eax` at 0x34b73) and the SUCCESS path (`mov eax,1` at 0x34e1d) -- filtered
to calls where Poly1 (`[ebp+8]`) carries a wanted `iLink`, logging Poly1/Poly2 base pointer + iLink +
NumVertices + outcome. This directly observes what the real merge fixpoint does call-by-call, instead
of inferring it from before/after soup snapshots.

Usage:  trytomerge_live_unatco.py [golden.dx]   ->  logs/trytomerge-live-unatco.log
"""
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[6]
HARNESS = ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"
HERE = HARNESS / "editor-tree-oracle"
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(HARNESS)); sys.path.insert(0, str(HERE))
import editor_tree_oracle as O
from uedcli import config
from uedcli.container_assets import resource_mounts
from uedcli.driver import Driver, to_z_path

GOLDEN = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/UEDGolden_unatco_full.dx")
PROJECT_DIR = ROOT / "_scratch/oracle-project"

WANT_ILINKS = {300, 878, 888, 889, 896, 977, 1144, 1163}
WANT_STR = "||".join(f"*(int *)($p1 + 0x1c4) == {v}" for v in WANT_ILINKS)

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

break *0x10034b73
commands
silent
set $p1 = *(unsigned int *)($ebp + 8)
set $p2 = *(unsigned int *)($ebp + 0xc)
if ({want})
  printf "TTM FAIL p1=%#x p2=%#x ilink=%d nv1=%d nv2=%d\n", $p1, $p2, *(int *)($p1 + 0x1c4), *(int *)($p1 + 0x1c0), *(int *)($p2 + 0x1c0)
end
continue
end

break *0x10034bf1
commands
silent
set $p1 = *(unsigned int *)($ebp + 8)
set $p2 = *(unsigned int *)($ebp + 0xc)
if ({want})
  printf "TTM FOUND p1=%#x p2=%#x ilink=%d start1(edi)=%d start2(esi)=%d\n", $p1, $p2, *(int *)($p1 + 0x1c4), $edi, $esi
end
continue
end

break *0x10034ddc
commands
silent
set $p1 = *(unsigned int *)($ebp + 8)
set $p2 = *(unsigned int *)($ebp + 0xc)
if ({want})
  printf "TTM RING p1=%#x p2=%#x ilink=%d ringcount=%d\n", $p1, $p2, *(int *)($p1 + 0x1c4), *(int *)($ebp - 0x2c)
end
continue
end

break *0x10034dea
commands
silent
set $p1 = *(unsigned int *)($ebp + 8)
set $p2 = *(unsigned int *)($ebp + 0xc)
if ({want})
  printf "TTM AFTERRC p1=%#x p2=%#x ilink=%d rc_eax=%d ringcount=%d\n", $p1, $p2, *(int *)($p1 + 0x1c4), $eax, *(int *)($ebp - 0x2c)
end
continue
end

break *0x10034e1d
commands
silent
set $p1 = *(unsigned int *)($ebp + 8)
set $p2 = *(unsigned int *)($ebp + 0xc)
if ({want})
  printf "TTM OK   p1=%#x p2=%#x ilink=%d nv1=%d nv2=%d newnv=%d\n", $p1, $p2, *(int *)($p1 + 0x1c4), *(int *)($p1 + 0x1c0), *(int *)($p2 + 0x1c0), *(int *)($ebp - 0x2c)
end
continue
end

break *0x1004a041
commands
silent
printf "REPART_ENTRY\n"
continue
end

printf "ORACLE_ATTACHED\n"
continue
""".replace("{want}", WANT_STR)


def main():
    if not PROJECT_DIR.exists():
        PROJECT_DIR.mkdir(parents=True, exist_ok=True)
        (PROJECT_DIR / "uedcli.toml").write_text('game = "deusex"\n')

    O._ensure_dbg_image()
    project = config.load_project(str(PROJECT_DIR))
    user_config = config.load_user_config()
    search_dirs = config.composed_search_dirs(project, user_config)
    mounts = resource_mounts(search_dirs)
    state_dir = config.state_dir(project.root, create=True)

    container = "uned-ttmlive-unatco"
    O.stop_dbg_editor(container, state_dir)
    print(f"starting {container} (golden={GOLDEN}) ...", flush=True)
    O.start_dbg_editor(container, mounts, state_dir)
    try:
        drv = Driver(container=container)
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /work/golden.dx"],
                       input=GOLDEN.read_bytes(), check=True)
        drv.exec(f"MAP LOAD FILE={to_z_path('/work/golden.dx')}")
        time.sleep(3.0)
        pid = O._editor_pid(container)
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /tmp/ttm.gdb"],
                       input=GDB.format(pid=pid), text=True, check=True)
        subprocess.run(["docker", "exec", "-d", container, "bash", "-c",
                        "exec gdb -batch -x /tmp/ttm.gdb > /tmp/ttm.log 2>&1"], check=True)
        for _ in range(120):
            out = subprocess.run(["docker", "exec", container, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/ttm.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if out and out != "0":
                break
            time.sleep(0.5)
        print("attached; MAP REBUILD ...", flush=True)
        drv.exec("MAP REBUILD")
        for _ in range(1500):
            done = subprocess.run(["docker", "exec", container, "bash", "-c",
                                   "grep -c REPART_ENTRY /tmp/ttm.log 2>/dev/null || true"],
                                  capture_output=True, text=True).stdout.strip()
            if done and done != "0":
                break
            time.sleep(1.0)
        time.sleep(2.0)  # let the breakpoint's own commands flush before detaching
        out = HERE / "logs" / "trytomerge-live-unatco.log"
        out.parent.mkdir(parents=True, exist_ok=True)
        data = subprocess.run(["docker", "exec", container, "cat", "/tmp/ttm.log"],
                              capture_output=True).stdout
        out.write_bytes(data)
        print(f"wrote {out}", flush=True)
        nd = subprocess.run(["bash", "-c", f"grep -c '^TTM ' {out}"],
                            capture_output=True, text=True).stdout.strip()
        print(f"{nd} TTM lines")
    finally:
        O.stop_dbg_editor(container, state_dir)


if __name__ == "__main__":
    main()

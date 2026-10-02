#!/usr/bin/env python3
r"""EDITOR repartition-soup dump for ANY golden .dx — `Model->Polys->Element` at `bspBuild` entry.

Generalizes `editor_polys_oracle.py` (hardcoded to a developer path + the castle/N-subset targets)
to a golden path given on the command line, and emits the SAME line format native's
`UEDCLI_BSPCSG_SOUP_ORDER` hook writes, so `polys_order_diff.py` can diff the two sequences directly.

Breakpoint `0x1004a041` is the `bspBuild` call site INSIDE `bspRepartition`, so the first hit is the
world repartition (the per-brush temp-BSP `bspBuild`s live at other call sites).

`SOUPBEGIN num=` is `Model->Polys->Element.Num`, i.e. every element. `bspBuild` then filters
`NumVertices==0` out before `SplitPolyList` sees the list (`editor_polys_oracle.py`'s decode), so the
input `FindBestSplit` actually strides over is the `nv>0` subset in the same order — count the POLY
lines with `nv>0`, not `num`, when comparing against native's soup size.

Usage: ed_soup.py <golden.dx> <out.log>
"""
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[6]
HARNESS = ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"
HERE = HARNESS / "editor-tree-oracle"
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(HARNESS)); sys.path.insert(0, str(HERE))
import editor_tree_oracle as O                                   # noqa: E402
from uedcli import config                                        # noqa: E402
from uedcli.container_assets import resource_mounts              # noqa: E402
from uedcli.driver import Driver, to_z_path                      # noqa: E402

GOLDEN = Path(sys.argv[1])
OUT = Path(sys.argv[2])
PROJECT_DIR = ROOT / "_scratch/oracle-project"
DEADLINE = 1200.0          # rules/background-work.md's ~20-minute hang detector
ATTACH_TIMEOUT = 120.0

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
break *0x1004a041
commands
silent
set $m = *(unsigned int *)($esp)
set $up = *(unsigned int *)($m + 0x54)
set $el = *(unsigned int *)($up + 0x28)
set $num = *(int *)($up + 0x2c)
printf "SOUPBEGIN num=%d\n", $num
set $i = 0
while $i < $num
  set $p = $el + $i * 0x1d8
  set $nv = *(int *)($p + 0x1c0)
  printf "POLY %d nv=%d ilink=%d N=%.5f,%.5f,%.5f B=%.5f,%.5f,%.5f\n", $i, $nv, *(int *)($p + 0x1c4), *(float *)($p + 0xc), *(float *)($p + 0x10), *(float *)($p + 0x14), *(float *)($p), *(float *)($p + 4), *(float *)($p + 8)
  set $k = 0
  while $k < $nv
    set $v = $p + 0x30 + $k * 12
    printf "VERT %.5f,%.5f,%.5f\n", *(float *)($v), *(float *)($v + 4), *(float *)($v + 8)
    set $k = $k + 1
  end
  set $i = $i + 1
end
printf "SOUPEND\n"
detach
quit
end
printf "ORACLE_ATTACHED\n"
continue
"""


def _grep(container, needle, log="/tmp/soup.log"):
    return subprocess.run(["docker", "exec", container, "bash", "-c",
                           f"grep -c {needle} {log} 2>/dev/null || true"],
                          capture_output=True, text=True).stdout.strip()


def main():
    if not PROJECT_DIR.exists():
        PROJECT_DIR.mkdir(parents=True, exist_ok=True)
        (PROJECT_DIR / "uedcli.toml").write_text('game = "deusex"\n')

    O._ensure_dbg_image()
    project = config.load_project(str(PROJECT_DIR))
    mounts = resource_mounts(config.composed_search_dirs(project, config.load_user_config()))
    state_dir = config.state_dir(project.root, create=True)

    container = "uned-soupdump"
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
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /tmp/soup.gdb"],
                       input=GDB.format(pid=pid), text=True, check=True)
        subprocess.run(["docker", "exec", "-d", container, "bash", "-c",
                        "exec gdb -batch -x /tmp/soup.gdb > /tmp/soup.log 2>&1"], check=True)
        # Driving `MAP REBUILD` before gdb is attached silently produces an EMPTY log — the whole run
        # then looks like "the editor wedged" when it actually finished unobserved.  So a failed
        # attach is an error, not a warning.
        attach_deadline = time.monotonic() + ATTACH_TIMEOUT
        while _grep(container, "ORACLE_ATTACHED") in ("", "0"):
            if time.monotonic() > attach_deadline:
                print(f"gdb never attached within {ATTACH_TIMEOUT:.0f}s "
                      f"(container {container}) — nothing captured", file=sys.stderr)
                return 1
            time.sleep(0.5)
        print("attached; MAP REBUILD ...", flush=True)
        drv.exec("MAP REBUILD")
        deadline = time.monotonic() + DEADLINE
        while _grep(container, "SOUPEND") in ("", "0"):
            if time.monotonic() > deadline:
                # A partial dump is a silent half-answer: `polys_order_diff.py` would read the
                # truncated tail as a real soup difference.  Name it and fail.
                OUT.parent.mkdir(parents=True, exist_ok=True)
                OUT.write_bytes(subprocess.run(
                    ["docker", "exec", container, "cat", "/tmp/soup.log"],
                    capture_output=True).stdout)
                print(f"no SOUPEND within {DEADLINE:.0f}s — {OUT} is PARTIAL, do not diff it",
                      file=sys.stderr)
                return 1
            time.sleep(2.0)
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_bytes(subprocess.run(["docker", "exec", container, "cat", "/tmp/soup.log"],
                                       capture_output=True).stdout)
        print(f"wrote {OUT}", flush=True)
        for line in OUT.read_text(errors="replace").splitlines():
            if line.startswith("SOUPBEGIN"):
                print("  " + line)
    finally:
        O.stop_dbg_editor(container, state_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())

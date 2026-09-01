#!/usr/bin/env python3
r"""Live GDB capture: the real editor's `Model.Points` array CONTENT (not just `.Num`), before and
after EVERY `bspRefresh` call, across a full `MAP REBUILD` of `DX.dx`'s trunk.

WHY. `DX.dx`'s 13/26 `p_base` surf diffs (`texture-ref-i-actor-divergence-traced-to-golden`,
`native-materialize-findings.md` "`DX.dx`'s `p_base` reordering") are a pure Points-array REORDER
with zero count delta. Offline analysis this round (no editor) pinned the minimal repro to `Brush3`
(a plain 6-face `CSG_Subtract` unit cube, `i_actor=2`, surfs 0-5): golden's leading 5-point "base"
block order is `[A,E,H,G,F]` (real Points[0..4]) where A/E/G/F/H are the brush's 5 distinct authored
polygon Origins in AUTHORED-polygon order [poly0=A, poly1=E, poly2=E(dup), poly3=G, poly4=F,
poly5=H] -- i.e. "first-appearance in authored/final-surf order" predicts `[A,E,G,F,H]` (which is
EXACTLY what native's `reorder_points_canonical` already produces and IS the 13-diff residual), but
golden's real order is `[A,E,H,G,F]` -- G and F swapped, H moved two slots earlier. This is a genuine
non-monotonic reordering relative to every final-model-visible order (surf order, node order, ring
order) tried offline -- consistent with the standing §10.20 hypothesis ("a `bspRefresh`
reachability-DFS-compaction artifact of the PRE-compaction pool indices, not reconstructable from the
final model") but never live-verified for this exact case.

MECHANISM. `bspRefresh` (Editor.dll VA `0x10036cd0`) is called once at world-level and once per
`bspRepartition` subtree (up to ~209/119 times on larger levels; DX.dx has far fewer). Its own
disassembly (`native-materialize-findings.md` "Round 3") shows it physically compacts `Points`/
`Vectors` in place via a reachability-marked remap+copy, confirmed at `0x10036fb0`-`0x10037166`. This
script does NOT try to read the remap table directly (its exact instruction-level address was never
pinned) -- instead it dumps the FULL `Model.Points` array (`Model+0x88` Data, `Model+0x8c` Num,
stride 0xc = 3×f32) as raw float triples at `bspRefresh` ENTRY (`0x10036cd0`) and at its confirmed
single epilogue (`0x1003718f`, `ret 8` -- verified by fresh capstone disassembly this round: the
OTHER `ret` in the same 0x600-byte window, at `0x10037251`, belongs to a DIFFERENT function whose
prologue starts right after `0x1003718f`) for EVERY call. Diffing each call's before/after arrays by
VALUE (not index) reconstructs each surviving point's pre-compaction pool index empirically, without
needing the remap table's own address.

Usage:  points_pool_refresh_trace.py [golden.dx]
  -> logs/points-pool-refresh-trace.log
"""
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
OLD_HARNESS = ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"
OLD_ORACLE = OLD_HARNESS / "editor-tree-oracle"
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(OLD_HARNESS))
sys.path.insert(0, str(OLD_ORACLE))
import editor_tree_oracle as O  # noqa: E402
from uedcli import config  # noqa: E402
from uedcli.container_assets import resource_mounts  # noqa: E402
from uedcli.driver import Driver, to_z_path  # noqa: E402

GOLDEN = Path(sys.argv[1]) if len(sys.argv) > 1 else (
    ROOT / "_scratch/dx-pbase-points-trace/golden_dx.dx")
PROJECT_DIR = ROOT / "_scratch/oracle-project"
POLL, QUIET_FOR, DEADLINE = 1.0, 15.0, 900.0

# bspRefresh entry (Editor.dll VA) -- established across many prior rounds (e.g. node-flags-live-
# verify's fresh disassembly, native-materialize-findings.md "Round 3"). Exit VA (0x1003718f, the
# `ret 8` epilogue) freshly disassembled THIS round (capstone, 0x600-byte window from entry) -- the
# other `ret` found in that window (0x10037251) belongs to the next function (a new SEH prologue
# starts immediately after 0x1003718f), not a second bspRefresh exit path.
BSPREFRESH_ENTRY = 0x10036cd0
BSPREFRESH_EXIT = 0x1003718f

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
set $callidx = 0
break *0x10036cd0
commands
silent
set $callidx = $callidx + 1
set $m = *(unsigned int *)($esp + 4)
set $pnum = *(int *)($m + 0x8c)
set $pdata = *(unsigned int *)($m + 0x88)
set $nnum = *(int *)($m + 0x5c)
printf "ENTRY callidx=%d model=%#x nodes_num=%d points_num=%d points_data=%#x\n", $callidx, $m, $nnum, $pnum, $pdata
printf "POINTS_BEFORE callidx=%d n=%d vals=", $callidx, $pnum
set $k = 0
while $k < $pnum
  set $px = *(float *)($pdata + $k*12)
  set $py = *(float *)($pdata + $k*12 + 4)
  set $pz = *(float *)($pdata + $k*12 + 8)
  printf "%.6f,%.6f,%.6f;", $px, $py, $pz
  set $k = $k + 1
end
printf "\n"
continue
end
break *0x1003718f
commands
silent
set $pnum2 = *(int *)($m + 0x8c)
set $pdata2 = *(unsigned int *)($m + 0x88)
set $nnum2 = *(int *)($m + 0x5c)
printf "EXIT callidx=%d model=%#x nodes_num=%d points_num=%d points_data=%#x\n", $callidx, $m, $nnum2, $pnum2, $pdata2
printf "POINTS_AFTER callidx=%d n=%d vals=", $callidx, $pnum2
set $k2 = 0
while $k2 < $pnum2
  set $px2 = *(float *)($pdata2 + $k2*12)
  set $py2 = *(float *)($pdata2 + $k2*12 + 4)
  set $pz2 = *(float *)($pdata2 + $k2*12 + 8)
  printf "%.6f,%.6f,%.6f;", $px2, $py2, $pz2
  set $k2 = $k2 + 1
end
printf "\n"
continue
end
printf "ORACLE_ATTACHED\n"
continue
"""


def main() -> int:
    if not PROJECT_DIR.exists():
        PROJECT_DIR.mkdir(parents=True, exist_ok=True)
        (PROJECT_DIR / "uedcli.toml").write_text('game = "deusex"\n')

    O._ensure_dbg_image()
    project = config.load_project(str(PROJECT_DIR))
    user_config = config.load_user_config()
    mounts = resource_mounts(config.composed_search_dirs(project, user_config))
    state_dir = config.state_dir(project.root, create=True)

    container = "uned-dxpoints-refresh"
    O.stop_dbg_editor(container, state_dir)
    print(f"[dxpoints] golden={GOLDEN}", flush=True)
    print(f"[dxpoints] starting {container} ...", flush=True)
    O.start_dbg_editor(container, mounts, state_dir)
    try:
        drv = Driver(container=container)
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /work/golden.dx"],
                       input=GOLDEN.read_bytes(), check=True)
        drv.exec(f"MAP LOAD FILE={to_z_path('/work/golden.dx')}")
        time.sleep(3.0)
        pid = O._editor_pid(container)
        print(f"[dxpoints] editor pid {pid}; attaching gdb ...", flush=True)
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /tmp/dxp.gdb"],
                       input=GDB.format(pid=pid), text=True, check=True)
        subprocess.run(["docker", "exec", "-d", container, "bash", "-c",
                        "exec gdb -batch -x /tmp/dxp.gdb > /tmp/dxp.log 2>&1"], check=True)
        for _ in range(120):
            out = subprocess.run(["docker", "exec", container, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/dxp.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if out and out != "0":
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("gdb did not attach")
        print("[dxpoints] attached; MAP REBUILD ...", flush=True)
        drv.exec("MAP REBUILD")
        prev, quiet, deadline = -1, 0.0, time.monotonic() + DEADLINE
        while quiet < QUIET_FOR:
            if time.monotonic() > deadline:
                print(f"[dxpoints] WARNING: gave up after {DEADLINE:.0f}s, {max(prev,0)} lines seen",
                      flush=True)
                break
            n = subprocess.run(["docker", "exec", container, "bash", "-c",
                                "wc -l < /tmp/dxp.log 2>/dev/null || true"],
                               capture_output=True, text=True).stdout.strip()
            n = int(n or 0)
            quiet = quiet + POLL if (n == prev and n > 0) else 0.0
            prev = n
            time.sleep(POLL)
        out = HERE.parent / "logs" / "points-pool-refresh-trace.log"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(subprocess.run(["docker", "exec", container, "cat", "/tmp/dxp.log"],
                                       capture_output=True).stdout)
        print(f"[dxpoints] wrote {out} ({prev} lines seen)", flush=True)
        text = out.read_text(errors="replace")
        print(f"[dxpoints] ENTRY count = {text.count('ENTRY ')}, EXIT count = {text.count('EXIT ')}",
              flush=True)
    finally:
        O.stop_dbg_editor(container, state_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

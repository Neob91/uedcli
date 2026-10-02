#!/usr/bin/env python3
r"""Live GDB capture: the real editor's Points/Verts/Nodes pool sizes across `bspOptGeom`'s own body,
on the ACTUAL UNATCO/Wanchai goldens (never `Test_Castle` -- see `feedback-test-against-unatco-not-
castle` / this repo's own owner ruling).

WHY. Round 4 of the Points-residual investigation (native +16 over golden on BOTH UNATCO and Wanchai,
post `repartition_frontier` fix): `native-materialize-findings.md` records that native's own final
compaction (`reorder_points_canonical`, `bspcsg.rs`) drops only 52 points on each level, and that the
`STAGE post-optgeom` checkpoint (`UEDCLI_BSPCSG_STAGE_COUNTS`) was never matched against a live editor
reading at the SAME point ("(not separately captured)" in the ledger's stage table) -- the coordinator
named this exact gap as the untried lever: does the real editor's own post-weld pass drop MORE points
than native's 52, i.e. is `reorder_points_canonical` too conservative?

This session's OWN `bspoptgeom.rs::merge_near_points` doc comment cites a `ShrinkModel`-style dedup
call (`Editor.dll 0x33dc0`, radius 0.25) at the START of `bspOptGeom`, and asserts "The Points array is
left intact; only vertex references collapse" -- i.e. native's port does NOT physically remove merged
points from the pool, only remaps `vert.iVertex`. That claim traces to the pre-2026-08-14 spike
(`sections/10-bsp-csg-build.md` family) and has never been independently re-verified live, on UNATCO or
Wanchai, post the owner's 2026-08-28 invalidation ruling.

Fresh disassembly this session (not copied from any prior doc) of `Editor.dll 0x10036870`-`0x10036c32`
(`bspOptGeom`'s own body, RVA independently re-confirmed via `vtable_dump.py`'s live `slot218=0x10036870`
capture on UNATCO, 2026-08-30) shows, in order:
  1. `0x100368e5: call 0x10033dc0` with args `(Model=esi, radius=0.25)` -- confirms the ShrinkModel-style
     call identity+signature the doc cites, independently re-derived.
  2. `0x100368f4: call [eax+0x200]` (a VIRTUAL call through `edi`'s own vtable, `edi` = bspOptGeom's
     "this" = likely `UEditorEngine`, NOT the Model -- so despite the `+0x200` offset matching UModel's
     own `bspRefresh` slot elsewhere in this investigation, this is a DIFFERENT class's vtable and must
     NOT be assumed to be the same function without live verification) with args `(Model=esi, 0)`.
  3. The T-junction weld (pass 1) and side-link pass (pass 2) run after, ending in a plain `ret 4` at
     `0x10036c32` (independently re-confirmed via disassembly this session, matches the address the
     pre-08-14 doc cited).

This script brackets ALL FOUR points with a live Points/Verts/Nodes read of the SAME model pointer
(saved once at entry into a gdb convenience var, `$optmodel`, so later reads are pointer-stable even if
a register gets reused) on the REAL UNATCO/Wanchai goldens:
  ENTRY            -- 0x10036870 (pre-prologue; Model = *(esp+4))
  POST_SHRINK      -- 0x100368ed (right after the `0x33dc0` call + its `add esp,8` cleanup)
  POST_VTCALL200   -- 0x100368fa (right after the `[eax+0x200]` call)
  EXIT             -- 0x10036c1a (still inside the function, before the epilogue pops registers --
                      reading via the saved pointer, not a register, so this is safe regardless)

Usage:  bspoptgeom_pool_trace.py [unatco|wanchai] [golden.dx]
  -> logs/bspoptgeom-pool-<level>.log
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

LEVEL = sys.argv[1] if len(sys.argv) > 1 else "unatco"
DEFAULT_GOLDEN = {
    "unatco": ROOT / "_scratch/bsp-parity-proj/golden_unatco_control.dx",
    "wanchai": ROOT / "_scratch/golden_wanchai_world.dx",
}[LEVEL]
GOLDEN = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_GOLDEN
PROJECT_DIR = ROOT / "_scratch/oracle-project"
POLL, DEADLINE = 2.0, 1200.0

DUMP = (
    r'*(int*)($optmodel+0x5c), *(int*)($optmodel+0x6c), *(int*)($optmodel+0x8c)'
)

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
set $optmodel = 0
break *0x10036870
commands
silent
set $callidx = $callidx + 1
set $optmodel = *(unsigned int *)($esp + 4)
printf "ENTRY callidx=%d model=%#x nodes=%d verts=%d points=%d\n", $callidx, $optmodel, """ + DUMP + r"""
continue
end
break *0x100368ed
commands
silent
printf "POST_SHRINK callidx=%d model=%#x nodes=%d verts=%d points=%d\n", $callidx, $optmodel, """ + DUMP + r"""
continue
end
break *0x100368fa
commands
silent
printf "POST_VTCALL200 callidx=%d model=%#x nodes=%d verts=%d points=%d\n", $callidx, $optmodel, """ + DUMP + r"""
continue
end
break *0x10036c1a
commands
silent
printf "EXIT callidx=%d model=%#x nodes=%d verts=%d points=%d\n", $callidx, $optmodel, """ + DUMP + r"""
printf "OPTGEOM_DONE callidx=%d\n", $callidx
detach
quit
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

    container = f"uned-bspoptpool-{LEVEL}"
    O.stop_dbg_editor(container, state_dir)
    print(f"[bspoptgeom-pool] level={LEVEL} golden={GOLDEN}", flush=True)
    print(f"[bspoptgeom-pool] starting {container} ...", flush=True)
    O.start_dbg_editor(container, mounts, state_dir)
    try:
        drv = Driver(container=container)
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /work/golden.dx"],
                       input=GOLDEN.read_bytes(), check=True)
        drv.exec(f"MAP LOAD FILE={to_z_path('/work/golden.dx')}")
        time.sleep(3.0)
        pid = O._editor_pid(container)
        print(f"[bspoptgeom-pool] editor pid {pid}; attaching gdb ...", flush=True)
        gdb_script = GDB.format(pid=pid)
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /tmp/bopt.gdb"],
                       input=gdb_script, text=True, check=True)
        subprocess.run(["docker", "exec", "-d", container, "bash", "-c",
                        "exec gdb -batch -x /tmp/bopt.gdb > /tmp/bopt.log 2>&1"], check=True)
        for _ in range(120):
            out = subprocess.run(["docker", "exec", container, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/bopt.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if out and out != "0":
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("gdb did not attach")
        print("[bspoptgeom-pool] attached; MAP REBUILD ...", flush=True)
        drv.exec("MAP REBUILD")
        deadline = time.monotonic() + DEADLINE
        while time.monotonic() < deadline:
            done = subprocess.run(["docker", "exec", container, "bash", "-c",
                                   "grep -c '^OPTGEOM_DONE' /tmp/bopt.log 2>/dev/null || true"],
                                  capture_output=True, text=True).stdout.strip()
            if done and done != "0":
                print("[bspoptgeom-pool] OPTGEOM_DONE seen", flush=True)
                break
            time.sleep(POLL)
        else:
            print(f"[bspoptgeom-pool] WARNING: gave up after {DEADLINE:.0f}s, OPTGEOM_DONE never seen",
                  flush=True)
        out = HERE.parent / "logs" / f"bspoptgeom-pool-{LEVEL}.log"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(subprocess.run(["docker", "exec", container, "cat", "/tmp/bopt.log"],
                                       capture_output=True).stdout)
        print(f"[bspoptgeom-pool] wrote {out}", flush=True)
        print(subprocess.run(["bash", "-c",
                              f"grep -E 'ENTRY|POST_|EXIT' {out}"],
                             capture_output=True, text=True).stdout)
    finally:
        O.stop_dbg_editor(container, state_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

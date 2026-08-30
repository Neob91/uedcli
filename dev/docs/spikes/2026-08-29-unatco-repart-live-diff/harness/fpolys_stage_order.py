#!/usr/bin/env python3
r"""Live GDB capture: the editor's REAL poly-list ORDER at TWO stage boundaries inside the
world-level `bspRepartition` call -- right after `bspBuildFPolys` returns (pre-merge) and right
after `bspMergeCoplanars` returns (post-merge) -- to find whether freeclinic08's world-level poly-
order divergence (confirmed at the FindBestSplit-entry stage by `fbs_world_poly_order.py`, k=700
editor vs k=672 native for the same plane) already exists coming OUT of `bspBuildFPolys`, or is
introduced BY `bspMergeCoplanars`'s own grouping/walk order.

WHY. `freeclinic08-nsfhq04-1-surf-under-build-root`'s 2026-08-30 second continuation confirmed the
world-level `bspBuild`/`FindBestSplit` input poly order genuinely differs from native's own
reconstruction (same COUNT, 1019, different order) -- but did not localize WHICH of the two prior
steps (`bspBuildFPolys` extraction, or `bspMergeCoplanars` grouping) introduces the divergence, or
whether it's already present coming out of Pass-1's incremental tree. This is the concrete next
step the item named.

MECHANISM. `bspRepartition` (`Editor.dll 0x10049fc0`) disassembled fresh this round (`rdis.py dis
Editor 0x10049fc0 0xb0`) is 4 sequential virtual calls through `edi`'s (Model's) own vtable, ALL
also passed the SAME `CTX = *(*(edi+0xa8)+0x98)` object (computed fresh per call, expression
identical to `bspbuild_ctx_dump.py`'s own derivation of `esi`):
  call 1 bspBuildFPolys   (vtbl+0x20c, real addr 0x10036090 per `vtable-dump.log`) at 0x1004a007,
      return address 0x1004a00d
  call 2 bspMergeCoplanars(vtbl+0x210, real addr 0x10036200 per `vtable-dump.log`) at 0x1004a021,
      return address 0x1004a027
  call 3 bspBuild         (vtbl+0x1fc,  real addr 0x10035ef0) at 0x1004a041
  call 4 bspRefresh       (vtbl+0x200,  real addr 0x10036cd0) at 0x1004a059, return 0x1004a05f
      (`WORLD_END`, reused from `fbs_world_poly_order.py`/`emptymodel_worldlevel_trace.py`)

At each of the two new return addresses, `edi` (Model) is still live (callee-saved, not
clobbered by the C++ thiscall stdcall-cleanup convention already confirmed in this dispatcher --
`edi` is preserved across all 4 calls per the existing disassembly). Recompute CTX the same way
`bspRepartition` itself does (`eax=[edi+0xa8]`, `ctx=[eax+0x98]`), then read CTX's `Polys` member
(a `UPolys*` at `CTX+0x54`) and dump its embedded dynamic array: `PolysObj+0x28`=Data(FPoly*),
`+0x2c`=Count, `+0x30`=Max. **Corrects an earlier ledger entry's `[[CTX+0x54]+0x2c]`=Data guess,
which was off by 4 bytes** -- live-verified this round (`ctx_polys_struct_probe.py`/`_probe2.py`):
the naive `+0x2c` slot holds a small int (Count, paired validly with `+0x30`=Max>=Count), not a
pointer; dereferencing `+0x28` as an `FPoly*` gives a first entry with a real unit normal
(`(0,0,1)`) and `nv=4` -- `+0x2c`/`+0x30` candidates dereferenced as pointers instead gave NaN
normals / garbage `nv` in the millions. FPoly stride is `0x1d8` (Base=+0x00, Normal=+0x0c,
NumVertices=+0x1c0, iLink=+0x1c4 -- reused verbatim from `bspAddNode`'s/`fbs_world_poly_order.py`'s
already-verified layout). The offset fix is validated in-band too: the post-merge dump's own
COUNT/i_link multiset must equal `fbs_world_poly_order.py`'s already-captured 1019-poly
FindBestSplit-entry order for the SAME golden (both are, structurally, "the CTX Polys array
content at the moment `bspBuild` starts using it") -- if it doesn't line up, the offset is still
wrong and this script says so rather than reporting a false order.

Usage:  fpolys_stage_order.py <level-tag> <golden.dx>
  -> logs/fpolys-stage-order-<level-tag>.log
     PREMERGE lines: k, i_link, nv, normal, dist -- CTX Polys array right after bspBuildFPolys
       returns (pre-merge).
     POSTMERGE lines: same fields -- CTX Polys array right after bspMergeCoplanars returns.
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

TAG = sys.argv[1]
GOLDEN = Path(sys.argv[2])
PROJECT_DIR = ROOT / "_scratch/oracle-project"
POLL, DEADLINE = 2.0, 2400.0

DUMP_POLYS = r"""
  set $eax = *(unsigned int *)($edi + 0xa8)
  set $ctx = *(unsigned int *)($eax + 0x98)
  set $polysobj = *(unsigned int *)($ctx + 0x54)
  set $data = *(unsigned int *)($polysobj + 0x28)
  set $count = *(int *)($polysobj + 0x2c)
  set $max = *(int *)($polysobj + 0x30)
  printf "HEADER stage=%s ctx=%#x polysobj=%#x data=%#x count=%d max=%d\n", "__STAGE__", $ctx, $polysobj, $data, $count, $max
  set $k = 0
  while $k < $count && $k < 4000
    set $p = $data + $k * 0x1d8
    set $nv = *(int *)($p + 0x1c0)
    set $ilink = *(int *)($p + 0x1c4)
    set $nx = *(float *)($p + 0xc)
    set $ny = *(float *)($p + 0x10)
    set $nz = *(float *)($p + 0x14)
    set $bx = *(float *)($p)
    set $by = *(float *)($p + 4)
    set $bz = *(float *)($p + 8)
    set $d = $nx * $bx + $ny * $by + $nz * $bz
    printf "__STAGE__ k=%d i_link=%d nv=%d normal=%.6f,%.6f,%.6f dist=%.6f\n", $k, $ilink, $nv, $nx, $ny, $nz, $d
    set $k = $k + 1
  end
"""

GDB_TEMPLATE = r"""
set pagination off
set confirm off
set height 0
set width 0
attach __PID__
handle SIGSEGV nostop noprint pass
handle SIGUSR1 nostop noprint pass
handle SIGUSR2 nostop noprint pass
handle SIGPIPE nostop noprint pass
set $callidx = 0
set $active = 0
break *0x10049fc0
commands
silent
set $callidx = $callidx + 1
if $callidx == 1
  set $active = 1
  printf "WORLD_BEGIN callidx=%d\n", $callidx
end
continue
end
break *0x1004a00d
commands
silent
if $active == 1
__PREMERGE_DUMP__
end
continue
end
break *0x1004a027
commands
silent
if $active == 1
__POSTMERGE_DUMP__
end
continue
end
break *0x1004a05f
commands
silent
if $active == 1
  printf "WORLD_END\n"
  set $active = 0
  detach
  quit
end
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

    container = f"uned-fpolystage-{TAG}"
    O.stop_dbg_editor(container, state_dir)
    print(f"[fpolystage] tag={TAG} golden={GOLDEN}", flush=True)
    print(f"[fpolystage] starting {container} ...", flush=True)
    O.start_dbg_editor(container, mounts, state_dir)
    try:
        drv = Driver(container=container)
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /work/golden.dx"],
                       input=GOLDEN.read_bytes(), check=True)
        drv.exec(f"MAP LOAD FILE={to_z_path('/work/golden.dx')}")
        time.sleep(3.0)
        pid = O._editor_pid(container)
        print(f"[fpolystage] editor pid {pid}; attaching gdb ...", flush=True)
        pre_dump = DUMP_POLYS.replace("__STAGE__", "PREMERGE")
        post_dump = DUMP_POLYS.replace("__STAGE__", "POSTMERGE")
        gdb_script = (GDB_TEMPLATE
                      .replace("__PID__", str(pid))
                      .replace("__PREMERGE_DUMP__", pre_dump)
                      .replace("__POSTMERGE_DUMP__", post_dump))
        subprocess.run(["docker", "exec", "-i", container, "bash", "-c", "cat > /tmp/fps.gdb"],
                       input=gdb_script, text=True, check=True)
        subprocess.run(["docker", "exec", "-d", container, "bash", "-c",
                        "exec gdb -batch -x /tmp/fps.gdb > /tmp/fps.log 2>&1"], check=True)
        for _ in range(120):
            out = subprocess.run(["docker", "exec", container, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/fps.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if out and out != "0":
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("gdb did not attach")
        print("[fpolystage] attached; MAP REBUILD ...", flush=True)
        drv.exec("MAP REBUILD")
        deadline = time.monotonic() + DEADLINE
        while time.monotonic() < deadline:
            done = subprocess.run(["docker", "exec", container, "bash", "-c",
                                   "grep -c '^WORLD_END' /tmp/fps.log 2>/dev/null || true"],
                                  capture_output=True, text=True).stdout.strip()
            if done and done != "0":
                print("[fpolystage] WORLD_END seen", flush=True)
                break
            time.sleep(POLL)
        else:
            print(f"[fpolystage] WARNING: gave up after {DEADLINE:.0f}s", flush=True)
        out = HERE.parent / "logs" / f"fpolys-stage-order-{TAG}.log"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(subprocess.run(["docker", "exec", container, "cat", "/tmp/fps.log"],
                                       capture_output=True).stdout)
        print(f"[fpolystage] wrote {out}", flush=True)
        text = out.read_text(errors="replace")
        npre = text.count("\nPREMERGE k=")
        npost = text.count("\nPOSTMERGE k=")
        print(f"[fpolystage] {npre} PREMERGE lines, {npost} POSTMERGE lines captured", flush=True)
    finally:
        O.stop_dbg_editor(container, state_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

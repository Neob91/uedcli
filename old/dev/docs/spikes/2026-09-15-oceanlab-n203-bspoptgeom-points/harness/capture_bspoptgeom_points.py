#!/usr/bin/env python3
r"""Live-capture UED22's real `Model->Points` array at `bspOptGeom` ENTRY, for OceanLab N=203.

Continues `dev/docs/board/to-spike/oceanlab-n-203-world-model2-split-vertex-ulp/` and
`dev/docs/spikes/2026-09-14-oceanlab-n203-addpoint-capture/`. That session found the mechanism on
NATIVE's own side: `Brush483`'s new point (x-bits `0xc3800004`) should be welded onto a pre-existing
wall-crossing point (x-bits `0xc3800002`, same y/z) by `bspoptgeom.rs::merge_near_points`, but native's
own points-GC (`bsp_refresh_points_vectors`) already dropped `0xc3800002` beforehand because its owning
node was spliced dead by `bsp_cleanup` -- so by the time native's `merge_near_points` runs, there's
nothing left to weld onto. The open question that session left: is the SAME wall-crossing point ALSO
gone from UED22's real `Model->Points` by the equivalent moment (both dead => the true divergence is
further upstream), or does UED22 still have it (native's node-liveness/GC is too aggressive relative to
the real editor => that IS the bug)?

Method: same live-gdb-attach recipe as `2026-09-14-oceanlab-n203-addpoint-capture/harness/
capture_addpoint.py` (ptrace attach inside the `dx-lum-uned-dbg` container, DLL bases read live and
remapped) and the `2026-07-15-native-materialize/harness/editor-tree-oracle/` oracles (`bspopt_pool_
oracle.py`, `repart_stage_oracle.py`) that already RE'd `bspOptGeom`'s own `Model*` argument and enough
of `UModel`'s in-memory `TArray` layout to read `Points` directly -- reused here, not re-derived from
scratch:

  bspOptGeom ENTRY = Editor.dll (preferred base 0x10000000) 0x10036870 -- first instruction (`push
  ebp`, prologue not yet run), so the sole argument (`Model*`) sits at `[esp+4]`.

  UModel in-memory TArray offsets (RE'd across `bspopt_pool_oracle.py`/`repart_stage_oracle.py`/
  `uedcli-native/src/zones.rs`'s own disassembly comments, all independently agreeing): Nodes
  {Data@+0x58, Num@+0x5c}, Vectors {Data@+0x78, Num@+0x7c}, Points {Data@+0x88, Num@+0x8c}, Surfs
  {Data@+0x98, Num@+0x9c}, Verts {Num@+0x6c}. A `TArray<FVector>` (`Points`/`Vectors`) is a tightly
  packed `{f32 x,y,z}` per entry, 12 bytes/stride, so `Points` is a flat dump-able buffer.

At each `bspOptGeom` call (there may be more than one per `MAP REBUILD` -- e.g. one per mover model --
so this captures up to the first 8 hits), dumps the whole live `Points` AND `Surfs` arrays to files
(`points_hitN.bin`, `surfs_hitN.bin`; `FBspSurf`'s in-memory `pBase` field is at `+0x08`, `vNormal`
at `+0x0c` -- `zones.rs`'s own disassembly comment) and logs `Nodes.Num`/`Verts.Num`/`Points.Num`/
`Surfs.Num`. Offline, `analyze.py` scans every dumped `Points` array for the two divergent-point
coordinates (x-bits `0xc3800002` -- UED22's surviving wall-crossing value -- OR `0xc3800004` --
native's own added value -- paired with either target y/z) to answer the open question directly from
the real editor's own memory, and cross-checks the `Surfs` dump for which (if any) surf's `pBase`
still points at each candidate index -- this needs no node-reachability walk at all, since native's
own `bsp_refresh_points_vectors`/`compact_points_to_surf_bases` scan `Surfs` unconditionally too.

Usage: capture_bspoptgeom_points.py [--out-dir logs]
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
NATIVE_MAT_HARNESS = ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"
ORACLE_DIR = NATIVE_MAT_HARNESS / "editor-tree-oracle"
ACTOR_PARITY_HARNESS = ROOT / "dev/docs/spikes/2026-09-03-incremental-actor-parity/harness"
UNBUILT_HARNESS = ROOT / "dev/docs/spikes/2026-09-02-unbuilt-structure-parity/harness"
HERE = Path(__file__).resolve().parent
for p in (ROOT, NATIVE_MAT_HARNESS, ORACLE_DIR, ACTOR_PARITY_HARNESS, UNBUILT_HARNESS):
    sys.path.insert(0, str(p))

import editor_tree_oracle as O  # noqa: E402
import actor_parity as ap  # noqa: E402
from uedcli import config, trunk  # noqa: E402
from uedcli.apply import _level_referenced_packages  # noqa: E402
from uedcli.classindex import ClassIndex  # noqa: E402
from uedcli.container_assets import resource_mounts  # noqa: E402
from uedcli.driver import Driver, to_z_path  # noqa: E402
from uedcli.emit import emit_map  # noqa: E402
from uedcli.materialize import levelinfo_first_order  # noqa: E402
from uedcli.movers import set_base_pose  # noqa: E402
from uedcli.packages import editor_search_dirs, ensure_load  # noqa: E402
from build_ued_import_built_golden import _dummy_builder_actor  # noqa: E402
from build_ued_import_golden import _quote_str_props  # noqa: E402
from build_ued_golden import _scratch_project  # noqa: E402

CONTAINER = "uned-oceanlab-n203-bspoptgeom"
EDITOR_PREF = 0x10000000
BSPOPTGEOM_ENTRY_VA = 0x10036870
MAX_HITS = 8

DX_PATH = Path("/workspace/uedcli/dev/games/substrate-deusex/Maps/14_OceanLab_Lab.dx")
N = 203


def remap(addr: int, live_base: int, pref: int) -> int:
    return live_base + (addr - pref)


def _find_dll_base(container: str, pid: int, dll: str) -> int:
    maps = subprocess.run(["docker", "exec", container, "cat", f"/proc/{pid}/maps"],
                          capture_output=True, text=True, check=True).stdout
    for line in maps.splitlines():
        if dll.lower() in line.lower():
            return int(line.split("-", 1)[0], 16)
    raise RuntimeError(f"{dll} not found")


def _dump_block(hit: int) -> str:
    return f"""
if $hits == {hit}
dump binary memory /tmp/points_hit{hit}.bin $pdata $pend
dump binary memory /tmp/surfs_hit{hit}.bin $sdata $send
end"""


GDB_SCRIPT = f"""
set pagination off
set confirm off
set height 0
set width 0
attach {{pid}}
handle SIGSEGV nostop noprint pass
handle SIGUSR1 nostop noprint pass
handle SIGUSR2 nostop noprint pass
handle SIGPIPE nostop noprint pass
set $hits = 0

break *{{va:#x}}
commands
silent
set $hits = $hits + 1
set $m = *(unsigned int *)($esp + 4)
set $nodes = *(int *)($m + 0x5c)
set $verts = *(int *)($m + 0x6c)
set $points = *(int *)($m + 0x8c)
set $surfs = *(int *)($m + 0x9c)
printf "BSPOPTGEOM hit=%d model=%#x nodes=%d verts=%d points=%d surfs=%d\\n", $hits, $m, $nodes, $verts, $points, $surfs
set $pdata = *(unsigned int *)($m + 0x88)
set $pend = $pdata + $points * 12
set $sdata = *(unsigned int *)($m + 0x98)
set $send = $sdata + $surfs * 0x40
{"".join(_dump_block(h) for h in range(1, MAX_HITS + 1))}
if $hits >= {MAX_HITS}
printf "ORACLE_MAXHITS\\n"
detach
quit
end
continue
end

printf "ORACLE_ATTACHED\\n"
continue
"""


def main() -> int:
    out_dir = HERE.parent / "logs"
    for i, a in enumerate(sys.argv):
        if a == "--out-dir":
            out_dir = Path(sys.argv[i + 1]).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    full_trunk, name = ap._resolve_trunk(DX_PATH, "deusex")
    subset = ap.make_subset(full_trunk, name, N)
    project = _scratch_project(subset, "deusex")
    user_config = config.load_user_config()
    search_dirs = config.composed_search_dirs(project, user_config)
    mounts = resource_mounts(search_dirs)
    host_search_dirs = editor_search_dirs(search_dirs)

    lvl, _ = trunk.read_level(subset)
    class_idx = ClassIndex.from_files([(f.stem, str(f)) for d in host_search_dirs
                                       for f in sorted(Path(d).glob("*.u"))])
    for an in lvl.order:
        set_base_pose(lvl.actors[an], class_idx)
    classes = {n: lvl.actors[n].cls for n in lvl.order}
    has_brush = {n: lvl.actors[n].brush is not None for n in lvl.order}
    imp_order = levelinfo_first_order(lvl.order, classes, has_brush)
    _quote_str_props(lvl, imp_order, project, user_config)
    actors = [lvl.actors[n] for n in imp_order]
    actors.insert(1, _dummy_builder_actor())
    ref_pkgs = _level_referenced_packages(
        type("L", (), {"actors": {n: lvl.actors[n] for n in imp_order}})())

    O._ensure_dbg_image()
    state_dir = config.state_dir(project.root, create=True)
    O.stop_dbg_editor(CONTAINER, state_dir)
    print(f"[capture] OceanLab N={N}; starting {CONTAINER}", flush=True)
    O.start_dbg_editor(CONTAINER, mounts, state_dir)
    try:
        drv = Driver(container=CONTAINER)
        t3d_path = drv.write_work_file(emit_map(actors), ext="t3d")
        pid = O._editor_pid(CONTAINER)
        editor_base = _find_dll_base(CONTAINER, pid, "editor.dll")
        print(f"[capture] editor pid={pid} Editor.dll live base={editor_base:#x}", flush=True)
        va = remap(BSPOPTGEOM_ENTRY_VA, editor_base, EDITOR_PREF)
        script = GDB_SCRIPT.format(pid=pid, va=va)
        subprocess.run(["docker", "exec", "-i", CONTAINER, "bash", "-c",
                        "cat > /tmp/bspoptgeom.gdb"], input=script, text=True, check=True)
        subprocess.run(["docker", "exec", "-d", CONTAINER, "bash", "-c",
                        "exec gdb -batch -x /tmp/bspoptgeom.gdb > /tmp/bspoptgeom.log 2>&1"], check=True)
        for _ in range(120):
            got = subprocess.run(["docker", "exec", CONTAINER, "bash", "-c",
                                  "grep -c ORACLE_ATTACHED /tmp/bspoptgeom.log 2>/dev/null || true"],
                                 capture_output=True, text=True).stdout.strip()
            if got and got != "0":
                break
            time.sleep(0.5)
        else:
            diag = subprocess.run(["docker", "exec", CONTAINER, "cat", "/tmp/bspoptgeom.log"],
                                  capture_output=True, text=True).stdout
            raise RuntimeError(f"gdb did not attach. log:\n{diag[:3000]}")
        print("[capture] gdb attached; running MAP IMPORT + MAP REBUILD ...", flush=True)
        saved = "/work/probe_n203.dx"
        drv.begin_script()
        ensure_load(drv, ref_pkgs, search_dirs=host_search_dirs, mounts=mounts)
        drv.exec(f"MAP IMPORT FILE={to_z_path(t3d_path)}")
        drv.exec("MAP REBUILD")
        drv.exec(f"MAP SAVE FILE={to_z_path(saved)}")
        try:
            drv.run_script(produces=saved, timeout=1800.0)
        except Exception as ex:  # noqa: BLE001
            print(f"[capture] batch wait ended: {ex}", flush=True)
        log_bytes = subprocess.run(["docker", "exec", CONTAINER, "cat", "/tmp/bspoptgeom.log"],
                                   capture_output=True).stdout
        log_out = out_dir / "capture.log"
        log_out.write_bytes(
            f"Editor.dll live base = {editor_base:#x}  VA = {va:#x}\n\n".encode() + log_bytes)
        print(f"[capture] wrote {log_out}", flush=True)
        for h in range(1, MAX_HITS + 1):
            for stem in ("points", "surfs"):
                src = f"/tmp/{stem}_hit{h}.bin"
                exists = subprocess.run(["docker", "exec", CONTAINER, "test", "-f", src]).returncode == 0
                if not exists:
                    continue
                dst = out_dir / f"{stem}_hit{h}.bin"
                # `docker cp` is broken on this rootless daemon: it deterministically fails with an
                # overlay "remount-ro .../stubs ... operation not permitted" error (the container's
                # read-only /stubs bind mount trips something in `cp`'s merged-dir walk), not a
                # transient fluke -- retrying it does not help. `docker exec ... cat` streams the
                # file's bytes over stdout instead, which never touches that machinery (this is
                # exactly how `capture.log` above is already pulled out).
                proc = subprocess.run(["docker", "exec", CONTAINER, "cat", src], capture_output=True,
                                       check=True)
                dst.write_bytes(proc.stdout)
                print(f"[capture] wrote {dst} ({dst.stat().st_size} bytes)", flush=True)
    finally:
        O.stop_dbg_editor(CONTAINER, state_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

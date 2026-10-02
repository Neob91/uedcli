#!/usr/bin/env python3
"""Build a **UnrealEd golden** `.dx` from a uedcli T3D trunk — UnrealEd's OWN build of the SAME
trunk the native materializer consumes. This is the CORRECT parity basis (board 2026-07-19):

WHY: native `level materialize` parity was long judged against the hand-authored SHIPPED `.dx`
(e.g. `03_NYC_UNATCOHQ.dx`). That is an UNFAIR golden — the shipped map carries authoring history
(object-table/export order, `iActor` numbering, texture-import order) the trunk cannot reproduce, so
a byte diff conflates real geometry drift with pure renumbering. The CORRECT basis is UnrealEd
building the *same trunk*: `MAP NEW` + re-add actors + a FULL rebuild + `LIGHT APPLY` + `MAP SAVE`.
Whatever UnrealEd emits from OUR trunk is the golden native must match.

TWO PARITY BASES — because no single rebuild path serves both (spike §92 stage 0, 2026-07-19;
refines §91). This is the measured resolution of §92 §2's "basis tension":

  (1) NODE / SURF / VECTOR basis  = a BARE `MAP REBUILD` (the `--rebuild-cmd` DEFAULT). native models
      only `csgRebuild` = exactly what `MAP REBUILD` runs (bspRepartition GOOD/Balance-12), so the
      bare-`MAP REBUILD` golden (UNATCO 6314 nodes / 3616 surfs / 599 vectors) is native's EXACT node
      target: native is +111 nodes (+1.76%), +82 surfs, +146 vectors. MEASURED FINDING that forces
      this: ANY `BSP REBUILD` step (GOOD *or* OPTIMAL) RE-PARTITIONS the whole BSP and INFLATES nodes
      — `BSP REBUILD GOOD OPTGEOM ZONES` -> 7273 (+15.2% over bare, MORE than OPTIMAL!), `…OPTIMAL
      OPTGEOM ZONES` -> 6859 (+8.6%). `BSP REBUILD GOOD` is a SEPARATE interactive-parser entry
      (Editor.dll 0x65220) whose Balance/stride is NOT csgRebuild's GOOD/12. So §92 §2 option (b) is
      REJECTED — no `BSP REBUILD` reproduces native's partition — and option (a) holds. (surfs/vectors
      are INVARIANT to the rebuild path: 3616/599 for all four, so native's +82/+146 is real.)

  (2) LEAF / VERT (refs/leaf==1.0) property basis = `MAP REBUILD;BSP REBUILD GOOD OPTGEOM ZONES`
      (opt-in, non-default). A bare `MAP REBUILD` skips the visibility/leaf pass
      (`TestVisibility`/`AssignLeaves`, gated on the `ZONES` keyword of the SEPARATE `BSP REBUILD`
      parser), so it ships a STALE leaf array from the incremental EDIT PASTE (762 leaves across 4454
      empty cells, refs/leaf 9.45 — §91). `BSP REBUILD` alone gives an EMPTY Model (never runs
      csgRebuild), so the clean-leaf sequence is TWO commands: `MAP REBUILD` then `BSP REBUILD GOOD
      OPTGEOM ZONES` -> AssignLeaves on the populated tree, refs/leaf == 1.0 + full Pass-D vert
      re-emit. But its NODE count is re-partitioned (7273) and is NOT native's basis — use ONLY its
      leaf/vert SHAPE for parity, not its node count. `bsp_health_check.py` ASSERTS refs/leaf == 1.0,
      which (correctly) FLAGS a bare-`MAP REBUILD` golden's stale leaves — expected: that golden's
      Nodes/Surfs/Vectors are the parity target, its Leaves are not.

native itself carries BOTH correctly at once (6425 nodes on the csgRebuild partition AND its own
clean refs/leaf==1.0 Pass-A), which the editor only produces across two different rebuild paths.
Pass `--rebuild-cmd "…OPTIMAL OPTGEOM ZONES"` to reproduce a GUI 'Rebuild Geometry' (Optimize=Optimal)
map for byte-identity to a GUI rebuild.

THE HEADLESS-BUILD BLOCKER this harness works around (spike section 89): the editor driver's
`wine_ctl exec` FIRES a console command and returns after ~0.3 s — it does NOT wait for the command
to finish. On the 95-brush castle a `MAP REBUILD` completes inside that window, so the production
`apply.run_materialize` path works. On a real level (UNATCO: 1437 actors / 734 CSG brushes) the
rebuild takes many seconds-to-minutes; `run_materialize` fires `MAP REBUILD`, then immediately
`LIGHT APPLY`, `MAP SAVE`, and `docker cp` — the `.dx` is not written yet and the cp fails
("nothing written"). So a headless build at scale needs an editor-IDLE wait between heavy steps,
which `run_materialize` has no hook for. This harness therefore drives the ephemeral editor itself
(the driver-primitives path the parity task calls out), reusing the SAME library helpers
(`ensure_editor`, `ensure_load`, `writes._re_add`, `xfer`) but inserting a CPU-idle barrier
(`_wait_idle`, via `docker stats`) after the paste, the rebuild, and the light bake, and waiting for
the saved file to stabilise before copying it out.

Class/stub note: OG-DX trunks name actor classes BARE (`Class=DeusExMover`, `Class=AllianceTrigger`).
With no v69 stub for `DeusEx.u`, the editor cannot resolve those and skips them — but they are POINT
actors and MOVERS that do NOT participate in the world CSG, so the level Model BSP (the deterministic
parity target) is built from exactly the 734 engine-`Class=Brush` CSG brushes native also uses.
`Class=Light` IS an engine class, so a full+lit golden bakes real lighting. `--world-only` drops
everything but `Brush`+`LevelInfo` for the cleanest geometry-only golden (matches the native
"World" build); `--no-light` skips the bake to compare unlit-vs-unlit.

Usage:
  build_ued_golden.py --trunk <trunk> --out <golden.dx> [--world-only] [--no-light]
                      [--game deusex] [--overwrite]

Run it as a BOUNDED BACKGROUND JOB — the editor wedges silently.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]      # Tools/uedcli (harness/ -> spike/ -> spikes/ -> docs/ -> dev/ -> root)
sys.path.insert(0, str(ROOT))

from uedcli import config, trunk, xfer                          # noqa: E402
from uedcli.container_assets import resource_mounts             # noqa: E402
from uedcli.driver import Driver                                # noqa: E402
from uedcli.editor import ensure_editor, stop_editor            # noqa: E402
from uedcli.apply import _level_referenced_packages             # noqa: E402
from uedcli.materialize import levelinfo_first_order, _short_class  # noqa: E402
from uedcli.packages import editor_search_dirs, ensure_load     # noqa: E402
from uedcli.writes import _re_add                               # noqa: E402
from uedcli.uuid7 import uuid7                                  # noqa: E402

DEFAULT_TRUNK = str(ROOT / "_scratch/unatco/uedcli/maps/unatco")
DEFAULT_OUT = str(ROOT / "_scratch/uedgolden/UEDGolden_unatco.dx")


def _cpu_pct(container: str) -> float:
    """Instantaneous whole-container CPU% via `docker stats --no-stream` (which self-samples over
    ~1-2 s, so it doubles as the poll interval). ~100%+ while a rebuild churns, ~0 when idle."""
    r = subprocess.run(["docker", "stats", "--no-stream", "--format", "{{.CPUPerc}}", container],
                       capture_output=True, text=True)
    return float((r.stdout.strip().rstrip("%")) or 0.0)


def _wait_idle(driver: Driver, *, label: str, thresh: float = 30.0, quiet_reads: int = 8,
               min_seconds: float = 0.0, timeout: float = 1800.0) -> float:
    """Block until the editor container CPU stays under `thresh`% for `quiet_reads` CONSECUTIVE
    reads (~1.5 s/read via docker stats) — the editor finished the console command — or raise
    TimeoutError. This is the barrier `wine_ctl exec` lacks.

    `quiet_reads` must be generous: `MAP REBUILD` runs in PHASES (CSG carve, then BSP build/optimize,
    then portalize/zone) with brief CPU lulls BETWEEN phases. A short quiet window fires during such
    a lull and MAP SAVE then captures a PARTIALLY-rebuilt level (symptom: a plausible node count but a
    truncated Leaves array). `min_seconds` refuses to declare idle before that much wall time has
    passed since the command, as a floor against an instant-idle false positive.

    Each poll defensively dismisses the "Cleaning up..." GC `xmessage` dialog
    (`Driver.dismiss_blocking_dialog()`), mirroring `qualify.dump_obj_dependencies`/
    `_read_loaded_classes` (`unrealed/quirks.md` "Stability"). The dialog never auto-closes headless;
    left up, this barrier has nothing to dismiss it and the caller times out at `timeout`
    (observed live, Training Final 2026-09-02, at both the `map-new` 1800s default and the
    `--rebuild-timeout` 2400s cap)."""
    t0 = time.time()
    quiet = 0
    last = -1.0
    while True:
        driver.dismiss_blocking_dialog()
        cpu = _cpu_pct(driver.container)
        last = cpu
        quiet = quiet + 1 if cpu < thresh else 0
        el = time.time() - t0
        if quiet >= quiet_reads and el >= min_seconds:
            print(f"    [{label}] idle after {el:.0f}s (cpu {cpu:.1f}%, {quiet} quiet reads)", flush=True)
            return el
        if el > timeout:
            raise TimeoutError(f"editor not idle after {timeout:.0f}s [{label}] (last cpu {last:.1f}%)")
        time.sleep(1.0)


def _scratch_project(trunk_dir: Path, game: str) -> config.Project:
    maps_root = trunk_dir.parent
    proj_root = maps_root.parent
    toml = proj_root / "uedcli.toml"
    if not toml.exists():
        toml.write_text(f'game = "{game}"\nmaps = "{maps_root.name}"\n')
    return config.load_project(str(proj_root))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--trunk", default=DEFAULT_TRUNK)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--game", default="deusex")
    ap.add_argument("--world-only", action="store_true",
                    help="keep only Brush + LevelInfo actors (cleanest geometry golden)")
    ap.add_argument("--no-light", action="store_true", help="skip LIGHT APPLY (unlit golden)")
    ap.add_argument("--no-obj-load", action="store_true",
                    help="skip OBJ LOAD of referenced texture/sound packages (geometry/BSP node "
                         "planes do not depend on texture resolution; this environment's package "
                         "load is extremely slow, so a geometry-only diagnostic golden can skip it)")
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--rebuild-timeout", type=float, default=2400.0)
    ap.add_argument("--quiet-reads", type=int, default=8,
                    help="consecutive sub-threshold CPU reads to declare the editor idle. Raise it "
                         "(e.g. 30) to force a MORE generous barrier — a too-short window fires in an "
                         "inter-phase rebuild lull and MAP SAVE captures a PARTIALLY-built tree "
                         "(symptom: a truncated Leaves array, refs/leaf > 1 — see spike section 91).")
    ap.add_argument("--rebuild-min-seconds", type=float, default=0.0,
                    help="refuse to declare the rebuild idle before this many wall seconds "
                         "(floor against an instant-idle false positive mid-rebuild).")
    ap.add_argument("--rebuild-cmd", default="MAP REBUILD",
                    help="';'-separated exec verbs run IN ORDER to rebuild geometry+BSP. "
                         "DEFAULT is a BARE `MAP REBUILD` — the NATIVE NODE/SURF/VECTOR PARITY BASIS "
                         "(spike §92 stage 0, 2026-07-19). native models only `csgRebuild` = exactly what "
                         "`MAP REBUILD` runs (bspRepartition GOOD/Balance-12/stride=NumPolys/20, §82 "
                         "§5/§10.10), so the bare-`MAP REBUILD` golden (UNATCO: 6314 nodes / 3616 surfs / "
                         "599 vectors) is native's exact node target — native is +111 nodes (+1.76%), +82 "
                         "surfs, +146 vectors against it. CRUCIAL MEASURED FINDING (§92 stage 0): ANY `BSP "
                         "REBUILD` step (GOOD *or* OPTIMAL) RE-PARTITIONS the whole BSP away from that "
                         "csgRebuild tree and INFLATES node count — `BSP REBUILD GOOD OPTGEOM ZONES` -> "
                         "7273 nodes (+15.2%!), `BSP REBUILD OPTIMAL OPTGEOM ZONES` -> 6859 (+8.6%); "
                         "`BSP REBUILD GOOD` is a SEPARATE interactive-parser entry point (Editor.dll "
                         "0x65220) whose Balance/stride is NOT csgRebuild's GOOD/12 and produces MORE "
                         "nodes than even OPTIMAL. So §92 §2 option (b) is REJECTED: no `BSP REBUILD` "
                         "reproduces native's partition; the bare `MAP REBUILD` golden is the node basis. "
                         "(surfs=3616/vectors=599 are INVARIANT to the rebuild path — native's +82/+146 "
                         "is real and basis-independent.) TRADE-OFF: a bare `MAP REBUILD` golden's Leaves "
                         "array is STALE (refs/leaf 9.45; §91) — its Nodes/Surfs/Vectors are complete and "
                         "trustworthy but it is UNUSABLE for Leaves/Verts parity. For the refs/leaf==1.0 "
                         "LEAF/VERT property basis pass `--rebuild-cmd 'MAP REBUILD;BSP REBUILD GOOD "
                         "OPTGEOM ZONES'` (clean AssignLeaves) — but treat ONLY its leaf/vert SHAPE as "
                         "parity, NOT its re-partitioned node count. Pass `…OPTIMAL OPTGEOM ZONES` to "
                         "reproduce a GUI 'Rebuild Geometry' (Optimize=Optimal) map for byte-identity to "
                         "a GUI rebuild. Two bases (option a), because no single rebuild path gives both. "
                         "The bare `MAP REBUILD` alone (UEditorEngine::Rebuild, MAP-exec vtable 0xec) "
                         "runs csgRebuild+bspBuild but does NOT run the visibility/leaf pass "
                         "(TestVisibility/AssignLeaves) on the final tree, so the on-disk Leaves array "
                         "is left STALE from the incremental EDIT PASTE (762 leaves reused across 4454 "
                         "empty cells, refs/leaf 9.45; 2750 iLeaf slots on NON-terminal nodes — spike "
                         "section 91). The visibility/leaf pass is gated on the `ZONES` keyword of the "
                         "SEPARATE `BSP REBUILD` parser (Editor.dll 0x65435 -> the 0x264 vtable call "
                         "at 0x5482, skipped via `je 0x1006548a` when ZONES is absent); OPTGEOM (the "
                         "vert re-emit) is gated on `OPTGEOM` (0x218 at 0x54d9). But `BSP REBUILD` "
                         "ALONE gives an EMPTY Model — it operates on the already-CSG'd model and "
                         "never runs csgRebuild (nodes=0 verified). So the faithful sequence is "
                         "TWO commands: `MAP REBUILD` (csgRebuild+bspBuild) THEN `BSP REBUILD OPTIMAL "
                         "OPTGEOM ZONES` (re-optimize + AssignLeaves on the populated tree) -> "
                         "one leaf per empty cell, refs/leaf == 1.0. This mirrors the GUI 'Rebuild "
                         "Geometry' dialog (checkboxes &BSP / Optimize Geometry / &Build Visibility "
                         "Zones -> `BSP REBUILD <opt> OPTGEOM ZONES`, unrealed.exe 0x84b60).")
    args = ap.parse_args()

    trunk_dir = Path(args.trunk).resolve()
    host_out = Path(args.out).resolve()
    if not (trunk_dir / "actors").is_dir():
        print(f"not a trunk dir: {trunk_dir}", file=sys.stderr); return 2
    if host_out.exists() and not args.overwrite:
        print(f"refusing to overwrite {host_out} (--overwrite)", file=sys.stderr); return 2

    user_config = config.load_user_config()
    project = _scratch_project(trunk_dir, args.game)
    search_dirs = config.composed_search_dirs(project, user_config)
    mounts = resource_mounts(search_dirs)
    host_search_dirs = editor_search_dirs(search_dirs)

    lvl, _ranks = trunk.read_level(trunk_dir)
    order = lvl.order
    if args.world_only:
        keep = [n for n in order
                if _short_class(lvl.actors[n].cls) in ("Brush", "LevelInfo")]
        order = keep
    classes = {n: lvl.actors[n].cls for n in order}
    has_brush = {n: lvl.actors[n].brush is not None for n in order}
    imp_order = levelinfo_first_order(order, classes, has_brush)
    actors = [lvl.actors[n] for n in imp_order]
    n_brush = sum(1 for n in imp_order if has_brush[n])
    print(f"trunk {trunk_dir.name}: {len(lvl.actors)} actors; building {len(actors)} "
          f"({n_brush} brush) world_only={args.world_only} lit={not args.no_light}", flush=True)

    ref_pkgs = _level_referenced_packages(
        type("L", (), {"actors": {n: lvl.actors[n] for n in imp_order}})())
    print(f"referenced packages to OBJ LOAD: {ref_pkgs}", flush=True)

    state_dir = config.state_dir(project.root, create=True)
    ed_id = uuid7()
    container = None
    work_out = None
    try:
        container = ensure_editor(ed_id, mounts=mounts, state_dir=state_dir)
        ed = Driver(container=container)
        print(f"editor up: {container}", flush=True)
        if args.no_obj_load:
            print("  (--no-obj-load: skipping OBJ LOAD of referenced packages)", flush=True)
        else:
            ensure_load(ed, ref_pkgs, search_dirs=host_search_dirs, mounts=mounts)
            _wait_idle(ed, label="obj-load")
        ed.map_new()
        _wait_idle(ed, label="map-new")
        _re_add(ed, actors)
        _wait_idle(ed, label="re-add", timeout=args.rebuild_timeout)
        for i, cmd in enumerate(c.strip() for c in args.rebuild_cmd.split(";") if c.strip()):
            print(f"  REBUILD[{i}]: {cmd} ...", flush=True)
            ed.exec(cmd)
            _wait_idle(ed, label=f"rebuild[{i}]", timeout=args.rebuild_timeout,
                       quiet_reads=args.quiet_reads, min_seconds=args.rebuild_min_seconds)
        if not args.no_light:
            print("  LIGHT APPLY ...", flush=True)
            ed.light_apply()
            _wait_idle(ed, label="light-apply", timeout=args.rebuild_timeout,
                       quiet_reads=args.quiet_reads)
        work_out = xfer.work_path("dx")
        print("  MAP SAVE ...", flush=True)
        # `map_save` itself waits for a stable, structurally COMPLETE package and returns the size
        # (driver.map_save; rationale/driver.md 2026-07-25 11:31 UTC), so the harness's own duplicate wait
        # (`_wait_file_stable`, the weaker "size stopped growing" rule) is gone. NB this pipeline
        # produced the §91 golden — whose leaf array is now known to be DETERMINISTIC, not truncated.
        size = ed.map_save(work_out)
        host_out.parent.mkdir(parents=True, exist_ok=True)
        xfer.cp_out(container, work_out, str(host_out))
        print(f"WROTE {host_out} ({size} bytes container-side, "
              f"{host_out.stat().st_size} host-side)", flush=True)
    finally:
        if container and work_out:
            xfer.remove(container, work_out)
        stop_editor(ed_id, state_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())

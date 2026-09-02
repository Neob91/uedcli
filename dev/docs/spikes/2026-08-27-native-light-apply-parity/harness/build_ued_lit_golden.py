#!/usr/bin/env python3
"""Build the LIT UnrealEd golden the native lighting bake is judged against.

Why not the production `level materialize` editor path: that path assembles an unbuilt package and
`MAP LOAD`s it, and the editor then carves a DIFFERENT world BSP from the very same brushes than it
does when the brushes arrive via `MAP NEW` + `EDIT PASTE` (measured on `03_NYC_UNATCOHQ` -- mislabeled
`01_NYC_UNATCOHQ` until 2026-08-31, see board item `unatco-baseline-trunk-is-actually-03-nyc` -- world-only
either way: MAP LOAD 3705 surfs / 6254 nodes / 776 leaves, paste 3616 / 6314 / 762). The native CSG
core reproduces the PASTE tree exactly, so the lit oracle has to be built the paste way too —
otherwise every lightmap record on the two sides describes a different surface and no byte comparison
means anything.

So this is `2026-07-15-native-materialize/harness/build_ued_golden.py`'s pipeline —
`OBJ LOAD` -> `MAP NEW` -> `EDIT PASTE`/`MAP IMPORTADD` -> `MAP REBUILD` -> `LIGHT APPLY` ->
`MAP SAVE`, each step behind a CPU-idle barrier because `wine_ctl exec` does not wait — with one
change: the actor filter keeps the level's LIGHTS as well as its geometry.

The filter matters in both directions. Keep too little and the golden bakes no lighting; keep too
much and the golden's GEOMETRY is contaminated, because `_re_add` pastes any brush-bearing actor as a
world brush — a `DeusExMover` included, and a real level's movers add hundreds of surfaces the
editor's own build keeps in a separate per-mover model.

So the default keeps every actor class in the trunk EXCEPT classes that descend from `Engine.Mover`
(schema-checked via `classindex.ClassIndex` + `movers.is_mover` -- not a name guess), plus it always
keeps `Brush` + `LevelInfo` + **every class the bake itself would treat as a light**, derived from the
trunk via `native.materialize.gather_lights` rather than hardcoded. Hardcoding `Light` is a trap:
`09_HONGKONG_WANCHAI_MARKET` has 13 `Engine.Spotlight`s alongside its 221 `Engine.Light`s, and a
golden built without them reads as native inventing 13 lights. A class whose mover-ness can't be
determined (its package isn't on the search path, or a bare name collides across packages with
disagreeing verdicts) is excluded conservatively, not guessed safe. Any kept class that actually
carries a brush is still refused at build time regardless of how it got into `keep` -- the backstop
below, not just the mover check, is what keeps the geometry honest.

Run it as a BOUNDED BACKGROUND JOB — the editor wedges silently.

Usage:
  build_ued_lit_golden.py --trunk <trunk-dir> --out <golden.dx> [--overwrite]
                          [--keep-classes Brush,LevelInfo,Light|ALL] [--no-light]
                          [--allow-brush-bearing]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"))

from uedcli import config, movers, trunk, xfer                      # noqa: E402
from uedcli.apply import _level_referenced_packages                 # noqa: E402
from uedcli.classdefaults import ClassDefaults                      # noqa: E402
from uedcli.classindex import ClassIndex, ClassRefError             # noqa: E402
from uedcli.container_assets import resource_mounts                 # noqa: E402
from uedcli.driver import Driver                                    # noqa: E402
from uedcli.editor import ensure_editor, stop_editor                # noqa: E402
from uedcli.materialize import levelinfo_first_order, _short_class   # noqa: E402
from uedcli.native.materialize import gather_lights                 # noqa: E402
from uedcli.packages import editor_search_dirs, ensure_load, schema_resolver  # noqa: E402
from uedcli.uuid7 import uuid7                                      # noqa: E402
from uedcli.writes import _re_add                                   # noqa: E402

from build_ued_golden import _scratch_project, _wait_idle            # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--trunk", required=True, help="the T3D trunk dir (holds actors/)")
    ap.add_argument("--out", required=True, help="host path for the built golden .dx")
    ap.add_argument("--game", default="deusex")
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--keep-classes", default=None,
                    help="comma-separated SHORT class names to build; everything else is dropped. "
                         "Pass ALL to keep every class present in the trunk with no filtering at all "
                         "(for measuring geometry contamination -- see --allow-brush-bearing). "
                         "Default: every trunk class except Engine.Mover descendants, plus always "
                         "Brush, LevelInfo, and every class the bake treats as a light (derived from "
                         "the trunk). Keeping a brush-bearing class other than Brush (a Mover) "
                         "contaminates the world BSP, because _re_add pastes it as a world brush.")
    ap.add_argument("--allow-brush-bearing", action="store_true",
                    help="do not refuse when a kept class other than Brush carries its own brush/"
                         "model (e.g. a Mover). UNSAFE for the golden's normal geometry-parity "
                         "purpose -- _re_add pastes such an actor as a WORLD brush, which can change "
                         "the built BSP. Only for deliberately measuring that contamination.")
    ap.add_argument("--no-light", action="store_true", help="skip LIGHT APPLY (unlit control)")
    ap.add_argument("--rebuild-cmd", default="MAP REBUILD",
                    help="the rebuild step(s), ';'-separated. The DEFAULT bare `MAP REBUILD` is the "
                         "native node/surf parity basis: any `BSP REBUILD` step re-partitions the "
                         "tree and inflates the node count (see build_ued_golden.py's own note).")
    ap.add_argument("--rebuild-timeout", type=float, default=2400.0)
    ap.add_argument("--quiet-reads", type=int, default=8)
    args = ap.parse_args()

    trunk_dir = Path(args.trunk).resolve()
    host_out = Path(args.out).resolve()
    if not (trunk_dir / "actors").is_dir():
        print(f"not a trunk dir: {trunk_dir}", file=sys.stderr)
        return 2
    if host_out.exists() and not args.overwrite:
        print(f"refusing to overwrite {host_out} (--overwrite)", file=sys.stderr)
        return 2

    user_config = config.load_user_config()
    project = _scratch_project(trunk_dir, args.game)
    search_dirs = config.composed_search_dirs(project, user_config)
    mounts = resource_mounts(search_dirs)
    host_search_dirs = editor_search_dirs(search_dirs)

    lvl, _ranks = trunk.read_level(trunk_dir)
    all_short = {(_short_class(lvl.actors[n].cls) or "").casefold() for n in lvl.order}
    if args.keep_classes:
        if args.keep_classes.strip().upper() == "ALL":
            keep = set(all_short)
        else:
            keep = {c.strip().casefold() for c in args.keep_classes.split(",") if c.strip()}
    else:
        lights = gather_lights(lvl, defaults=ClassDefaults(
            schema_resolver(project, user_config)))
        light_classes = {(_short_class(lvl.actors[n].cls) or "").casefold()
                         for n, *_rest in lights}
        class_index = ClassIndex.from_project(project, user_config)
        mover_short: set[str] = set()
        unresolved_short: set[str] = set()
        if class_index.class_exists(movers.MOVER_BASE):
            for n in lvl.order:
                actor = lvl.actors[n]
                short = (_short_class(actor.cls) or "").casefold()
                if not short or short in mover_short or short in unresolved_short:
                    continue
                try:
                    if movers.is_mover(actor, class_index):
                        mover_short.add(short)
                except ClassRefError as e:
                    unresolved_short.add(short)
                    print(f"cannot determine mover-ness for class {actor.cls!r}: {e} -- "
                          f"excluding conservatively", file=sys.stderr)
            keep = (all_short - mover_short - unresolved_short) | {"brush", "levelinfo"} | light_classes
            if mover_short:
                print(f"Mover-descendant classes excluded (brush-bearing): {sorted(mover_short)}",
                      flush=True)
            if unresolved_short:
                print(f"classes excluded (mover-ness undetermined): {sorted(unresolved_short)}",
                      flush=True)
        else:
            print(f"cannot resolve {movers.MOVER_BASE} on this search path -- falling back to the "
                  f"narrow default (brush+levelinfo+light classes only)", file=sys.stderr)
            keep = {"brush", "levelinfo"} | light_classes
        print(f"light classes in this trunk: {sorted(light_classes)}", flush=True)
    if bad := sorted({lvl.actors[n].cls for n in lvl.order
                      if (_short_class(lvl.actors[n].cls) or "").casefold() in keep
                      and (_short_class(lvl.actors[n].cls) or "").casefold() != "brush"
                      and lvl.actors[n].brush is not None}):
        if args.allow_brush_bearing:
            print(f"WARNING: proceeding despite brush-bearing classes in keep (--allow-brush-bearing): "
                  f"{', '.join(bad)} -- the golden's geometry may not be the one native builds",
                  file=sys.stderr)
        else:
            print(f"refusing to build: {', '.join(bad)} carries a brush, and `_re_add` would paste it "
                  f"as a WORLD brush -- the golden's geometry would not be the one native builds",
                  file=sys.stderr)
            return 2
    order = [n for n in lvl.order
             if (_short_class(lvl.actors[n].cls) or "").casefold() in keep]
    classes = {n: lvl.actors[n].cls for n in order}
    has_brush = {n: lvl.actors[n].brush is not None for n in order}
    imp_order = levelinfo_first_order(order, classes, has_brush)
    actors = [lvl.actors[n] for n in imp_order]
    n_brush = sum(1 for n in imp_order if has_brush[n])
    print(f"trunk {trunk_dir.name}: {len(lvl.actors)} actors; building {len(actors)} "
          f"({n_brush} brush, {len(actors) - n_brush} point) keep={sorted(keep)} "
          f"lit={not args.no_light}", flush=True)

    ref_pkgs = _level_referenced_packages(
        type("L", (), {"actors": {n: lvl.actors[n] for n in imp_order}})())
    print(f"referenced packages to OBJ LOAD: {ref_pkgs}", flush=True)

    state_dir = config.state_dir(project.root, create=True)
    ed_id = uuid7()
    container = work_out = None
    try:
        container = ensure_editor(ed_id, mounts=mounts, state_dir=state_dir)
        ed = Driver(container=container)
        print(f"editor up: {container}", flush=True)
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
                       quiet_reads=args.quiet_reads)
        if not args.no_light:
            print("  LIGHT APPLY ...", flush=True)
            ed.light_apply()
            _wait_idle(ed, label="light-apply", timeout=args.rebuild_timeout,
                       quiet_reads=args.quiet_reads)
        work_out = xfer.work_path("dx")
        print("  MAP SAVE ...", flush=True)
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

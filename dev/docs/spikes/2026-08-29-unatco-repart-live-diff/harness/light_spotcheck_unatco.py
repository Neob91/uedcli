#!/usr/bin/env python3
r"""Lighting spot-check for the `repartition_frontier` fix (Verts/Points-only pass, no node graft) —
`unatco-verts-points-residual-after-the-zone`. UNATCO's tree is now node-exact for the first time
since the repartition-frontier work started (`native-light-apply-bake-where-it-stands-and`'s own
UNATCO table has been marked STALE for exactly this reason: "needs UNATCO's node-exactness restored
... before trusting anything again"). This does NOT redo that item's full analysis -- it's a bounded
spot check that the fix doesn't break lighting, reusing the EXISTING lit golden
(`_scratch/native-visgate-2026-08-29/golden_unatco_lit.dx`, built 2026-08-29 via the real editor's
MAP NEW -> EDIT PASTE -> MAP REBUILD -> LIGHT APPLY -> MAP SAVE flow, per that item's own reproduction
steps) rather than a fresh (costly) editor capture -- the golden reflects the EDITOR's real behavior,
unaffected by this native-side change.

Mirrors `uedcli/apply.py`'s own `_materialize_native` logic directly (`build_world_model` +
`gather_lights` + `assemble_unbuilt`), using the SAME UNATCO trunk `regression_gate.py` already uses,
rather than going through the CLI's `level/NAME` project convention (this project directory uses
`maps/unatco`, not that convention).

Usage:  light_spotcheck_unatco.py
  -> writes logs/light-spotcheck-unatco-native.dx, prints lightparity.py's own summary.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
LIGHT_HARNESS = ROOT / "dev/docs/spikes/2026-08-27-native-light-apply-parity/harness"
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

TRUNK = ROOT / "_scratch/bsp-parity-proj/maps/unatco"
GOLDEN = ROOT / "_scratch/native-visgate-2026-08-29/golden_unatco_lit.dx"
OUT = HERE.parent / "logs" / "light-spotcheck-unatco-native.dx"


def main() -> int:
    if not GOLDEN.exists():
        print(f"[spotcheck] golden not found: {GOLDEN}", file=sys.stderr)
        return 2

    import os
    os.environ["UEDCLI_PROJECT"] = str(TRUNK.parent.parent)
    from uedcli import config, trunk, packages
    from uedcli.classdefaults import ClassDefaults
    from uedcli.native.materialize import build_world_model, gather_lights, resolve_zone_actors
    from uedcli.native.unbuilt import assemble_unbuilt, substrate_schema
    sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"))
    from spike_classindex import class_index  # noqa: E402

    project = config.load_project(str(TRUNK.parent.parent))
    user_config = config.load_user_config()
    pkg_dirs = [str(d) for d in config.composed_search_dirs(project, user_config)]

    level, _ranks = trunk.read_level(TRUNK)
    ci = class_index()
    resolver = packages.schema_resolver(project, user_config)
    defaults = ClassDefaults(resolver)
    try:
        lights = gather_lights(level, defaults=defaults)
    except Exception as e:
        print(f"[spotcheck] gather_lights needs a real schema resolver: {e}", file=sys.stderr)
        return 2
    print(f"[spotcheck] {len(lights)} participating light(s)", flush=True)

    world_model, csg_brushes = build_world_model(level, index=ci, lights=lights)
    print(f"[spotcheck] world_model nodes={len(world_model.nodes)} verts={len(world_model.verts)} "
          f"points={len(world_model.points)}", flush=True)

    dx_bytes, warnings = assemble_unbuilt(
        level, schema=substrate_schema(*pkg_dirs), pkg_dirs=pkg_dirs, world_model=world_model,
        csg_brushes=csg_brushes, zone_actors=resolve_zone_actors(level, world_model),
        light_names=[n for n, *_rest in lights])
    for w in warnings:
        print(f"[spotcheck] warning: {w}", file=sys.stderr)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(dx_bytes)
    print(f"[spotcheck] wrote {OUT} ({len(dx_bytes)} bytes)", flush=True)

    subprocess.run([sys.executable, str(LIGHT_HARNESS / "lightparity.py"), str(OUT), str(GOLDEN)],
                    check=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

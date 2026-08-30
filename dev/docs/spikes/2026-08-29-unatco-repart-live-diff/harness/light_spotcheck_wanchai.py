#!/usr/bin/env python3
r"""Lighting re-measure for Wanchai on the CURRENT tree — `native-light-apply-bake-where-it-stands-
and`'s task to re-measure the lighting gap breakdown before chasing gap 1 or 2. The last full Wanchai
lighting measurement (72.8%, `getvisiblesurfs-wanchai-run-gap-root-cause`) predates the
`repartition_frontier` rewrite (`unatco-verts-points-residual-after-the-zone`, commit `bcc3693`),
which changed Wanchai's own Verts residual (+138 -> +74) — a geometry-side change that can move the
Pan/UScale/VScale bucket, so the old `native_pxctr.dx` build is stale and must be rebuilt fresh.

Mirrors `light_spotcheck_unatco.py`'s approach (`uedcli/apply.py`'s `_materialize_native` logic
directly — `build_world_model` + `gather_lights` + `assemble_unbuilt`), against the trunk
`dev/games/trunks/tmp-wanchai-market` (project root `dev/games`, holding `uedcli.toml`) and the
existing, provenance-confirmed lit golden `_scratch/wanchai-relight-2026-08-29/golden.dx` (editor
build, unaffected by native-side code changes — see `native-materialize-findings.md`'s "provenance —
CONFIRMED" entry).

Usage:  light_spotcheck_wanchai.py
  -> writes logs/light-spotcheck-wanchai-native.dx, prints lightparity.py's own summary.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
LIGHT_HARNESS = ROOT / "dev/docs/spikes/2026-08-27-native-light-apply-parity/harness"
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

TRUNK = ROOT / "dev/games/trunks/tmp-wanchai-market"
GOLDEN = ROOT / "_scratch/wanchai-relight-2026-08-29/golden.dx"
OUT = HERE.parent / "logs" / "light-spotcheck-wanchai-native.dx"


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
    lights = gather_lights(level, defaults=defaults)
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

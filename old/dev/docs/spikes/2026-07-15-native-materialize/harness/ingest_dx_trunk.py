#!/usr/bin/env python3
"""Ingest an on-disk `.dx` map into a uedcli T3D trunk — OFFLINE (no live editor, no stubs).

Regenerates the wipeable acceptance trunks (`_scratch/castle/...`) from `Maps/Test_Castle.dx`,
and builds scratch trunks from RETAIL maps for `level preview --native` study (e.g. the UNATCO
maps). Two pieces:

1. **UCC batchexport** (`store_export.export_dx_level`) in a NO-GUI ephemeral build container
   (`stub.ephemeral_build_container`) — reads the `.dx` bytes, no live editor. The map's package
   dirs ride in as `/resources` mounts so demand-loaded deps resolve.
2. **Host-side texture qualification**: batchexport strips the `Texture=` package qualifier
   (spikes/2026-06-19-t3d-package-qualification), and the canonical recovery
   (`qualify.export_and_qualify`) needs a live editor + the full stub closure. This script
   instead qualifies each bare ref from the `.dx`'s OWN import table (`utexture.load_package`
   reads any UE1 package's header tables): every imported Texture object names its owning
   package exactly. Same-bare-name imports from two packages get a warning (first wins).

The result is a trunk for RENDERING/study — actor classes stay as exported (bare); `preview_native`
copes (its brush detection is bare-name, and the schema-aware `movers.is_mover` resolves a bare
class through the class index). NOT a materialize-grade ingest
(that is the future `level import` verb — direction/trunk-and-editor.md `--from-dx` note).

Usage:
    .venv/bin/python ingest_dx_trunk.py <map.dx> <trunk-dir> [--search DIR ...]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]      # Tools/uedcli (harness/ -> spike/ -> spikes/ -> docs/ -> dev/ -> root)
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"))

from spike_classindex import class_index  # noqa: E402  (schema-aware mover gate's index)
from uedcli import trunk as trunk_mod                     # noqa: E402
from uedcli.container_assets import resource_mounts      # noqa: E402
from uedcli.movers import canonicalize_mover             # noqa: E402
from uedcli.store_export import export_dx_level          # noqa: E402
from uedcli.stub import ephemeral_build_container        # noqa: E402
from uedcli.utexture import load_package                 # noqa: E402


def texture_package_index(dx_path: str) -> dict[str, str]:
    """bare texture name (casefolded) -> owning package name, from the .dx import table."""
    pkg = load_package(dx_path)

    def root_package(idx: int) -> str | None:
        # idx is an import ref (negative object-ref encoded as row already resolved here)
        cur = idx
        for _ in range(64):
            cp, cn, pkgi, on = pkg.imports[cur]
            if pkgi == 0:
                return pkg.names[on]
            if pkgi < 0:
                cur = -pkgi - 1
            else:
                return None
        return None

    index: dict[str, str] = {}
    for j, (cp, cn, pkgi, on) in enumerate(pkg.imports):
        if pkg.names[cn] != "Texture":
            continue
        name = pkg.names[on]
        owner = root_package(j) if pkgi != 0 else None
        if owner is None:
            continue
        key = name.casefold()
        if key in index and index[key] != owner:
            print(f"WARNING: texture {name!r} imported from BOTH {index[key]} and {owner}; "
                  f"keeping {index[key]}", file=sys.stderr)
            continue
        index.setdefault(key, owner)
    return index


def qualify_level_textures(level, index: dict[str, str]) -> tuple[int, int]:
    """Qualify every bare poly Texture= from the import-table index. Returns (hit, miss)."""
    hit = miss = 0
    for actor in level.actors.values():
        if actor.brush is None:
            continue
        for poly in actor.brush.polys:
            if not poly.texture or "." in poly.texture:
                continue
            owner = index.get(poly.texture.casefold())
            if owner is None:
                miss += 1
                continue
            poly.texture = f"{owner}.{poly.texture}"
            hit += 1
    return hit, miss


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("dx", help="the map file to ingest (.dx/.unr)")
    ap.add_argument("trunk", help="output trunk dir (created; refuses to overwrite a non-empty one)")
    ap.add_argument("--search", action="append", default=[],
                    help="package dir mounted for UCC demand-load (repeatable; e.g. the game's "
                         "System and Textures dirs)")
    args = ap.parse_args()

    dx = Path(args.dx).resolve()
    out = Path(args.trunk).resolve()
    if out.exists() and any(out.iterdir()):
        print(f"refusing to overwrite non-empty {out}", file=sys.stderr)
        return 2

    search = [str(Path(d).resolve()) for d in args.search]
    mounts = resource_mounts(search)
    from uedcli import xfer
    # `ephemeral_build_container` now takes a `state_dir` (project `.uedcli/`, direction/projects-and-config.md
    # 2026-07-17 20:58) instead of the old `repo_root`; for an offline scratch ingest any
    # writable dir suffices (it only hosts the crafted-ini temp), so use the trunk's own scratch.
    state_dir = out.parent.parent / ".uedcli"
    state_dir.mkdir(parents=True, exist_ok=True)
    with ephemeral_build_container(state_dir=state_dir, mounts=mounts) as container:
        c_dx = xfer.cp_in(container, str(dx), ext="dx")
        level = export_dx_level(container, c_dx)

    # `movers.is_mover` is schema-aware since 2026-07-25 (direction/conventions.md 2026-07-25 10:18 UTC): the
    # mover canonicalization gate resolves the class hierarchy against `Engine.Mover`, so it needs a
    # ClassIndex over the game's `.u` packages (project + ~/.uedcli/config.toml). `class_index()`
    # raises naming what is missing rather than letting the harness mis-ingest movers silently.
    idx = class_index()
    for actor in level.actors.values():
        canonicalize_mover(actor, idx)
    hit, miss = qualify_level_textures(level, texture_package_index(str(dx)))
    print(f"qualified {hit} texture ref(s), {miss} miss(es); "
          f"{len(level.actors)} actors, {len(level.order)} in order")

    ranks = {n: f"a{i:06d}" for i, n in enumerate(level.order)}
    out.mkdir(parents=True, exist_ok=True)
    trunk_mod.write_level(out, level, ranks)
    print(f"wrote trunk {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

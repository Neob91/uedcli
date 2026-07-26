#!/usr/bin/env python3
"""export_map.py — one-time `.dx` → T3D trunk export (the interim route until `level import` lands).

Drives an ephemeral no-GUI editor container to UCC-`batchexport` a retail `.dx` map into T3D, then
writes it as a uedcli trunk so the offline read/preview verbs (`actor find`, `actor preview`,
`--within-bbox`) can work on real level geometry — the corpus brush-idiom study's input.

    export_map.py <host.dx> <out-level-dir>
      <out-level-dir> is the trunk dir to create, e.g.  $PROJ/maps/wanchai

Resolves the project from $UEDCLI_PROJECT and the game paths from ~/.uedcli/config.toml, exactly like
the CLI's `texture sync` container path. Reuses `config.composed_search_dirs` → `resource_mounts` →
`ephemeral_build_container` → `xfer.cp_in` → `store_export.export_dx_t3d`.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parents[4]
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

from uedcli import config, container_assets, store_export, trunk, xfer   # noqa: E402
from uedcli.model import parse_t3d                                       # noqa: E402
from uedcli.stub import ephemeral_build_container                        # noqa: E402


def export_to_trunk(host_dx: str, out_level_dir: str) -> int:
    proj_env = os.environ.get("UEDCLI_PROJECT")
    if not proj_env:
        print("set UEDCLI_PROJECT to a dir containing uedcli.toml", file=sys.stderr)
        return 2
    project = config.load_project(proj_env)
    user_config = config.load_user_config()
    if user_config is None:
        print("no ~/.uedcli/config.toml with [games.<name>] paths", file=sys.stderr)
        return 2

    search_dirs = config.composed_search_dirs(project, user_config)
    mounts = container_assets.resource_mounts(search_dirs)
    state_dir = config.state_dir(project.root, create=True)

    host_dx = os.path.abspath(host_dx)
    print(f"[export] {host_dx}", file=sys.stderr)
    with ephemeral_build_container(mounts=mounts, state_dir=state_dir) as container:
        work_dx = xfer.cp_in(container, host_dx, ext="dx")
        print(f"[export] container={container} work={work_dx}; running batchexport…", file=sys.stderr)
        t3d = store_export.export_dx_t3d(container, work_dx)
    level = parse_t3d(t3d)
    n = len(level.actors)
    ranks = dict(zip(level.order or list(level.actors), trunk.initial_ranks(n) or []))
    out = Path(out_level_dir)
    out.mkdir(parents=True, exist_ok=True)
    trunk.write_level(out, level, ranks)
    brushes = sum(1 for a in level.actors.values() if a.brush is not None)
    print(f"[export] wrote {n} actors ({brushes} brushes) -> {out}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(export_to_trunk(sys.argv[1], sys.argv[2]))

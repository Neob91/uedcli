#!/usr/bin/env python3
"""Write the probe matrix as a git-trunk under a scratch project, ready for
`build_ued_import_built_golden.py --trunk`.

Layout: <out>/uedcli.toml, <out>/maps/basestamp/actors/<name>/{actor.t3d, order_value}.
Each probe actor gets a UNIQUE Location and NO authored Base / NO authored Physics.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path("/workspace/uedcli/.claude/worktrees/native-parity-incremental")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from uedcli import t3dtree                          # noqa: E402
from uedcli.model import Actor, Brush, Level, Polygon  # noqa: E402

from probe_classes import MOVER_PROBE, PROBES        # noqa: E402


def _cube_brush() -> Brush:
    """A 2-face builder-style cube brush so a mover imports with a real model."""
    faces = [
        ((0.0, 0.0, 64.0), (0.0, 0.0, 1.0),
         [(-64.0, -64.0, 64.0), (-64.0, 64.0, 64.0), (64.0, 64.0, 64.0), (64.0, -64.0, 64.0)]),
        ((0.0, 0.0, -64.0), (0.0, 0.0, -1.0),
         [(64.0, -64.0, -64.0), (64.0, 64.0, -64.0), (-64.0, 64.0, -64.0), (-64.0, -64.0, -64.0)]),
    ]
    return Brush(model_name="Brush",
                 polys=[Polygon(origin=b, normal=n, texture_u=(1.0, 0.0, 0.0),
                                texture_v=(0.0, 1.0, 0.0), vertices=v) for b, n, v in faces])


def build_level(include_mover: bool) -> Level:
    actors: dict[str, Actor] = {}
    order: list[str] = []
    # LevelInfo first.
    actors["LevelInfo0"] = Actor(name="LevelInfo0", cls="Engine.LevelInfo", props=[])
    order.append("LevelInfo0")
    specs = list(PROBES) + ([MOVER_PROBE] if include_mover else [])
    for i, (name, cls, _note) in enumerate(specs):
        loc = (float(256 * (i + 1)), 0.0, 128.0)
        if name == MOVER_PROBE[0]:
            actors[name] = Actor(name=name, cls=cls, location=loc,
                                 props=[("Brush", "Model'MyLevel.Brush'")], brush=_cube_brush())
        else:
            actors[name] = Actor(name=name, cls=cls, location=loc, props=[])
        order.append(name)
    return Level(actors=actors, order=order)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True, help="scratch project root")
    ap.add_argument("--no-mover", action="store_true")
    args = ap.parse_args()

    out = Path(args.out).resolve()
    level_dir = out / "maps" / "basestamp"
    level_dir.mkdir(parents=True, exist_ok=True)
    (out / "uedcli.toml").write_text('game = "deusex"\nmaps = "maps"\n')

    level = build_level(include_mover=not args.no_mover)
    ranks = dict(zip(level.order, t3dtree.initial_ranks(len(level.order))))
    t3dtree.write_actor_tree(level_dir, level, ranks)
    print(f"wrote {len(level.actors)} actors to {level_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

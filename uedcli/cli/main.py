"""uedcli CLI — the LLM-facing verb surface. Query and mutate verbs operate
model-side on $UEDCLI_LEVEL's git-native T3D trunk (`maps/<level>/`); the
editor is reached only via a per-command ephemeral spin-up (materialize /
photo / the stash CSG generators). The project's OWN git is the history —
uedcli reads it but never runs git for you, so history/recovery exist only once
the project is its own repo (`level status` reports when it is not).
"""
from __future__ import annotations

import argparse
import sys

from .parsers import (
    actor,
    brush,
    cache,
    classes,
    docs,
    event,
    level,
    mover,
    music,
    prefab,
    project,
    sound,
    stash,
    substrate,
    texture,
    uscript,
)
from .parsers._arguments import _CoordArgumentParser


def build_parser() -> argparse.ArgumentParser:
    p = _CoordArgumentParser(prog="uedcli", description=__doc__)
    p.add_argument("--project", default=None,
                   help="project root (or its uedcli.toml); else $UEDCLI_PROJECT, else the nearest "
                        "ancestor dir containing an uedcli.toml walking up from the cwd")
    sub = p.add_subparsers(dest="cmd", required=True)

    actor.register(sub)
    brush.register(sub)
    mover.register(sub)
    level.register(sub)
    event.register(sub)
    project.register(sub)
    classes.register(sub)
    sound.register(sub)
    music.register(sub)
    stash.register(sub)
    prefab.register(sub)
    docs.register(sub)
    texture.register(sub)
    substrate.register(sub)
    cache.register(sub)
    uscript.register(sub)

    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    from .dispatch import dispatch
    return dispatch(args)


if __name__ == "__main__":
    sys.exit(main())

"""Shared corpus/environment plumbing for this spike's three measurement scripts.

The measured content is a set of REAL shipped Deus Ex levels already extracted to uedcli trunks by
earlier campaign work. They live under `_scratch/` (gitignored, wiped on demand), so every script
here takes the corpus root as an argument and every script's RESULT is committed next to it as
JSON — the numbers stay reproducible-by-inspection even once the inputs are gone.

Class defaults / mover resolution come from the GIT-TRACKED `uned/UED22/*.u` corpus, so that half
needs no gitignored input at all.

Run from the repo root:  .venv/bin/python dev/docs/spikes/<slug>/harness/<script>.py ...
"""
from __future__ import annotations

import glob
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]   # harness/ slug/ spikes/ docs/ dev/ <repo>/
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

UED22 = REPO / "uned" / "UED22"

# Where the earlier `geo-confirm-*` campaign left real shipped-DX level trunks. Gitignored.
DEFAULT_CORPUS = Path("/workspace/uedcli/_scratch")


def ued22_index():
    from uedcli.classindex import ClassIndex
    files = [(os.path.splitext(os.path.basename(f))[0], f) for f in glob.glob(str(UED22 / "*.u"))]
    return ClassIndex.from_files(files)


def ued22_defaults():
    from uedcli.classdefaults import ClassDefaults

    def resolve(name: str) -> str | None:
        p = UED22 / f"{name}.u"
        return str(p) if p.is_file() else None

    return ClassDefaults(resolve)


# A second extraction of a map already in the corpus under another name, dropped so it does not
# count twice: `_scratch/geo-confirm-wanchaimkt-wk/maps/wanchaimkt-q` is the same WanChai Market map
# as `_scratch/proj/maps/wanchai` (same 2288 actors, both with qualified class names).
DUPLICATE_LEVELS = {"wanchaimkt-q"}


def find_levels(corpus: Path) -> list[tuple[str, Path]]:
    """Every `<proj>/maps/<level>/` trunk dir under `corpus`, sorted by actor count descending, with
    duplicate level names dropped (some projects carry a `-q` variant of the same map)."""
    out = []
    for actors_dir in sorted(corpus.glob("*/maps/*/actors")):
        level_dir = actors_dir.parent
        out.append((level_dir.name, level_dir, len(list(actors_dir.iterdir()))))
    out.sort(key=lambda t: -t[2])
    seen, uniq = set(DUPLICATE_LEVELS), []
    for name, path, _n in out:
        if name in seen:
            continue
        seen.add(name)
        uniq.append((name, path))
    return uniq


def game_of(name: str) -> str:
    """Which shipped game a corpus level came from. The `showcase_*` trunks are original-Unreal
    maps, the rest are Deus Ex — both are UE1, and `uedcli` targets UE1 generally, so results are
    reported per game rather than one being discarded."""
    return "unreal" if name.startswith("showcase_") else "deusex"


def load_level(level_dir: Path):
    from uedcli.trunk import read_level
    level, _ = read_level(level_dir)
    return level

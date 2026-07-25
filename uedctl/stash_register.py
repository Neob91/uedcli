"""Filesystem stash register — the git-native home for the stash register, under the project's
self-ignoring state dir `<root>/.uedctl/stash/` (decisions 2026-07-05 14:58, relocated by the
2026-07-17 20:58 project-layout reorg). Since the unify-T3D-trees change (decisions 2026-07-18
23:01 UTC) a stash entry is the SAME per-actor T3D tree as the trunk and a prefab:
`<id>/{actors/<name>/{actor.t3d, order_value[, folder]}, packages, meta.json}` — read/written through
the ONE shared `t3dtree` code path (`stashlib.write_tree_box`/`read_tree_box`).
`dispatch._dispatch_stash` drives it via `write_stash`/`read_stash`/`list_stashes`/`drop_stash`.

An unknown id reads back as empties (never raises), a drop of an unknown id is a no-op, and `list`
reports only real stash dirs (keyed on `meta.json`). Stash is machine-local throwaway, so an old
FLAT-format entry (loose `actors/<name>.t3d` files + a shared `order` file) is treated as ABSENT and
simply regenerated — there is no stash migration path.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from . import stashlib
from .stashlib import validate_member_name


def _is_stale_flat_stash(dest: Path) -> bool:
    """True when `dest` is an OLD flat-format stash (its `actors/` holds loose `*.t3d` FILES rather
    than per-actor sub-DIRS). `t3dtree.read_actor_tree` only iterates sub-dirs, so it would otherwise
    return an empty Level while `meta.json`/`packages` still read non-empty — an inconsistent
    half-empty result. Treat such an entry as fully absent (it is throwaway and gets regenerated)."""
    adir = Path(dest) / "actors"
    if not adir.is_dir():
        return False
    return any(p.is_file() and p.suffix == ".t3d" for p in adir.iterdir())


class FileStashRegister:
    def __init__(self, root: Path):
        self.root = Path(root)

    def write_stash(self, stash_id: str, *, full_level: dict[str, str], order: list[str],
                    packages: list[str], meta: dict, folders: dict[str, str | None] | None = None,
                    force: bool = False) -> str:
        """Store a stash entry as a per-actor T3D tree `<root>/<id>/` (via `stashlib.write_tree_box`:
        per-actor `actors/<name>/…` + sibling `packages`/`meta.json`, ranks preserved across rewrites,
        atomic staging swap). Refuses an existing id without `force`. `folders` (name→folder|None)
        gives each member its own `folder` sidecar (full trunk parity)."""
        validate_member_name(stash_id)
        stashlib.write_tree_box(self.root / stash_id, full_level=full_level, order=order,
                                packages=packages, meta=meta, folders=folders, force=force)
        return stash_id

    def read_stash(self, stash_id: str
                   ) -> tuple[dict[str, str], list[str], list[str], dict, dict[str, str | None]]:
        """(actors{name:t3d}, order, packages, meta, folders). Unknown id OR a stale flat-format
        entry → all-empty (mirrors the store); never raises for a missing id."""
        dest = self.root / stash_id
        if not dest.is_dir() or _is_stale_flat_stash(dest):
            return {}, [], [], {}, {}
        return stashlib.read_tree_box(dest)

    def exists(self, stash_id: str) -> bool:
        """Does this stash id exist? Keyed on its `meta.json` (same marker `list_stashes` uses),
        so it resolves NESTED ids directly AND stays true for a stash whose actors were all deleted
        (an empty-but-real stash) — unlike `read_stash(...)[0]` emptiness, which can't tell an emptied
        stash from a missing one now that `--tree` editing can delete a stash down to zero actors.
        A stale FLAT-format entry returns False (an honest `stash not found` → re-capture) so a
        `--tree stash/<stale>` edit can't silently touch zero actors while `meta.json` survives."""
        dest = self.root / stash_id
        return (dest / "meta.json").is_file() and not _is_stale_flat_stash(dest)

    def list_stashes(self) -> list[str]:
        # Only dirs carrying a `meta.json` are real stashes — this skips the `.staging` scratch dir
        # and any empty parent left behind after a nested-id drop, so `list` never reports a phantom.
        if not self.root.is_dir():
            return []
        return sorted(p.name for p in self.root.iterdir()
                      if p.is_dir() and (p / "meta.json").is_file())

    def drop_stash(self, stash_id: str) -> str:
        dest = self.root / stash_id
        if dest.is_dir():
            shutil.rmtree(dest)
        return stash_id

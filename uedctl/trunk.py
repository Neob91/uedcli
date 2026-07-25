"""Git-native T3D trunk: read/write a level as maps/<level>/actors/<name>/{actor.t3d, order_value}.

Thin, level-facing veneer over `t3dtree` — the ONE shared per-actor tree implementation used by the
trunk, the stash, and prefabs alike (decisions.md 2026-07-18 23:01 UTC — "stash, prefab, and trunk
MUST share ONE T3D tree format"). This module keeps the historical LEVEL names (`read_level`,
`write_level`, `read_level_with_bodies`, …) so a level's ~20 caller/test sites don't churn; the
actual code lives in `t3dtree` (which speaks tree-neutral `write_actor_tree`/`read_actor_tree`
because a stash/prefab is neither a "level" nor a "trunk").

The directory name is the single source of truth for an actor's identity: `actor.t3d` is stored with
its Name= header/trailer stripped and its brush model-ref neutralized to a constant, both re-derived
from the dir name on read. Order is a per-actor LexoRank `order_value` sidecar; the CSG order is the
(order_value, name) sort. See specs/2026-07-05-uedctl-git-native-model-design.md +
specs/2026-07-18-unify-t3d-trees.md + decisions.md 2026-07-05 / 2026-07-18. Pure module — no editor,
no session store; the primary read/write path for a level's trunk.
"""
from __future__ import annotations

from pathlib import Path

from .model import Level
from .t3dtree import (  # noqa: F401 — the shared per-actor tree, re-exported under level-facing names
    _SUFFIX_ALPHABET,
    _MODEL_CONST,
    alloc_name,
    append_rank,
    check_safe_segment,
    dump_actor_body,
    duplicate_ranks,
    initial_ranks,
    load_actor_body,
    rank_between,
    ranks_between,
    read_actor_tree as read_level_with_bodies,
    remove_actor,
    write_actor_tree as write_level,
)

# Kept as an alias for the handful of call sites that used the private name before the t3dtree split.
_check_safe_segment = check_safe_segment


def read_level(level_dir: Path) -> tuple[Level, dict[str, str]]:
    """Read the per-actor-dir trunk → (Level, name→order_value). `level.order` is the
    (order_value, name) sort. A missing/empty tree → an empty level."""
    level, ranks, _bodies, _folders = read_level_with_bodies(level_dir)
    return level, ranks

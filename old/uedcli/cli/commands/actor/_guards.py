"""The actor family's trunk-only surface guards, shared by `routes` and `edit`.

Not a feature module — it registers no subverb and the route matrix does not cover it, so both the
family route and a feature module may import it without the inward edge to `routes` that feature
isolation forbids.

Each guard rejects `--tree stash|prefab` for a surface only the per-actor trunk sidecar can hold.
`--tree level/NAME` (a named level's trunk) is always fine — these fire ONLY on stash/prefab. They
are called from two places: `routes._apply_source_free_guards`, BEFORE any source is resolved (so
the message is the right one and no box is loaded for a surface it cannot hold), and
`edit._ingest_actor_t3d`, where an incoming `// uedcli-folder:` / `// uedcli-labels:` CARRIER is the
same surface arriving by another route.
"""
from __future__ import annotations

from ...errors import CommandError


def reject_nonlevel_target_for_folders(args) -> None:
    """Folder surfaces are TRUNK-ONLY (spec §4): a folder lives only in the per-actor trunk sidecar,
    and the flat stash/prefab boxes serialize via `canonical_actor_t3d` (T3D only), with no
    per-actor sidecar slot. So every folder surface (`actor folder set/unset/get`, `actor add
    --folder`, `actor find --folder/--no-folder`, and a `// uedcli-folder:` carrier in ingested T3D)
    exits 2 rather than silently writing a sidecar the box save drops."""
    tgt = getattr(args, "tree", None)
    if tgt and tgt.partition("/")[0] in ("stash", "prefab"):
        raise CommandError("folders apply only to a level (not --tree stash|prefab)")


def reject_nonlevel_target_for_labels(args) -> None:
    """Label surfaces are TRUNK-ONLY this slice (plan scope-cut): labels live in the per-actor trunk
    `labels` sidecar and the stash/prefab box channel is deferred to the copy-between-trees spec. So
    every label surface (`actor label add/remove/clear/get`, `actor add --label`, `actor find
    --label/--no-label`, `actor duplicate`'s minted batch label, and a `// uedcli-labels:` carrier in
    ingested T3D) exits 2 rather than silently dropping a label on a box save."""
    tgt = getattr(args, "tree", None)
    if tgt and tgt.partition("/")[0] in ("stash", "prefab"):
        raise CommandError("labels apply only to a level (not --tree stash|prefab)")


def reject_nonlevel_target_for_order(args) -> None:
    """CSG ordering is TRUNK-ONLY (spec §7): the `order_value` sidecar the ordering verbs rewrite
    lives only in the per-actor trunk layout — stash/prefab boxes use a flat `order` list. So
    `actor order` and `actor add --order <non-last>` exit 2 rather than silently no-op'ing."""
    tgt = getattr(args, "tree", None)
    if tgt and tgt.partition("/")[0] in ("stash", "prefab"):
        raise CommandError("ordering applies only to a level (not --tree stash|prefab)")

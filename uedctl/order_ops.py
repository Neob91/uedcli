"""Pure model-side `order` maintenance (design D-F). With no editor in the edit loop, the
edit path maintains the full actor order itself: an `add` appends, a `delete` removes, and
move/set/clip/vertex-move leave order unchanged (they don't add/remove actors).

CSG-order control (`actor order` + `actor add --order`; spec 2026-07-18) reassigns/mints per-actor
`order_value`s (the LexoRank sidecar whose `(order_value, name)` sort IS the CSG precedence). Those
helpers live here — `compute_reorder_ranks` (move existing actors) and `compute_add_ranks` (place
new ones) — both minting K consecutive ranks in a target gap via `trunk.ranks_between`."""
from __future__ import annotations

from . import trunk


def order_after_add(order: list[str], name: str) -> list[str]:
    return order if name in order else [*order, name]


def order_after_delete(order: list[str], names: list[str]) -> list[str]:
    drop = set(names)
    return [n for n in order if n not in drop]


# --- CSG-order placement (LexoRank gap minting) ---

def _placement_gap(current_ranks: dict[str, str], selector: str, ref: str | None,
                   exclude: set[str]) -> tuple[str | None, str | None]:
    """The (lo, hi) rank boundaries of the target gap, with `exclude` filtered OUT of the neighbour
    lookup (spec §7 B2 — the predecessor/successor that bound the gap must NOT be an actor whose rank
    is simultaneously being reassigned). `None` = open end. Selectors: `first` (before the min),
    `last` (after the max), `before`/`after` NAME (adjacent to NAME's rank). Boundaries come from the
    non-excluded actors sorted by `(order_value, name)` — the CSG order itself."""
    remaining = sorted((r, n) for n, r in current_ranks.items() if n not in exclude)
    if selector == "first":
        return None, (remaining[0][0] if remaining else None)
    if selector == "last":
        return (remaining[-1][0] if remaining else None), None
    if selector in ("before", "after"):
        ref_rank = current_ranks[ref]
        idx = remaining.index((ref_rank, ref))       # ref is never excluded, so it is present
        if selector == "before":
            return (remaining[idx - 1][0] if idx > 0 else None), ref_rank
        return ref_rank, (remaining[idx + 1][0] if idx + 1 < len(remaining) else None)
    raise ValueError(f"unknown order selector: {selector!r}")     # internal guard (never user-facing)


def _mint(lo: str | None, hi: str | None, k: int) -> list[str]:
    """K ranks strictly between lo and hi. Raises `ValueError` (→ the caller's named exit-2) when no
    order_value can fit: either lo/hi are already equal-or-inverted (a pre-existing DUPLICATE rank
    bounds the gap) or `trunk.ranks_between` finds genuinely-adjacent imported ranks (e.g. `a`/`a0`,
    or `--first` against a smallest-digit min)."""
    if lo is not None and hi is not None and not lo < hi:
        raise ValueError(
            f"no order_value fits between {lo!r} and {hi!r} — the trunk has adjacent/duplicate ranks")
    return trunk.ranks_between(lo, hi, k)


def compute_reorder_ranks(current_ranks: dict[str, str], moved: list[str], selector: str,
                          ref: str | None) -> dict[str, str]:
    """New `order_value`s for the MOVED actors, placed as a block at the target position. Neighbour
    lookup EXCLUDES the moved set (§7 B2). The moved actors are sorted by their CURRENT
    `(order_value, name)` so their internal CSG order is preserved (block move) and given consecutive
    minted ranks in the gap. Raises `ValueError` on an unfillable gap (see `_mint`)."""
    moved_set = set(moved)
    lo, hi = _placement_gap(current_ranks, selector, ref, moved_set)
    ordered = sorted(moved, key=lambda n: (current_ranks[n], n))
    return dict(zip(ordered, _mint(lo, hi, len(ordered))))


def compute_add_ranks(current_ranks: dict[str, str], new_names: list[str], selector: str,
                      ref: str | None) -> dict[str, str]:
    """`order_value`s for NEW actors placed at the target position (`actor add --order`). The new
    names aren't in `current_ranks` yet, so nothing is excluded; they keep their EMIT order as a
    block. Raises `ValueError` on an unfillable gap (see `_mint`)."""
    lo, hi = _placement_gap(current_ranks, selector, ref, set())
    return dict(zip(new_names, _mint(lo, hi, len(new_names))))

"""ORDER-PRESERVING materialize (spec). Actor creation order = CSG precedence (brush
subsequence) + determinism, so we MUST NOT silently reorder.

Strategy = FULL RE-IMPORT (Task 20a spike, 2026-06-18): by-name CSG brush delete is NOT
reliable (a real CsgOper-carrying brush is not INSIDE-selectable, so the suffix-rebuild's
delete K..N can't run), so instead of deleting a suffix we `MAP NEW` and re-import the ENTIRE
merged level in canonical order — correct by construction, no by-name delete. Append-at-end
ordering holds (spike), so re-adding in canonical order reproduces the order. Cost = a
rebuild+relight per apply (loses baked lightmaps — an accepted non-concern: lightmaps/BSP are
regenerable build output, not authored state); the backup + step-5 post-verify keep it safe.

The pure planner (earliest_changed_actor / actor_suffix_plan) is retained for the
suffix-rebuild branch should by-name brush delete become reliable; it is unused on the live
full-re-import path. All-or-nothing: any failure restores the captured original level (D2
rollback widened to the batch) and re-raises."""
from __future__ import annotations

from dataclasses import dataclass


_ENGINE_LEVELINFO = "LevelInfo"       # the engine Actors[0] singleton class (short name)
_DEUSEX_LEVELINFO = "DeusExLevelInfo"  # a NORMAL gameplay actor (mission metadata), NOT Actors[0]


def _short_class(c: str | None) -> str | None:
    """Short class name from a bare OR qualified class (`Engine.LevelInfo` -> `LevelInfo`)."""
    return c.rsplit(".", 1)[-1] if c is not None else None


def _is_levelinfo_class(c: str | None) -> bool:
    """True ONLY for the engine `LevelInfo` singleton class (bare `LevelInfo` OR qualified
    `Engine.LevelInfo`) — the actor that occupies `ULevel.Actors[0]`.

    It deliberately does NOT match `DeusEx.DeusExLevelInfo`: although that is a subclass of
    `Engine.LevelInfo`, a shipped Deus Ex map places it as an ORDINARY actor at a non-zero
    Actors[] slot (verified against every `DX/Maps/*.dx`: Actors[0] is always plain `LevelInfo`
    and each map ALSO carries exactly one `DeusExLevelInfo` at some later slot — e.g.
    03_NYC_UNATCOHQ has `LevelInfo` at [0] and `DeusExLevelInfo` at [330]). So the Actors[0]
    hoist (`levelinfo_first_order`) must move ONLY the engine `LevelInfo`, leaving the
    `DeusExLevelInfo` in its authored point-actor slot.

    (History: the old form matched both classes on the assumption the DeusEx subclass REPLACED
    the singleton; the shipped maps disprove that — they coexist as two distinct actors.)"""
    return _short_class(c) == _ENGINE_LEVELINFO


def assert_at_most_one_levelinfo(actor_classes: dict[str, str]) -> None:
    """Guard the Actors[0] LevelInfo singleton invariant against a genuine duplicate, while
    ALLOWING the normal Deus Ex pairing of one engine `LevelInfo` + one `DeusExLevelInfo`.

    The merged MODEL may carry zero (from-scratch/empty trunk — MAP NEW / native assembly
    supplies the default) or one engine `LevelInfo`; TWO engine `LevelInfo`s is the bug (only the
    first would become Actors[0], the second would be silently dropped by the assembler's
    `is_level_info` filter). Independently, a DX map carries exactly one `DeusExLevelInfo` (a
    normal actor) — two of THOSE is also anomalous, so it is rejected too. One of each together is
    the correct, common case and passes. EXACTLY-one engine LevelInfo is an editor-side
    post-import fact (MAP NEW's default + the singleton rule), checked by apply's post-verify."""
    engine_lis = [n for n, c in actor_classes.items()
                  if _short_class(c) == _ENGINE_LEVELINFO]
    deusex_lis = [n for n, c in actor_classes.items()
                  if _short_class(c) == _DEUSEX_LEVELINFO]
    if len(engine_lis) > 1:
        raise ValueError(f"level model has at most one engine LevelInfo (Actors[0] singleton); "
                         f"found {len(engine_lis)}: {sorted(engine_lis)}")
    if len(deusex_lis) > 1:
        raise ValueError(f"level model has at most one DeusExLevelInfo; "
                         f"found {len(deusex_lis)}: {sorted(deusex_lis)}")


def levelinfo_first_order(order: list[str], actor_classes: dict[str, str],
                          has_brush: dict[str, bool]) -> list[str]:
    """Predict the order materialize's FULL RE-IMPORT actually produces: LevelInfo first
    (D-I), then every POINT actor (stable relative order), then every BRUSH (stable relative
    order). `writes._re_add` splits any re-add batch into ONE `MAP IMPORTADD` for all point
    actors followed by ONE `EDIT PASTE` for all brushes — so a brush listed BEFORE a point
    actor in the merged/authored order still lands AFTER every point actor in the live editor's
    resulting actor list (confirmed live 2026-06-21: a base-content map whose natural order
    interleaves a brush before two point actors re-exported with the point actors first after
    materialize). This doesn't violate "actor order = CSG precedence" (materialize.py's module
    docstring) — CSG precedence is a brush-to-brush ordering concern; point actors don't
    participate in CSG, so grouping them ahead of brushes changes nothing CSG cares about, only
    the literal recorded order. `_expected_level`'s canonical-hash comparison (which folds in
    `level.order`) needs this EXACT prediction, not just "LevelInfo first" — otherwise the FIRST
    materialize of any level whose authored order interleaves point actors and brushes
    spuriously fails H3 post-verify."""
    li = [n for n in order if _is_levelinfo_class(actor_classes.get(n))]
    li_set = set(li)
    rest = [n for n in order if n not in li_set]
    points = [n for n in rest if not has_brush.get(n, False)]
    brushes = [n for n in rest if has_brush.get(n, False)]
    return li + points + brushes


def earliest_changed_actor(current_order: list[str], merged_order: list[str]) -> int:
    """First index where the two orders diverge (== common-prefix length).
    Everything before it keeps its slot; from K on we rebuild the suffix."""
    k = 0
    for a, b in zip(current_order, merged_order):
        if a != b:
            break
        k += 1
    return k


@dataclass(frozen=True, kw_only=True)
class ActorSuffixPlan:
    first_changed: int
    delete: list[str]      # current actors K..N to delete
    readd: list[str]       # merged actors K..N to re-add, in canonical order


def actor_suffix_plan(*, current_order: list[str], merged_order: list[str]) -> ActorSuffixPlan:
    k = earliest_changed_actor(current_order, merged_order)
    return ActorSuffixPlan(first_changed=k, delete=current_order[k:], readd=merged_order[k:])


def materialize(*, driver, current_actors: dict, merged_actors: dict, current_order: list[str],
                merged_order: list[str], parse_actor, validate_brush, re_add, delete_named,
                rebuild, packages: list[str] | None = None, ensure_load=lambda pkgs: None) -> None:
    """Reach merged state from current via FULL RE-IMPORT, order-preserving + all-or-nothing.

    Injected callables keep this driver-agnostic and unit-testable; dispatch wires the
    writes.*/driver implementations:
      parse_actor(t3d) -> Actor; validate_brush(brush); re_add(actors); delete_named(names);
      rebuild(); ensure_load(packages) (default no-op — Task 14 wires the real ini-edit).

    Steps:
      1. `ensure_load(packages)` — make the manifest packages loadable BEFORE MAP NEW imports
         actors that reference them (D-I/Task 14).
      2. `MAP NEW` — reset to an empty level (no by-name brush delete needed).
      3. Re-add every merged actor in `levelinfo_first_order`'s predicted canonical order
         (D-I; `re_add` splits point actors → one `IMPORTADD` and brushes → one `PASTE`, each
         appending as a group — so the predicted order must ALSO group points before brushes,
         not just hoist LevelInfo, see `levelinfo_first_order`'s docstring). The model may
         carry at most one LevelInfo (assert) — MAP NEW's default is replaced
         name-independently by the imported one (LevelInfo update spike).
      4. On any failure, restore the captured ORIGINAL level (MAP NEW + re-add current in its
         own order) and re-raise — the batch is all-or-nothing.
      5. rebuild() once at the end.
    """
    parsed = {name: parse_actor(merged_actors[name]) for name in merged_order}
    actor_classes = {name: getattr(a, "cls", None) for name, a in parsed.items()}
    has_brush = {name: getattr(a, "brush", None) is not None for name, a in parsed.items()}
    assert_at_most_one_levelinfo(actor_classes)
    import_order = levelinfo_first_order(merged_order, actor_classes, has_brush)
    merged = [parsed[name] for name in import_order]
    for a in merged:
        if getattr(a, "brush", None) is not None:
            validate_brush(a.brush)
    ensure_load(packages or [])
    driver.map_new()
    try:
        re_add(merged)
    except Exception:
        # Roll the whole batch back to the original level (D2 widened to the batch).
        driver.map_new()
        re_add([parse_actor(current_actors[name]) for name in current_order])
        raise
    rebuild()

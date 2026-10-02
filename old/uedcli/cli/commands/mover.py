"""`mover key list|count|move|rotate|remove` — set a mover's keyframe count and edit its animation
keyframes. Pure, model-side (no editor; design D-F).

Resolves the trunk level source (honouring `--tree` / `$UEDCLI_LEVEL`), transforms the mover's
keyframe arrays in the in-memory model, and writes the trunk back — the same order the transitional
monolith used (the single source resolution before the sub-verb dispatch). This module uses
`cli.level_sources`/`cli.resources` and the model-side `movers`/`rotation`/`query` services; it never
imports another command family or the router.
"""
from __future__ import annotations

from decimal import Decimal

from .. import level_sources, resources
from ..errors import CommandError


def run(args):
    """Route one `mover` invocation. Resolves the trunk level source first (no project ⇒ clean exit
    2), then runs the requested sub-verb. Returns `None` for a sub argparse can't produce, so the
    dispatch fallback reports it."""
    src = level_sources.resolve_level_source(args)
    if args.sub == "key":
        return _key(args, src)
    return None


def _key(args, src) -> int:
    from ... import movers, query, rotation
    level = src.load()
    try:
        canonical = query.resolve_actor_name(level, args.name)
    except KeyError as e:
        raise CommandError(f"mover key {args.keysub}: {e.args[0]}")
    actor = level.actors[canonical]
    if not movers.is_mover(actor, resources.mover_index(args, f"mover key {args.keysub}")):
        raise CommandError(
            f"mover key {args.keysub}: {canonical} is not a Mover "
            f"(class {actor.cls or '(none)'} does not descend from {movers.MOVER_BASE})")

    if args.keysub == "list":
        if getattr(args, "json", False):
            import json
            print(json.dumps(query.list_mover_keys(actor), indent=2))
        else:
            print(query.format_mover_keys(actor))
        return 0

    if args.keysub == "count":
        if args.n is None:                       # getter: print the current count to stdout
            print(movers.num_keys(actor))
            return 0
        try:
            movers.set_num_keys(actor, args.n)   # shared bounded setter (== `actor prop set NumKeys=`)
        except ValueError as e:
            raise CommandError(str(e)) from None
        src.save(verb="mover-key-count",
                 args={"name": canonical, "num_keys": movers.num_keys(actor)},
                 level=level, touched=[canonical])
        return 0

    if args.keysub in ("move", "rotate"):
        # Frame / --by gating runs BEFORE the index guard (spec 2026-07-20). argparse already
        # forbids --from-base WITH --from-world and requires exactly one of --to/--by.
        from_base = getattr(args, "from_base", False)
        from_world = getattr(args, "from_world", False)
        if args.to is not None and not (from_base or from_world):
            raise CommandError(
                f"mover key {args.keysub}: --to needs a coordinate frame — "
                "choose --from-base (offset from the base pose) or --from-world (absolute world)")
        if args.by is not None and (from_base or from_world):
            raise CommandError(
                f"mover key {args.keysub}: --by is a frame-agnostic delta — "
                "drop --from-base/--from-world (they apply only to --to)")
        n = movers.num_keys(actor)
        if args.index == 0:
            verb = "actor move" if args.keysub == "move" else "actor rotate --by"
            raise CommandError(
                f"mover key {args.keysub}: key 0 is the base pose — use '{verb}' on the mover")
        if not (1 <= args.index < n):
            raise CommandError(
                f"mover key {args.keysub}: {canonical} has no key {args.index} "
                f"(keys 1..{n-1}) — raise the count first with 'mover key count {canonical} <n>'")
        if args.keysub == "move":
            cur = movers.key_pos(actor, args.index)
            if args.to is not None:
                if from_base:
                    new = tuple(args.to)                 # offset written straight into KeyPos
                else:                                    # --from-world: subtract the base pose
                    base = actor.location or (Decimal(0), Decimal(0), Decimal(0))
                    new = tuple(args.to[j] - base[j] for j in range(3))
            else:
                new = tuple(cur[j] + args.by[j] for j in range(3))
            movers.set_key_pos(actor, args.index, new)
            rec = {"name": canonical, "index": args.index,
                   "key_pos": movers.emit_or_none_pos(actor, args.index)}
        else:  # rotate
            cur_uu = movers.key_rot(actor, args.index)
            delta_uu = tuple(rotation.uu_field(c) for c in (args.to or args.by))
            if args.to is not None:
                if from_base:
                    new_uu = delta_uu                    # offset UU written straight into KeyRot
                else:                                    # --from-world: FRotator field-subtract base
                    base_uu = rotation.actor_rotation_uu(actor)
                    new_uu = rotation.subtract_uu(delta_uu, base_uu)
            else:
                new_uu = rotation.compose_uu(cur_uu, delta_uu)
            movers.set_key_rot(actor, args.index, new_uu)
            rec = {"name": canonical, "index": args.index,
                   "key_rot": movers.emit_or_none_rot(actor, args.index)}
        src.save(verb=f"mover-key-{args.keysub}", args=rec,
                        level=level, touched=[canonical])
        return 0

    if args.keysub == "remove":
        n = movers.num_keys(actor)
        if args.index == 0:
            raise CommandError("mover key remove: key 0 is the base pose — delete the actor "
                                 "with 'actor delete' to remove the whole mover")
        if not (1 <= args.index < n):
            raise CommandError(
                f"mover key remove: {canonical} has no key {args.index} (keys 1..{n-1})")
        if n - 1 < movers.MIN_KEYS:
            raise CommandError(
                f"mover key remove: a mover needs at least {movers.MIN_KEYS} keys")
        movers.remove_key(actor, args.index)
        src.save(verb="mover-key-remove",
                        args={"name": canonical, "index": args.index},
                        level=level, touched=[canonical])
        return 0

    raise CommandError(f"mover key: unimplemented sub-verb: {args.keysub}")

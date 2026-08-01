"""`actor prop get|set|unset` — schema-validated actor property edits. Pure, model-side (no editor).

Resolves the trunk level source (honouring `--tree` / `$UEDCLI_LEVEL`), then reads/writes. `-` in
the name position reads a name list from stdin (multi-actor mode). The grammar/planner/effective-value
logic lives in `propedit`; the class schema/defaults resolve lazily through `cli.resources` (the
seams tests mock). This module uses `cli.level_sources`/`cli.resources`/`cli.targets`; it never
imports another command family or the router.
"""
from __future__ import annotations

import sys

from ... import level_sources, resources
from ... import targets as target_names
from .... import propedit, query
from ....uprops import SchemaError


def run(args) -> int:
    """`actor prop get|set|unset`. `-` in the name position reads a newline name list from stdin →
    multi-actor mode; the SAME tokens apply to every piped actor. Piped actors may be DIFFERENT
    classes, so the class schema/defaults resolve per-actor. Single (non-`-`) name keeps today's
    behaviour exactly (singular "Actor not found:" message, bare `get` output, `{"name": …}`
    record)."""
    src = level_sources.resolve_level_source(args)
    piped = (args.name == "-")
    raw = target_names.resolve_target_names([args.name])
    if not raw:
        return 0                                      # empty stdin: no-op, exit 0
    level = src.load()
    try:
        if piped:
            # Dedupe on CANONICAL names (spec §8): a repeated piped name is the same actor;
            # applying the edit twice would double-apply (or double-print for `get`).
            names = list(dict.fromkeys(query.resolve_actor_names(level, raw)))
        else:
            names = [query.resolve_actor_name(level, raw[0])]
    except KeyError as e:
        print(e.args[0], file=sys.stderr)
        return 2
    actors = [level.actors[n] for n in names]
    # The class schema/defaults resolve LAZILY inside each ClassCtx (only when a token needs
    # them) — hard-rejects and typed-field-only invocations never require the v68 install
    # (spec §2.4). The four seams (resources.class_schema/resources.class_defaults/resources.struct_members/
    # resources.enum_names) are what tests mock.
    try:
        if args.propsub == "get":
            toks = [propedit.parse_token(t, expect_value=False) for t in args.tokens]
            want_json = getattr(args, "json", False)
            # JSON always renders the KV-form (KEY=VALUE) lines so each splits into a
            # (key, value) pair; the KEY (a prop name/dot-path) never contains `=`, so the
            # value keeps any embedded `=` (a struct like `(Pitch=0,…)`). Build EVERY actor's
            # lines first, then print — a bad token/class on a later actor leaves the whole
            # dump un-emitted (atomic), and `get` never partial-prints.
            kv = args.kv or piped or want_json
            per_actor: list[tuple[str, list[str]]] = []
            for actor, name in zip(actors, names):
                ctx = resources.class_ctx(actor.cls, args)
                if toks:
                    # Piped multi-actor output is name-prefixed KV (`<name>\t<key>=<value>`) so
                    # a dump over several keys stays parseable (spec §8); a single CLI name
                    # keeps today's bare (or `--kv`) output.
                    lines = propedit.get_lines(actor, toks, ctx, propedit.TYPED_FIELDS, kv=kv)
                else:                            # dump-all: the stored view (spec §2.3)
                    lines = propedit.dump_all_lines(actor, ctx, propedit.TYPED_FIELDS)
                per_actor.append((name, lines))
            if want_json:
                import json

                def _kv_obj(lines):
                    obj: dict[str, str] = {}
                    for ln in lines:
                        k, _, v = ln.partition("=")
                        obj[k] = v
                    return obj
                # Piped read (`-`): {name: {key: value}}; a single named actor: flat {key: value}.
                if piped:
                    print(json.dumps({name: _kv_obj(lines) for name, lines in per_actor},
                                     indent=2))
                else:
                    print(json.dumps(_kv_obj(per_actor[0][1]) if per_actor else {}, indent=2))
                return 0
            out_lines: list[str] = []
            for name, lines in per_actor:
                out_lines.extend(f"{name}\t{ln}" if piped else ln for ln in lines)
            for ln in out_lines:
                print(ln)
            return 0
        mode = args.propsub                      # "set" | "unset"
        toks = [propedit.parse_token(t, expect_value=(mode == "set"))
                for t in args.tokens]
        # TWO-PHASE (spec §8): plan EVERY actor before mutating ANY, so a bad token leaves ALL
        # actors untouched (validate-before-mutate across the whole piped set, cross-class).
        plans = [propedit.plan_edit(actor, toks, mode, resources.class_ctx(actor.cls, args),
                                    propedit.TYPED_FIELDS)
                 for actor in actors]
    except propedit.PropEditError as e:
        print(str(e), file=sys.stderr)
        return 2
    except SchemaError as e:
        print(str(e), file=sys.stderr)
        return 2
    for actor, plan in zip(actors, plans):
        for w in plan.warnings:
            print(f"warning: {w}", file=sys.stderr)
        actor.props = plan.props
        for attr, val in plan.typed_updates.items():
            setattr(actor, attr, val)
    # Single (non-`-`) name keeps the `{"name": …}` record shape (tests + callers depend on it);
    # multi-actor records `{"names": […]}`.
    rec = {"names": names} if piped else {"name": names[0]}
    rec.update(propsub=args.propsub, tokens=list(args.tokens))
    src.save(verb="prop", args=rec, level=level, touched=names)
    for name in names:                               # PRODUCER: touched names → stdout (feed `| verb -`)
        print(name)
    print(f"{mode} on {len(names)} actor(s)", file=sys.stderr)
    return 0

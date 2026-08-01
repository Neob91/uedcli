"""Actor read/query verbs: `find`, `show`, `bbox`. Pure, model-side (no editor).

Each verb resolves the trunk level source (honouring `--tree` / `$UEDCLI_LEVEL`), then reads. The
source is resolved before the empty-stdin no-op, matching the pre-move dispatch order. This module
uses `cli.level_sources`/`cli.resources`/`cli.targets` and the model-side `query` service; it never
imports another command family or the router.
"""
from __future__ import annotations

import sys

from ... import level_sources, resources
from ... import targets as target_names
from ...errors import CommandError
from .... import emit, folderlib, labellib, propedit, query, writes
from ....classindex import ClassRefError
from ....uprops import SchemaError


def run(args) -> int:
    """Route one actor query verb. Resolves the trunk level source first (no project ⇒ clean exit 2),
    then runs the requested subverb."""
    src = level_sources.resolve_level_source(args)
    if args.sub == "find":
        return _find(args, src)
    if args.sub == "show":
        return _show(args, src)
    if args.sub == "bbox":
        return _bbox(args, src)
    raise CommandError(f"unimplemented actor query sub-verb: {args.sub}")


def _find(args, src) -> int:
    """`actor find` — deterministic query over the concrete T3D tree, printing an exact name set to
    stdout (one/line, or `--json`). Filters (class/group/folder/label/prop/spatial) AND together;
    `-` (composable find) makes a piped name-set the universe and `--exclude` negates the match."""
    find_folders = getattr(args, "folder", None) or []
    find_no_folder = getattr(args, "no_folder", False)
    for pat in find_folders:                          # globstar grammar-check → exit 2 (spec §3)
        try:
            folderlib.validate_pattern(pat)
        except ValueError as e:
            raise CommandError(str(e))
    find_labels = getattr(args, "label", None) or []
    find_no_label = getattr(args, "no_label", False)
    for pat in find_labels:                           # flat `*`-only grammar-check → exit 2 (spec §5)
        try:
            labellib.match_label(pat, "")             # reject `?`/`[`/`]`; the match result is discarded
        except ValueError as e:
            raise CommandError(str(e))
    level = src.load()
    if getattr(args, "exclude", False) and getattr(args, "restrict", None) != "-":
        raise CommandError("--exclude requires - (a piped name-set to exclude from)")
    if getattr(args, "restrict", None) not in (None, "-"):
        raise CommandError(f"find takes no positional name; use --name (got {args.restrict!r})")
    class_filter = _find_class_filter(args, level)    # --exact-class ∪ --subclass-of expansion
    names = query.list_actors(
        level,
        names=args.name or None,
        classes=class_filter,
        groups=args.group or None,
        folders=find_folders or None,
        no_folder=find_no_folder,
        labels=find_labels or None,
        no_label=find_no_label,
        kind=args.kind,
    )
    if args.prop:
        # EFFECTIVE-value matching (spec §7, ruling R3): each --prop token matches what
        # `actor prop get` would print — stored value, else class default, else zero —
        # compared type-aware. A key not declared on a GIVEN actor's class is a per-actor
        # no-match; a key declared on NO considered class is a typo → exit 2; an
        # unbuildable class schema is a hard error (no-fallback). Plain `find` without
        # --prop never touches the schema.
        try:
            toks = [propedit.parse_token(t, expect_value=True) for t in args.prop]
        except propedit.PropEditError as e:
            print(str(e), file=sys.stderr)
            return 2
        ctxs: dict[str, propedit.ClassCtx] = {}
        declared: dict[str, bool] = {t.raw: False for t in toks}
        matched: list[str] = []
        try:
            for n in names:
                actor = level.actors[n]
                ctx = ctxs.setdefault(actor.cls.casefold(), resources.class_ctx(actor.cls, args))
                ok = True
                for t in toks:
                    r = propedit.effective_match(actor, t, ctx, propedit.TYPED_FIELDS)
                    if r is None:                # class doesn't declare the key
                        ok = False
                    else:
                        declared[t.raw] = True
                        ok = ok and r
                if ok:
                    matched.append(n)
            # Typo protection (ruling R3): a key declared on NO class → exit 2. Checked
            # over the considered actors' classes; with an EMPTY considered set, fall back
            # to every class in the level so `find --name zzz --prop Typoo=1` still flags
            # the typo (review finding — the guard used to be skipped entirely).
            undeclared = [t for t in toks if not declared[t.raw]]
            if undeclared and not names:
                for a in level.actors.values():
                    ctx = ctxs.setdefault(a.cls.casefold(), resources.class_ctx(a.cls, args))
                    for t in list(undeclared):
                        if t.base.casefold() in propedit.TYPED_FIELDS or \
                                ctx.schema().get(t.base.casefold()) is not None:
                            declared[t.raw] = True
                            undeclared.remove(t)
                    if not undeclared:
                        break
        except propedit.PropEditError as e:
            print(f"--prop: {e}", file=sys.stderr)
            return 2
        except SchemaError as e:
            print(str(e), file=sys.stderr)
            return 2
        if level.actors:                         # typo protection (empty level: nothing to say)
            for t in toks:
                if not declared[t.raw]:
                    print(f"--prop {t.raw}: no considered actor's class declares "
                          f"{t.base}", file=sys.stderr)
                    return 2
        names = matched
    # Spatial filter (spec 2026-07-24-find-spatial): `--within-bbox` keeps actors whose world AABB
    # is fully inside the given box. AABB predicate over `writes.actor_bounds` (full transform,
    # Decimal), in the handler AFTER list_actors — ANDs with the other filters, alongside --prop,
    # before the composable-find restrict. In-tree order preserved.
    bbox = getattr(args, "within_bbox", None)
    if bbox is not None:
        names = [n for n in names
                 if writes.aabb_within(writes.actor_bounds(level.actors[n]), bbox)]
    # Composable-find grep/universe model (spec 2026-07-24-composable-find): `-` makes the piped
    # name-set the universe; the filters above are the predicate; --exclude negates it. Applied to
    # the FINAL `names` (post --prop), in-tree order preserved.
    if getattr(args, "restrict", None) == "-":
        raw = target_names.resolve_target_names(["-"])
        try:
            universe = set(query.resolve_actor_names(level, raw))   # strict, all-or-nothing
        except KeyError as e:
            print(e.args[0], file=sys.stderr)
            return 2
        matched_set = set(names)
        keep = universe - matched_set if getattr(args, "exclude", False) else universe & matched_set
        names = [n for n in query.list_actors(level) if n in keep]
    if getattr(args, "json", False):
        import json
        print(json.dumps(names, indent=2))
    else:
        for n in names:
            print(n)
    return 0


def _show(args, src) -> int:
    """`actor show` — emit the canonical T3D block(s) for the named actor(s). The positional is a
    single actor name; `-` (a stdin name list) is the ONLY multi-actor mechanism (owner ruling
    2026-07-25 — `actor find` owns patterns). Each block carries `// uedcli-folder:`/`//
    uedcli-labels:` comments unless `--t3d-only`."""
    with_sidecars = not getattr(args, "t3d_only", False)
    if args.name == "-":
        raw = target_names.resolve_target_names([args.name])
        if not raw:
            return 0                                  # empty stdin: no-op, exit 0
        level = src.load()
        try:
            names = list(dict.fromkeys(query.resolve_actor_names(level, raw)))
        except KeyError as e:
            print(e.args[0], file=sys.stderr)
            return 2
        # Each block self-identifies via its `Name=`; concatenation is valid T3D (spec §3).
        print("\n".join(query.actor_show_block(level.actors[n], with_sidecars) for n in names))
        return 0
    level = src.load()                               # outside the guard, like the sibling verbs
    try:
        out = query.show_actor(level, args.name, with_sidecars=with_sidecars)
    except KeyError as e:                            # a name that matches no actor → exit 2
        print(e.args[0], file=sys.stderr)
        return 2
    print(out)
    return 0


def _find_class_filter(args, level) -> list[str] | None:
    """The class-name filter for `actor find`, combining the two class flags (decision 2026-07-19):
    the `--exact-class` bases (exact class match, as the old `--class` did), UNIONed with every class
    present in `level` that DESCENDS from a `--subclass-of` base (descendant-aware, expanded via the
    offline `ClassIndex` — `--subclass-of Engine.Light` also matches Spotlight). The two flags OR
    within the class dimension; `list_actors` ANDs the result with the other filters.

    Returns None when NEITHER class flag was given (no class filter → every class); a possibly-empty
    list when a class flag WAS given (an empty list matches no actor — the requested filter simply
    hit nothing). Only `--subclass-of` touches the schema/project; a plain or `--exact-class`-only
    find never does. Raises `CommandError` on an unknown `--subclass-of` base or a missing
    package path."""
    exact = list(getattr(args, "cls", None) or [])
    bases = list(getattr(args, "subclass_of", None) or [])
    if not exact and not bases:
        return None                                       # no class filter → match every class
    if not bases:
        return exact                                      # --exact-class only: identical to the old --class
    index = resources.class_index(resources.resolve_project(args))
    if index.empty:                                       # `empty` is a property, not a method
        raise CommandError("--subclass-of needs the game's .u packages, but none were found on "
                             "the project's package path")
    qbases: list[str] = []
    for b in bases:
        try:
            fq = b if "." in b else index._qualify_bare(b)
        except ClassRefError as e:
            raise CommandError(f"--subclass-of: {e}")
        if fq is None or not index.class_exists(fq):
            raise CommandError(f"--subclass-of: unknown class {b!r}")
        qbases.append(fq)
    matched = set(exact)
    for cls in {a.cls for a in level.actors.values()}:    # only the classes actually present, deduped
        try:
            fq_cls = cls if "." in cls else index._qualify_bare(cls)
        except ClassRefError:
            fq_cls = None                                 # an unknown stored class can't be a descendant
        if fq_cls and any(index.descends_from(fq_cls, qb) for qb in qbases):
            matched.add(cls)                              # add the class AS STORED (list_actors matches it)
    return sorted(matched)


def _bbox(args, src) -> int:
    """`actor bbox <names…|->` — world AABB enclosing the passed actors as ONE box (the multi-actor
    case IS the union — no --union flag). `-` reads a name list from stdin; empty stdin is a clean
    no-op."""
    raw = target_names.resolve_target_names(args.names)
    if not raw:
        return 0                                      # empty stdin: no-op, exit 0
    level = src.load()
    try:
        resolved = query.resolve_actor_names(level, raw)  # unknown name → clean exit 2 (below)
    except KeyError as e:
        print(e.args[0], file=sys.stderr)             # "Actors not found: <names>" — no traceback
        return 2
    names = list(dict.fromkeys(resolved))
    actors = [level.actors[n] for n in names]
    lo, hi, size, center = _bbox_of(actors)
    vecs = {"min": lo, "max": hi, "size": size, "center": center}
    if getattr(args, "field", None) is not None:
        v = vecs[args.field]
        print(",".join(emit.fmt_coord(c) for c in v))
    elif getattr(args, "json", False):
        import json
        print(json.dumps({k: {"x": emit.num_coord(v[0]), "y": emit.num_coord(v[1]),
                              "z": emit.num_coord(v[2])} for k, v in vecs.items()},
                         indent=2))
    else:
        for k in ("min", "max", "size", "center"):
            print(f"{k:<6} {','.join(emit.fmt_coord(c) for c in vecs[k])}")
    print(f"bbox of {len(actors)} actor(s)", file=sys.stderr)
    return 0


def _bbox_of(actors):
    """Compute the world AABB enclosing `actors` as Decimal (lo, hi, size, center). Reuses
    `writes.union_bounds` → `writes.actor_bounds`, which honours the full actor transform
    (`Location + PostScale·R·MainScale·(v − PrePivot)`, the same math as `rotation.world_vertices`)
    and treats a point actor as a zero-size box at its Location.

    Derived coordinates are TOLERANCE-SNAPPED for reporting (`emit.clean`, CLEAN_EPS = 0.001), the
    same rule the emitter applies to authored ones. UE1's GMath rotator table is not exact — a 180°
    yaw carries `sin = -8.742278e-08`, so a ±64 vertex offset leaks ~6e-06 into the cross axis and a
    brush sitting exactly on `Y=228` reports `227.999994`. That is noise ~170x below the weld grid
    (`doctor.WELD` = 1e-3) and it reads as "the rotate pushed my geometry off-grid" when the trunk is
    in fact exact. A genuine fraction — a 2.5-uu semisolid, an odd-span centre — is still preserved
    at 6-dp, because `clean` only snaps inside the tolerance band.

    The snap is confined to THIS reporting path on purpose: `writes.union_bounds` itself stays raw,
    because `doctor`, the CSG core and the preview cameras must decide on the real numbers. Cleaning
    a value that feeds a geometric decision would mask the faults those tolerances exist to catch.
    """
    lo, hi = writes.union_bounds(actors)
    lo = tuple(emit.clean(c) for c in lo)
    hi = tuple(emit.clean(c) for c in hi)
    size = tuple(emit.clean(hi[i] - lo[i]) for i in range(3))
    center = tuple(emit.clean((hi[i] + lo[i]) / 2) for i in range(3))
    return lo, hi, size, center

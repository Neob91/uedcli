"""`class list` / `class show` — offline class discovery over the composed `.u` path.

Module is `classes` because `class` is a Python keyword (the sole spelling exception in
`cli.commands`); the CLI verb is still `class`.
"""
from __future__ import annotations

import json
import sys

from ... import classindex, meshfacts, rotation, uprops
from ...classindex import ClassRefError
from .. import resources
from ..errors import CommandError

# `class show` (without --all) shows the class's own props + as many ancestor sections as fit in this
# many lines, then notes the rest — a deep chain (…→Engine.Actor→Core.Object) is ~200 props otherwise.
_SHOW_LINE_BUDGET = 60

_TREE_LINE_BUDGET = 60


def _class_tree(idx, *, subclass_of, include_non_actor, depth, package) -> list[str]:
    """The `class list` TREE (default rendering): the inheritance hierarchy under a root, indented,
    every class shown with abstract branch-points marked `*` and a frontier node's hidden direct
    subclasses shown inline as `(N)` (decision 2026-07-18). Root = `--subclass-of`, else `Core.Object`
    with `--include-non-actor`, else `Engine.Actor`. `--depth N` sets the depth (`--depth all` =
    `math.inf` = the whole tree, no `(N)` collapse); without it, the depth auto-grows while it fits the
    ~60-line budget (min 1 level). `--package P` prunes to P's classes + the ancestor branches needed to
    reach them. Direct subclasses at each level are listed in the name-sorted order `idx.subclasses()`
    returns (see `ClassIndex.children_map`)."""
    root = subclass_of or (classindex.CORE_OBJECT if include_non_actor else classindex.ENGINE_ACTOR)
    if not idx.class_exists(root):
        raise ClassRefError(f"unknown --subclass-of class: {root}" if subclass_of
                            else f"root class {root} not on the package path")
    package_cf = package.casefold() if package else None
    if package_cf is not None and package_cf not in idx._paths:
        raise ClassRefError(f"package not found on the path: {package}")

    pcache: dict[str, bool] = {}
    def has_pkg(fqcn):                               # keep a node iff it (or a descendant) is in P
        if package_cf is None:
            return True
        k = fqcn.casefold()
        if k not in pcache:
            pcache[k] = False                        # provisional: a re-entrant hit (pathological
            pcache[k] = (fqcn.split(".", 1)[0].casefold() == package_cf   # inheritance cycle) reads
                         or any(has_pkg(c) for c in idx.subclasses(fqcn)))  # as "not in P", so a
        return pcache[k]                             # cycle can't keep an out-of-package subtree in

    def kids(fqcn):
        return [c for c in idx.subclasses(fqcn) if has_pkg(c)]

    def render(maxd):
        out: list[str] = []
        def walk(fqcn, d, indent, seen):
            mark = " *" if idx.is_abstract(fqcn) else ""
            ks = kids(fqcn)
            if (d >= maxd or fqcn.casefold() in seen) and ks:
                out.append(f"{indent}{fqcn}{mark} ({len(ks)})")
            else:
                out.append(f"{indent}{fqcn}{mark}")
                for c in ks:
                    walk(c, d + 1, indent + "  ", seen | {fqcn.casefold()})
        walk(root, 0, "", frozenset())
        return out

    if depth is not None:
        eff = max(0, depth)
    else:
        eff = 1
        cur = render(eff)
        while eff < 30:
            nxt = render(eff + 1)
            if len(nxt) > _TREE_LINE_BUDGET or nxt == cur:   # over budget, or growth converged
                break
            eff, cur = eff + 1, nxt
        return cur
    return render(eff)


# ── `class show` FACTS block (asset-catalog class arm C1) ────────────────────────────────────────
# `class show` reports a class's file-facts: DrawType, the default Mesh, its signed mesh-local
# extents, collision cylinder, PrePivot, and parent. Everything but the extents comes straight from
# the resolved class defaults; the extents come from decoding the default Mesh (see `meshfacts`).
# These are FACTS read from the package — the tool infers nothing (`direction/asset-catalog.md`).


def _num(text: str | None) -> float:
    """A class default's numeric text (`"56.5"`, `"22"`) → float; an absent default is the type's
    zero (a class with no CollisionRadius default effectively has 0)."""
    return float(text) if text else 0.0


def _fvec(text: str | None) -> list[float]:
    """A struct default like `(X=0,Y=0,Z=0)` → `[x, y, z]` floats; an absent default → zeros."""
    if not text:
        return [0.0, 0.0, 0.0]
    return [float(v) for v in rotation.parse_fvector(text)]


def _json_num(v: float):
    """A number JSON-rendered as an int when integral (`56.0` → `56`), else the float (`56.5`)."""
    return int(v) if float(v).is_integer() else v


def _build_facts(fqcn: str, idx, project) -> dict:
    """The class's file-facts for `class show`. `drawtype`/`mesh`/`collision`/`prepivot` come from the
    resolved class defaults; `extents` is the default Mesh's signed mesh-local bounding box (`Scale`
    applied, pre-Origin/RotOrigin, DrawScale not — `meshfacts`). A `DT_Mesh` class whose Mesh is
    unresolvable or fails to decode raises `meshfacts.MeshFactError`; a non-mesh class
    (DT_Sprite/DT_Brush/DT_None) reports `mesh`/`extents` as None, not an error."""
    defaults = resources.class_defaults(fqcn, project)
    drawtype = defaults.get(("drawtype", 0))
    chain = idx.ancestry(fqcn)
    mesh = extents = None
    if drawtype == "DT_Mesh":
        ref = meshfacts.parse_mesh_ref(defaults.get(("mesh", 0)))
        if ref is None:
            raise meshfacts.MeshFactError(
                f"cannot read mesh facts for {fqcn}: DrawType is DT_Mesh but the Mesh default "
                f"({defaults.get(('mesh', 0))!r}) is unresolvable")
        mesh, box, scale = meshfacts.decode_mesh_box(ref, class_fqcn=fqcn, resolver=idx.resolver())
        extents = meshfacts.signed_extents(box, scale)
    return {
        "ref": fqcn,
        "drawtype": drawtype,
        "mesh": mesh,
        "extents": extents,
        "collision": {"radius": _num(defaults.get(("collisionradius", 0))),
                      "height": _num(defaults.get(("collisionheight", 0)))},
        "prepivot": _fvec(defaults.get(("prepivot", 0))),
        "parent": chain[1] if len(chain) > 1 else None,
        "abstract": idx.is_abstract(fqcn),
        "placeable": idx.is_placeable(fqcn),
    }


def _facts_json(facts: dict) -> dict:
    """`_build_facts` → the §3 `--json` object: extents `[lo, hi]` per axis (or null), collision/
    prepivot as plain numbers."""
    c = facts["collision"]
    return {
        "ref": facts["ref"],
        "drawtype": facts["drawtype"],
        "mesh": facts["mesh"],
        "extents": facts["extents"],
        "collision": {"radius": _json_num(c["radius"]), "height": _json_num(c["height"])},
        "prepivot": [_json_num(v) for v in facts["prepivot"]],
        "parent": facts["parent"],
        "abstract": facts["abstract"],
        "placeable": facts["placeable"],
    }


def _print_facts(facts: dict) -> None:
    """The human `Facts:` block appended to `class show` (spec §3). Extents are mesh-local seating
    facts (`Scale` applied, pre-Origin/RotOrigin, DrawScale not); they do NOT assert world facing."""
    print("\nFacts:")
    print(f"  drawtype:  {facts['drawtype'] if facts['drawtype'] is not None else 'none'}")
    print(f"  mesh:      {facts['mesh'] if facts['mesh'] is not None else 'none'}")
    ext = facts["extents"]
    if ext is None:
        print("  extents:   none (not a mesh class)")
    else:
        axes = "  ".join(f"{ax} {ext[ax][0]}..{ext[ax][1]}" for ax in "xyz")
        print(f"  extents:   {axes}   (mesh-local uu; Scale applied, "
              "pre-Origin/RotOrigin, DrawScale not)")
    c = facts["collision"]
    print(f"  collision: radius {uprops.format_float(c['radius'])}  "
          f"height {uprops.format_float(c['height'])}")
    print(f"  prepivot:  {','.join(uprops.format_float(v) for v in facts['prepivot'])}")
    print(f"  parent:    {facts['parent'] if facts['parent'] is not None else 'none'}")


def run(args) -> int:
    """`class list` / `class show` — offline class discovery over the composed `.u` path (no editor,
    no level). Builds the `ClassIndex` from the resolved project."""
    project = resources.resolve_project(args)
    idx = resources.class_index(project)
    if idx.empty:
        raise CommandError(resources.NO_PACKAGE_PATH)
    if args.sub == "list":
        if getattr(args, "legacy_all", False):       # `--all` was split (2026-07-18): targeted pointer
            raise CommandError(
                "class list: --all was split — use --include-non-actor (non-Actor classes), "
                "--include-abstract (abstract/non-placeable), and/or --depth all (full depth).")
        subclass_of = getattr(args, "subclass_of", None)
        flat = getattr(args, "flat", False)
        include_non_actor = getattr(args, "include_non_actor", False)
        include_abstract = getattr(args, "include_abstract", False)
        depth = getattr(args, "depth", None)
        # `--include-abstract` only acts in the --flat drill/--package list; REJECT it where it can do
        # nothing (the tree, the bare category view, or ANY --depth browse — already unfiltered) rather
        # than silently no-op'ing (Andrzej 2026-07-24: error, not warn).
        if include_abstract and not (flat and depth is None
                                     and (subclass_of is not None or args.package is not None)):
            raise CommandError(
                "--include-abstract is not valid here — it applies ONLY to the --flat --subclass-of "
                "drill and the --package flat list. The tree, the bare category view, and any --depth "
                "browse already show abstract classes (branch-points marked *). Drop the flag, or pair "
                "--flat with --subclass-of/--package.")
        try:
            if flat:                                 # --flat: the pipeable one-per-line list
                for fqcn in idx.list_classes(package=args.package, subclass_of=subclass_of,
                                             include_non_actor=include_non_actor,
                                             include_abstract=include_abstract, depth=depth):
                    print(fqcn)
            else:                                    # DEFAULT: the indented inheritance tree
                lines = _class_tree(idx, subclass_of=subclass_of,
                                    include_non_actor=include_non_actor,
                                    depth=depth, package=args.package)
                for line in lines:
                    print(line)
                if args.package and len(lines) == 1:     # only the root survived the --package prune
                    root_name = lines[0].strip().removesuffix(" *")   # drop the abstract mark if present
                    print(f"(no classes under {root_name} are in package {args.package})",
                          file=sys.stderr)
        except ClassRefError as e:
            raise CommandError(str(e))
        return 0
    if args.sub == "show":
        if getattr(args, "legacy_all", False):       # `--all` renamed to `--depth all` (2026-07-18)
            raise CommandError("class show: --all was renamed — use --depth all (the whole super chain).")
        fqcn = args.fqcn
        if not idx.class_exists(fqcn):
            raise CommandError(f"unknown class: {fqcn} (package not on the path, or the package "
                                 f"does not define that class)")
        # FACTS (asset-catalog class arm C1). Built before any output so a bad Mesh fails cleanly
        # with stdout still empty (a redirecting script gets nothing on the exit-2 path).
        try:
            facts = _build_facts(fqcn, idx, project)
        except meshfacts.MeshFactError as e:
            raise CommandError(str(e))
        if getattr(args, "json", False):                 # `--json`: the facts object only (no schema)
            print(json.dumps(_facts_json(facts)))
            return 0
        chain = idx.ancestry(fqcn)
        abstract = idx.is_abstract(fqcn)
        abs_word = {True: "abstract", False: "concrete", None: "abstract=unknown"}[abstract]
        placeable = "placeable" if idx.is_placeable(fqcn) else "not-placeable"

        def _emit(props):
            for p in props:
                dim = f"[{p.array_dim}]" if p.array_dim > 1 else ""
                enum = f" {{{', '.join(p.enum_value_names)}}}" if p.enum_value_names else ""
                print(f"  {p.name}{dim}: {p.kind}{enum}")

        # Props grouped by editor CATEGORY (UnrealEd's own property-browser view). Only EDITABLE props
        # are shown — a `var(Group)`/`var()` prop carries a category, a plain non-editable `var` has
        # category None and is HIDDEN (internal class working). `var()` (no explicit group) stores the
        # declaring class name as its category (per-class section); explicit `var(Group)` categories
        # (Movement/Display/…) cross classes. (RE'd 2026-07-18 — see unrealed/class-schema.md.)
        depth = getattr(args, "depth", None)         # int, math.inf (--depth all), or None
        categories = getattr(args, "categories", None) or []
        # The super chain (idx.ancestry, above) and the property walk BOTH resolve from the persistent
        # per-package SCHEMA CACHE (stat-tuple-keyed, version-consistent): ancestry reads super refs via
        # idx._schema, and resolve_class_properties (no `_cache` seed) takes its cache-ON path for the
        # props. Reading both from that one cache keeps the `super:` line and the prop set consistent
        # per package, which SUBSUMES the old seed (which pre-loaded each chain package as a full
        # `Package` to force one shared byte-read but thereby bypassed the warm schema cache — dropped
        # 2026-07-20 so `class show` gets the ~2.4× warm win).
        # A missing/unparseable ANCESTOR package makes the resolver return None → SchemaError, and that
        # is a HARD ERROR: exit 2 naming the package that failed. There is NO own-only degrade — printing
        # the class's own props with a stderr note is a silent half-answer (the note scrolls away and the
        # caller reads a truncated property set as a complete one). Per `dev/docs/direction/conventions.md` "No silent
        # half-answers" / decisions.md 2026-07-24 21:58 UTC.
        try:
            allp = uprops.resolve_class_properties(fqcn, resolver=idx.resolver())
        except uprops.SchemaError as e:
            raise CommandError(f"cannot read schema for {fqcn}: {e}")
        editable = [p for p in allp if p.category is not None]

        # `--category` (repeatable, exact, case-insensitive, OR-combined) narrows the output to the
        # named editor categories AND forces the EXPANDED render at unlimited depth (spec 2026-07-18:
        # if you asked for a category you want to SEE its props, not a count — and a derived class's
        # category is often entirely inherited). `wanted` is a casefolded set, or None when unfiltered.
        wanted = None
        if categories:
            available = sorted({p.category for p in editable})
            if not available:
                raise CommandError(f"class {fqcn} has no editable categories")
            avail_cf = {c.casefold() for c in available}
            for v in categories:                         # first value matching nothing is named (all-or-
                if v.casefold() not in avail_cf:         # nothing, like multi --set in actor prop)
                    raise CommandError(f"no category {v!r} on {fqcn}; available: "
                                         f"{', '.join(available)}")
            wanted = {v.casefold() for v in categories}

        # Header prints only AFTER --category validation, so a rejected filter leaves stdout empty
        # (a script redirecting stdout gets nothing on an unknown-category error).
        print(f"{fqcn}  [{abs_word}, {placeable}]")
        if len(chain) > 1:
            print(f"  super: {' -> '.join(chain[1:])}")

        if depth is not None or wanted is not None:
            # EXPANDED view: own + INHERITED props per category, inherited tagged `← SourceClass`
            # (Style C). `--depth N` includes inherited from up to N superclass hops (own = hop 0);
            # `--depth all` (math.inf) / `--category` expand the WHOLE chain (unlimited depth).
            chain_cf = [c.casefold() for c in chain]     # chain[0] == this class (hop 0)

            def hop(p):                                  # superclass distance of a prop's declarer
                cf = p.owner.casefold()
                return chain_cf.index(cf) if cf in chain_cf else len(chain_cf)

            # When `--category` filters, the depth budget + omitted-levels trailer reckon over the
            # WANTED categories only, so a level holding no wanted-category prop is never counted.
            in_scope = (lambda p: True) if wanted is None else (lambda p: p.category.casefold() in wanted)
            max_hop = max((hop(p) for p in editable if in_scope(p)), default=0)

            def render(eff):                             # -> the output lines for depth `eff`
                by: dict[str, list] = {}
                for p in editable:
                    if hop(p) <= eff and in_scope(p):
                        by.setdefault(p.category, []).append(p)
                out = []
                for cat, group in by.items():
                    out.append(f"\n{cat}:")
                    for p in sorted(group, key=hop):     # own (hop 0) first; stable within a hop
                        dim = f"[{p.array_dim}]" if p.array_dim > 1 else ""
                        enum = f" {{{', '.join(p.enum_value_names)}}}" if p.enum_value_names else ""
                        # own props (hop 0) are untagged; every inherited prop is tagged with its
                        # FULLY-QUALIFIED source class.
                        tag = "" if hop(p) == 0 else f"   ← {p.owner}"
                        out.append(f"  {p.name}{dim}: {p.kind}{enum}{tag}")
                return out

            if depth is not None:
                eff = max(0, min(depth, max_hop))        # --depth N clips; --depth all (inf) → max_hop
            else:                                        # --category means the WHOLE chain (unlimited
                eff = max_hop                            # depth — a single category is narrow)
            for ln in render(eff):
                print(ln)
            if eff < max_hop:
                scope = "for the whole chain" if wanted is None else "to see every matched superclass level"
                print(f"\n(+{max_hop - eff} more superclass level(s) omitted — --depth all "
                      f"{scope})")
            _print_facts(facts)
            return 0

        # DEFAULT: this class's OWN props grouped by category; inherited props of that category are
        # COLLAPSED to a `(+N inherited, from M superclasses)` count; categories that are ENTIRELY
        # inherited fold into one collapsed tail line (decision 2026-07-18: own-only + inherited counts).
        own_cf = fqcn.casefold()
        own_by_cat: dict[str, list] = {}
        inh_by_cat: dict[str, list] = {}                 # category -> [count, {owner classes}]
        for p in editable:
            if p.owner.casefold() == own_cf:
                own_by_cat.setdefault(p.category, []).append(p)
            else:
                d = inh_by_cat.setdefault(p.category, [0, set()])
                d[0] += 1
                d[1].add(p.owner)

        def _inh_note(n, owners):
            return f"  (+{n} inherited, from {len(owners)} superclass{'es' if len(owners) != 1 else ''})"

        lines_used = 2                                   # header (class + super)
        hidden_own: list[str] = []
        own_cats = list(own_by_cat)
        for i, cat in enumerate(own_cats):
            group = own_by_cat[cat]
            section_lines = len(group) + 2 + (1 if cat in inh_by_cat else 0)
            if i > 0 and lines_used + section_lines > _SHOW_LINE_BUDGET:
                hidden_own = own_cats[i:]
                break
            print(f"\n{cat}:")
            _emit(group)
            if cat in inh_by_cat:
                print(_inh_note(*inh_by_cat[cat]))
            lines_used += section_lines
        if hidden_own:
            noun = "category" if len(hidden_own) == 1 else "categories"
            # list the NAMES (short) so `class show <C>` is a complete category listing — `--category X`
            # is then discoverable without --depth all or a deliberate typo (spec 2026-07-18 discoverability).
            print(f"\n(+{len(hidden_own)} more own {noun} hidden: {', '.join(hidden_own)} "
                  f"— use --depth all or --category NAME)")
        only_inh = sorted(c for c in inh_by_cat if c not in own_by_cat)
        if only_inh:
            tot = sum(inh_by_cat[c][0] for c in only_inh)
            noun = "category" if len(only_inh) == 1 else "categories"
            print(f"\n(+{tot} inherited, in {len(only_inh)} more {noun}: {', '.join(only_inh)})")
        _print_facts(facts)
        return 0
    raise CommandError(f"unimplemented class sub-verb: {args.sub}")

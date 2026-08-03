"""`texture` — offline texture catalog over the composed package search path.

The `texture` noun carries the same verb family as `class`: `list`, `show`, `preview`, `search`,
`classify set·unset·status·tags`, `prewarm`. It enumerates every `Engine.Texture` descendant on the
path, reports Layer-2 facts, produces the preview bitmap, and stores the classification it is handed
against the texture's Layer-1 CONTENT identity (`sha256(w,h,RGB)`, or the name for a procedural). It
never infers meaning — the one exception is texture colours, pre-filled from the texture's own pixels
(`direction/asset-catalog.md`).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from ... import config, texture_catalog as tc, texture_colors, utexture
from ...texture_catalog import TextureCatalogError
from .. import rendering, resources, targets
from ..errors import CommandError


# ── shared: the resolver (widened), identity + Layer-2 facts, colours ────────────────────────────

def _resolver_and_index(project):
    """The widened `TextureResolver` (carrying the class index) over the composed path, or a clean
    exit 2 when the path resolves no packages. Every path-reading verb goes through here."""
    idx = resources.class_index(project)
    if idx.empty:
        raise CommandError(resources.NO_PACKAGE_PATH)
    resolver = resources.texture_resolver(project, class_index=idx)
    if resolver is None:
        raise CommandError(resources.NO_PACKAGE_PATH)
    return resolver


def _ref_pkg_name(ref: str) -> tuple[str, str]:
    parts = ref.split(".")
    return parts[0], parts[-1]


def _ref_facts(resolver, ref: str) -> tuple[str | None, dict, "utexture.TextureError | None"]:
    """Decode `ref` → `(identity | None, facts, error)`. A `DecodedTexture` → its content identity
    + full facts. A procedural (`no-mip-data`) → its NAME identity + facts with no bitmap. Any other
    error → `identity=None` (reads unclassified; a per-ref request exits 2). `group` is a Layer-2
    fact read live from the export."""
    res = resolver.resolve(ref)
    pkgi = resolver.package_for_ref(ref)
    group = utexture.group_of_export(*pkgi) if pkgi else None
    if isinstance(res, utexture.DecodedTexture):
        identity = utexture.texture_identity(res)
        facts = {"ref": ref, "width": res.width, "height": res.height, "format": res.layout,
                 "group": group, "masked": res.b_masked, "identity": identity, "procedural": False}
        return identity, facts, None
    if res.case == "no-mip-data":                        # a procedural texture — name-keyed
        pkg, name = _ref_pkg_name(ref)
        identity = utexture.procedural_identity(pkg, name)
        facts = {"ref": ref, "width": None, "height": None, "format": None, "group": group,
                 "masked": None, "identity": identity, "procedural": True}
        return identity, facts, res
    return None, {"ref": ref, "width": None, "height": None, "format": None, "group": group,
                  "masked": None, "identity": None, "procedural": False}, res


def _colors_for(resolver, ref: str, facts: dict, shard) -> list[str]:
    """The colours to REPORT for `ref`: a classified texture's stored `colors` (when set), else
    derived live from its pixels — so colour facts work before any classification. A procedural /
    undecodable texture has no pixels, so `[]`."""
    if shard is not None and shard.colors:
        return list(shard.colors)
    if facts["procedural"] or facts["identity"] is None:
        return []
    res = resolver.resolve(ref)
    if isinstance(res, utexture.DecodedTexture):
        return texture_colors.derive_colors(res.width, res.height, res.rgb)
    return []


# ── list ─────────────────────────────────────────────────────────────────────────────────────────

def _run_list(args, resolver, catalog_dir) -> int:
    entries = resolver.texture_refs()
    if args.package is not None:
        entries = [t for t in entries if t.package.casefold() == args.package.casefold()]
    group_cf = args.group.casefold() if args.group is not None else None
    # --group filters on the enumeration's Layer-2 group WITHOUT decoding; identity/masked need it.
    need_decode = args.json or args.classified or args.unclassified or args.masked
    have = tc.classified_identities(catalog_dir) if need_decode else set()
    for t in entries:
        if group_cf is not None and (t.group or "").casefold() != group_cf:
            continue
        if not need_decode:
            print(t.ref)
            continue
        identity, facts, _err = _ref_facts(resolver, t.ref)
        is_cls = identity is not None and identity in have
        if args.classified and not is_cls:
            continue
        if args.unclassified and is_cls:
            continue
        if args.masked and facts["masked"] is not True:
            continue
        if args.json:
            print(json.dumps({"ref": t.ref, "identity": identity, "classified": is_cls,
                              "group": t.group, "masked": facts["masked"], "preview": None}))
        else:
            print(t.ref)
    return 0


# ── show ───────────────────────────────────────────────────────────────────────────────────────────

def _masked_word(m) -> str:
    return "unknown" if m is None else ("true" if m else "false")


def _run_show(args, resolver, catalog_dir) -> int:
    refs = targets.resolve_target_names(args.refs)
    if not refs:                                          # empty stdin / no refs → clean no-op
        return 0
    for ref in refs:
        identity, facts, err = _ref_facts(resolver, ref)
        if identity is None:                              # ref-layer / undecodable non-procedural
            raise CommandError(f"{ref}: {err.case} — {err.detail}")
        shard = tc.load_shard(tc.shard_path(catalog_dir, identity))
        colors = _colors_for(resolver, ref, facts, shard)
        if args.json:
            classification = (None if shard is None else
                              {"tags": shard.tags, "description": shard.description,
                               "colors": shard.colors})
            print(json.dumps({"ref": ref, "width": facts["width"], "height": facts["height"],
                              "format": facts["format"], "group": facts["group"],
                              "masked": facts["masked"], "identity": identity,
                              "colors": colors, "classification": classification}))
            continue
        size = ("none (procedural — no bitmap)" if facts["procedural"]
                else f"{facts['width']}x{facts['height']}")
        print(ref)
        print(f"  size:     {size}")
        print(f"  format:   {facts['format'] if facts['format'] else 'none'}")
        print(f"  group:    {facts['group'] if facts['group'] else 'none'}")
        print(f"  masked:   {_masked_word(facts['masked'])}")
        print(f"  identity: {identity}")
        print(f"  colors:   {', '.join(colors) if colors else '(none)'}")
        print("Classification:")
        if shard is None:
            print("  (unclassified)")
        else:
            print(f"  tags:        {', '.join(shard.tags) if shard.tags else '(none)'}")
            print(f"  description: {shard.description if shard.description else '(none)'}")
    return 0


# ── preview ─────────────────────────────────────────────────────────────────────────────────────────

def _run_preview(args, resolver, catalog_dir) -> int:
    refs = targets.resolve_target_names(args.refs)
    if not refs:
        return 0
    from PIL import Image
    for ref in refs:
        res = resolver.resolve(ref)
        if isinstance(res, utexture.TextureError):
            # A per-ref request exits 2 naming the ref + case (procedural / undecodable alike). The
            # ambiguous-alpha text already states the stated limit on universality (`utexture`).
            raise CommandError(f"{ref}: {res.case} — {res.detail}")
        img = Image.frombytes("RGB", (res.width, res.height), res.rgb)   # mip 0, mask NOT applied
        host_out = rendering.write_png(img, args.out)
        if args.skeleton:                                # the ready-to-fill classification row
            colors = texture_colors.derive_colors(res.width, res.height, res.rgb)
            print(json.dumps({"ref": ref, "preview": host_out, "tags": [], "description": "",
                              "colors": colors}))
        else:
            print(f"{ref}\t{host_out}")
    return 0


# ── search ─────────────────────────────────────────────────────────────────────────────────────────

def _run_search(args, resolver, catalog_dir) -> int:
    terms = [t.lower() for t in args.terms if t.strip()]
    if not terms:
        raise CommandError(
            "texture search needs at least one term (it ranks textures by name + stored tags/"
            "description). To list every texture without ranking, use `texture list`.")
    try:
        texture_colors.validate_colors([c.lower() for c in args.color])
    except ValueError as e:
        raise CommandError(str(e))
    want_colors = {c.lower() for c in args.color}
    require_tags = [t.lower() for t in args.tag]
    group_cf = args.group.casefold() if args.group is not None else None
    have = tc.classified_identities(catalog_dir)
    scored: list[tuple[int, str, bool, list[str], str, list[str]]] = []
    for t in resolver.texture_refs():
        if args.package is not None and t.package.casefold() != args.package.casefold():
            continue
        if group_cf is not None and (t.group or "").casefold() != group_cf:
            continue
        identity, facts, _err = _ref_facts(resolver, t.ref)
        if args.masked and facts["masked"] is not True:
            continue
        classified = identity is not None and identity in have
        if args.classified and not classified:
            continue
        if args.unclassified and classified:
            continue
        shard = (tc.load_shard(tc.shard_path(catalog_dir, identity))
                 if classified else None)
        tags, desc = (shard.tags, shard.description) if shard else ([], "")
        if require_tags and not all(rt in tags for rt in require_tags):
            continue
        colors = _colors_for(resolver, t.ref, facts, shard)   # stored, else live-derived (like show)
        if want_colors and not (want_colors & set(colors)):
            continue
        s = tc.score(t.ref, tags, desc, terms)
        if s is None:
            continue
        scored.append((s, t.ref, classified, tags, desc, colors))
    scored.sort(key=lambda r: (-r[0], r[1]))
    for s, ref, classified, tags, desc, colors in scored:
        if args.json:
            print(json.dumps({"ref": ref, "score": s, "classified": classified,
                              "tags": tags, "description": desc, "colors": colors}))
        else:
            print(ref)
    if not scored:
        print("no matches", file=sys.stderr)
    else:
        print(f"{len(scored)} match{'es' if len(scored) != 1 else ''}", file=sys.stderr)
    return 0


# ── prewarm ─────────────────────────────────────────────────────────────────────────────────────────

def _run_prewarm(args, resolver, catalog_dir) -> int:
    entries = resolver.texture_refs()
    if args.package is not None:
        entries = [t for t in entries if t.package.casefold() == args.package.casefold()]
    warmed = 0
    for t in entries:
        resolver.resolve(t.ref)                          # warm the per-invocation ref→identity cache
        warmed += 1
    print(f"warmed {warmed} texture{'s' if warmed != 1 else ''} (decoded ref → identity)",
          file=sys.stderr)
    return 0


# ── classify ─────────────────────────────────────────────────────────────────────────────────────────

def _require_identity(resolver, ref: str) -> tuple[str, dict]:
    """`ref` → `(identity, facts)`, or a clean exit 2. A procedural is classifiable (name identity);
    an undecodable non-procedural has no identity to key on and exits 2 naming the case."""
    identity, facts, err = _ref_facts(resolver, ref)
    if identity is None:
        raise CommandError(f"{ref}: {err.case} — {err.detail}")
    return identity, facts


def _prefill_colors(resolver, facts: dict, given) -> list[str]:
    """An LLM-supplied `colors` wins; otherwise pre-fill from the texture's pixels (a procedural has
    none, so `[]`)."""
    if given is not None:
        return list(given)
    if facts["procedural"]:
        return []
    res = resolver.resolve(facts["ref"])
    if isinstance(res, utexture.DecodedTexture):
        return texture_colors.derive_colors(res.width, res.height, res.rgb)
    return []


def _classify_set(args, resolver, cat_dir, lock_dir) -> int:
    if args.ref == "-":
        return _classify_set_batch(args, resolver, cat_dir, lock_dir)
    if args.ref is None:
        raise CommandError("classify set needs a texture ref (Package[.Group].Name), or - to read "
                           "JSONL rows {ref, tags?, description?, colors?} from stdin")
    if args.tags is None and args.description is None:
        raise CommandError(f"classify set {args.ref}: nothing to set — pass --tags and/or "
                           "--description")
    identity, facts = _require_identity(resolver, args.ref)
    given = None if args.colors is None else [c.lower() for c in args.colors]
    if given is not None:
        texture_colors.validate_colors(given)
    colors = _prefill_colors(resolver, facts, given)
    with tc.shard_lock(lock_dir, identity):
        path = tc.shard_path(cat_dir, identity)
        shard = tc.merge_set(tc.load_shard(path), identity=identity, ref=args.ref,
                             tags=args.tags, description=args.description, colors=colors,
                             force=args.force)
        tc.save_shard(path, shard)
    print(args.ref)
    return 0


def _classify_set_batch(args, resolver, cat_dir, lock_dir) -> int:
    """`classify set -` — JSONL rows {ref, tags?, description?, colors?}, one shard per row. ALL-OR-
    NOTHING: every row is validated (ref decodable, colours in palette, refuse-over-existing) and its
    shard staged in memory FIRST; a single bad row exits 2 naming it and writes nothing. Empty stdin
    is a clean no-op (exit 0)."""
    rows: list[tuple[int, dict]] = []
    for lineno, line in enumerate(sys.stdin.read().splitlines(), 1):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as e:
            raise CommandError(f"classify set -: line {lineno}: not valid JSON ({e})")
        if not isinstance(obj, dict) or not isinstance(obj.get("ref"), str):
            raise CommandError(f"classify set -: line {lineno}: each row must be a JSON object with "
                               "a string `ref`")
        rows.append((lineno, obj))
    if not rows:
        return 0
    staged: dict[str, tuple] = {}                        # identity -> (path, ref, shard)
    for lineno, obj in rows:
        ref = obj["ref"]
        tags = obj.get("tags")
        if tags is not None and not (isinstance(tags, list) and all(isinstance(x, str) for x in tags)):
            raise CommandError(f"classify set -: line {lineno}: `tags` must be an array of strings")
        desc = obj.get("description")
        if desc is not None and not isinstance(desc, str):
            raise CommandError(f"classify set -: line {lineno}: `description` must be a string")
        given_colors = obj.get("colors")
        if given_colors is not None and not (isinstance(given_colors, list)
                                             and all(isinstance(x, str) for x in given_colors)):
            raise CommandError(f"classify set -: line {lineno}: `colors` must be an array of strings")
        given = None if given_colors is None else [c.lower() for c in given_colors]
        try:
            identity, facts = _require_identity(resolver, ref)
            if given is not None:
                texture_colors.validate_colors(given)
            colors = _prefill_colors(resolver, facts, given)
            path = tc.shard_path(cat_dir, identity)
            prior = staged[identity][2] if identity in staged else tc.load_shard(path)
            shard = tc.merge_set(prior, identity=identity, ref=ref, tags=tags, description=desc,
                                 colors=colors, force=args.force)
        except (TextureCatalogError, ValueError) as e:
            raise CommandError(f"classify set -: line {lineno}: {e}")
        staged[identity] = (path, ref, shard)
    for path, ref, shard in staged.values():
        with tc.shard_lock(lock_dir, shard.identity):
            tc.save_shard(path, shard)
        print(ref)
    return 0


def _classify_unset(args, resolver, cat_dir, lock_dir) -> int:
    """`classify unset <ref>… | -` — undo classification on each ref's IDENTITY shard. Reads a
    newline ref list on `-`; empty stdin is a clean no-op. All-or-nothing: every ref must decode
    and own a shard, else exit 2 naming it, nothing changed."""
    refs = targets.resolve_target_names(args.refs)
    if not refs:
        return 0
    if args.tags is None:
        remove_tags, clear_tags = None, False
    elif args.tags == []:                                # BARE --tags: clear the whole field
        remove_tags, clear_tags = None, True
    else:
        remove_tags, clear_tags = args.tags, False
    plans: list[tuple] = []
    for ref in refs:
        identity, _facts = _require_identity(resolver, ref)
        path = tc.shard_path(cat_dir, identity)
        prior = tc.load_shard(path)
        if prior is None:
            raise CommandError(f"not classified: {ref} (no shard to unset)")
        if args.clear_all:
            plans.append((ref, identity, path, None))
        else:
            plans.append((ref, identity, path, tc.unset(
                prior, remove_tags=remove_tags, clear_tags=clear_tags,
                clear_description=args.description, clear_colors=args.colors)))
    for ref, identity, path, shard in plans:
        with tc.shard_lock(lock_dir, identity):
            if shard is None:
                path.unlink(missing_ok=True)
            else:
                tc.save_shard(path, shard)
        print(ref)
    return 0


def _classify_status(args, resolver, cat_dir) -> int:
    """Of the textures on the path, how many have a shard — the INTERSECTION of on-path identities
    with stored shards (so the ratio never exceeds the total). Decodes each ref to its identity."""
    on_path = set()
    for t in resolver.texture_refs():
        identity, _facts, _err = _ref_facts(resolver, t.ref)
        if identity is not None:
            on_path.add(identity)
    classified = len(tc.classified_identities(cat_dir) & on_path)
    total = len(on_path)
    if args.json:
        print(json.dumps({"classified": classified, "total": total}))
    else:
        print(f"classified {classified} / {total} textures")
    return 0


def _classify_tags(args, cat_dir) -> int:
    shards, bad = tc.load_all_shards(cat_dir)
    for p in bad:
        print(f"skipping unreadable shard {p}", file=sys.stderr)
    vocab = tc.tag_vocabulary(shards)
    if args.json:
        print(json.dumps({tag: n for tag, n in vocab}))
    else:
        for tag, n in vocab:
            print(f"{tag}\t{n}")
    return 0


# ── entry ─────────────────────────────────────────────────────────────────────────────────────────

def run(args) -> int:
    """The offline texture catalog. STATELESS — no level, no live editor. Resolves the project
    LAZILY: every path-reading verb needs it (and the composed package path); `classify tags` reads
    only the shard tree, so an explicit `--catalog-dir` runs it OUTSIDE a project."""
    _project: dict = {}

    def project():
        if "p" not in _project:
            _project["p"] = resources.resolve_project(args)     # no project ⇒ ProjectError → exit 2
        return _project["p"]

    catalog_dir = args.catalog_dir or resources.catalog_dir(project())

    def lock_dir() -> str:
        return str(config.self_ignoring_dir(Path(catalog_dir) / ".locks", create=True,
                                            what="catalog lock dir"))

    try:
        if args.sub == "classify" and args.csub == "tags":  # shard-only — no package path needed
            return _classify_tags(args, catalog_dir)
        resolver = _resolver_and_index(project())
        if args.sub == "list":
            return _run_list(args, resolver, catalog_dir)
        if args.sub == "show":
            return _run_show(args, resolver, catalog_dir)
        if args.sub == "preview":
            return _run_preview(args, resolver, catalog_dir)
        if args.sub == "search":
            return _run_search(args, resolver, catalog_dir)
        if args.sub == "prewarm":
            return _run_prewarm(args, resolver, catalog_dir)
        if args.sub == "classify":
            if args.csub == "set":
                return _classify_set(args, resolver, catalog_dir, lock_dir())
            if args.csub == "unset":
                return _classify_unset(args, resolver, catalog_dir, lock_dir())
            if args.csub == "status":
                return _classify_status(args, resolver, catalog_dir)
            raise CommandError(f"unimplemented texture classify sub-verb: {args.csub}")
    except (TextureCatalogError, ValueError) as e:
        raise CommandError(str(e))
    raise CommandError(f"unimplemented texture sub-verb: {args.sub}")

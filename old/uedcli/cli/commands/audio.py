"""`sound` / `music` — offline audio discovery + classification over the composed package path.

One kind-parametrised handler behind two nouns (`args.kind` is `"sound"` or `"music"`, set by each
parser). The verbs mirror the class arm (`cli.commands.classes`): `list`/`show`/`search` are offline
producers; `classify set|unset|status|tags` records what an object IS. Identity is name-based
(`audioindex`): a ref keys to `Package.Name`, or the full dotted `Package.Group.Name` on a bare-name
collision. `music` additionally reports each module's embedded title (`umxtitle`), read live.

The store is `audio_catalog`, with the refuse-then-`--force` write rule (never a silent overwrite of
authored classification) — NOT the class arm's tag union-merge.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from ... import audio_catalog, audioindex, config, umxtitle
from .. import resources, targets
from ..errors import CommandError

_TITLE_KINDS = {"music"}                    # kinds whose objects carry an embedded module title


# --------------------------------------------------------------------------- shared helpers

def _catalog_and_locks(project):
    """The catalog dir (mockable `resources.catalog_dir` seam) and its self-ignoring per-shard lock
    dir `<catalog>/.locks/`, mirroring the class arm so lock litter can never be committed."""
    cat = resources.catalog_dir(project)
    locks = str(config.self_ignoring_dir(Path(cat) / ".locks", create=True, what="catalog lock dir"))
    return cat, locks


def _resolve(index, ref: str) -> str:
    """Supplied ref → stored identity, turning `AudioRefError` into a clean exit 2."""
    try:
        return index.resolve(ref)
    except audioindex.AudioRefError as e:
        raise CommandError(str(e))


def _title_of(entry) -> tuple[str | None, str]:
    """The `(title, format)` for a music object, sniffed live from its `.umx`."""
    with open(entry.path, "rb") as f:
        return umxtitle.sniff_title(f.read())


# --------------------------------------------------------------------------- list

def _run_list(args, index, project) -> int:
    kind = args.kind
    wanted = None
    if args.package:
        have = index.packages()
        for p in args.package:
            if p.casefold() not in have:
                raise CommandError(f"package not found on the path (no {kind} objects): {p}")
        wanted = {p.casefold() for p in args.package}
    classified = audio_catalog.classified_refs(resources.catalog_dir(project), kind)
    entries = sorted(index.entries, key=lambda e: e.ref.casefold())
    shown = 0
    for e in entries:
        if wanted is not None and e.package.casefold() not in wanted:
            continue
        is_cls = e.identity.casefold() in classified
        if args.only_classified and not is_cls:
            continue
        if args.only_unclassified and is_cls:
            continue
        if args.json:
            obj = {"ref": e.ref, "identity": e.identity, "group": e.group, "classified": is_cls}
            if kind in _TITLE_KINDS:
                title, fmt = _title_of(e)
                obj["title"], obj["format"] = title, fmt
            print(json.dumps(obj))
        else:
            print(e.ref)
        shown += 1
    print(f"{shown} {kind}{'s' if shown != 1 else ''}", file=sys.stderr)
    return 0


# --------------------------------------------------------------------------- show

def _run_show(args, index, project) -> int:
    kind = args.kind
    refs = targets.resolve_target_names(args.refs)
    if not refs:                                          # empty stdin / no refs → clean no-op
        return 0
    cat_dir = resources.catalog_dir(project)
    blocks = []
    for ref in refs:
        identity = _resolve(index, ref)
        entry = index.entry_of_identity(identity)
        shard = audio_catalog.load_shard(audio_catalog.shard_path(cat_dir, kind, identity))
        obj = {"ref": entry.ref, "identity": entry.identity, "package": entry.package,
               "group": entry.group,
               "classification": None if shard is None
               else {"tags": shard.tags, "description": shard.description}}
        if kind in _TITLE_KINDS:
            obj["title"], obj["format"] = _title_of(entry)
        blocks.append(obj)
    if args.json:
        for obj in blocks:
            print(json.dumps(obj))
        return 0
    for obj in blocks:
        print(obj["ref"])
        print(f"  identity: {obj['identity']}")
        print(f"  package:  {obj['package']}")
        print(f"  group:    {obj['group'] if obj['group'] is not None else '(root)'}")
        if kind in _TITLE_KINDS:
            print(f"  title:    {obj['title'] if obj['title'] is not None else '(none)'}")
            print(f"  format:   {obj['format']}")
        cls = obj["classification"]
        print("  classification:")
        if cls is None:
            print("    (unclassified)")
        else:
            print(f"    tags:        {', '.join(cls['tags']) if cls['tags'] else '(none)'}")
            print(f"    description: {cls['description'] if cls['description'] else '(none)'}")
    return 0


# --------------------------------------------------------------------------- search

def _run_search(args, index, project) -> int:
    kind = args.kind
    terms = [t.lower() for t in args.terms if t.strip()]
    if not terms:
        raise CommandError(
            f"{kind} search needs at least one term (it ranks objects by name + stored tags/"
            f"description). To list every {kind} without ranking, use `{kind} list`.")
    cat_dir = resources.catalog_dir(project)
    classified = audio_catalog.classified_refs(cat_dir, kind)
    require_tags = [t.lower() for t in args.tag]
    scored: list[tuple[int, str, bool, list[str], str]] = []
    for e in index.entries:
        is_cls = e.identity.casefold() in classified
        if is_cls:
            shard = audio_catalog.load_shard(audio_catalog.shard_path(cat_dir, kind, e.identity))
            tags, desc = (shard.tags, shard.description) if shard else ([], "")
        else:
            tags, desc = [], ""
        if require_tags and not all(t in tags for t in require_tags):
            continue
        s = audio_catalog.score(e.ref, tags, desc, terms)
        if s is None:
            continue
        scored.append((s, e.ref, is_cls, tags, desc))
    scored.sort(key=lambda r: (-r[0], r[1]))              # score desc, then ref asc — deterministic
    for s, ref, is_cls, tags, desc in scored:
        if args.json:
            print(json.dumps({"ref": ref, "score": s, "classified": is_cls,
                              "tags": tags, "description": desc}))
        else:
            print(ref)
    if not scored:
        print("no matches", file=sys.stderr)
    else:
        print(f"{len(scored)} match{'es' if len(scored) != 1 else ''}", file=sys.stderr)
    return 0


# --------------------------------------------------------------------------- classify

def _classify_set(args, index, kind, cat_dir, lock_dir) -> int:
    if args.ref == "-":
        return _classify_set_batch(args, index, kind, cat_dir, lock_dir)
    if args.ref is None:
        raise CommandError(f"{kind} classify set needs a ref (Package.Name), or - to read JSONL "
                           "rows {ref, tags, description} from stdin")
    if args.tags is None and args.description is None:
        raise CommandError(f"{kind} classify set {args.ref}: nothing to set — pass --tags and/or "
                           "--description")
    identity = _resolve(index, args.ref)
    with audio_catalog.shard_lock(lock_dir, kind, identity):
        path = audio_catalog.shard_path(cat_dir, kind, identity)
        shard = audio_catalog.set_shard(audio_catalog.load_shard(path), kind, identity,
                                        tags=args.tags, description=args.description,
                                        force=args.force)
        audio_catalog.save_shard(path, shard)
    print(identity)
    return 0


def _classify_set_batch(args, index, kind, cat_dir, lock_dir) -> int:
    """`classify set -` — JSONL rows {ref, tags?, description?}, one shard write per row. ALL-OR-
    NOTHING: every row is validated (ref resolves, tag/desc types, refuse-existing unless --force)
    and staged in memory FIRST; a single bad row exits 2 naming it and writes nothing. `--force`
    governs every row. Empty stdin is a clean no-op (exit 0)."""
    rows: list[tuple[int, dict]] = []
    for lineno, line in enumerate(sys.stdin.read().splitlines(), 1):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as e:
            raise CommandError(f"{kind} classify set -: line {lineno}: not valid JSON ({e})")
        if not isinstance(obj, dict) or not isinstance(obj.get("ref"), str):
            raise CommandError(f"{kind} classify set -: line {lineno}: each row must be a JSON "
                               "object with a string `ref`")
        rows.append((lineno, obj))
    if not rows:
        return 0
    staged: dict[str, tuple] = {}                          # shard path -> (path, identity, AudioShard)
    for lineno, obj in rows:
        identity = _resolve(index, obj["ref"])
        tags = obj.get("tags")
        if tags is not None and not (isinstance(tags, list) and all(isinstance(t, str) for t in tags)):
            raise CommandError(f"{kind} classify set -: line {lineno}: `tags` must be an array of strings")
        desc = obj.get("description")
        if desc is not None and not isinstance(desc, str):
            raise CommandError(f"{kind} classify set -: line {lineno}: `description` must be a string")
        path = audio_catalog.shard_path(cat_dir, kind, identity)
        key = str(path)
        prior = staged[key][2] if key in staged else audio_catalog.load_shard(path)
        try:
            shard = audio_catalog.set_shard(prior, kind, identity, tags=tags, description=desc,
                                            force=args.force)
        except audio_catalog.AudioCatalogError as e:
            raise CommandError(f"{kind} classify set -: line {lineno}: {e}")
        staged[key] = (path, identity, shard)
    for path, identity, shard in staged.values():
        with audio_catalog.shard_lock(lock_dir, kind, identity):
            audio_catalog.save_shard(path, shard)
        print(identity)
    return 0


def _classify_unset(args, index, kind, cat_dir, lock_dir) -> int:
    """`classify unset <ref>… | -` — undo classification. Reads a newline ref list on `-`; empty
    stdin is a clean no-op. All-or-nothing: every ref must resolve AND own a shard, else exit 2
    naming it, nothing changed."""
    refs = targets.resolve_target_names(args.refs)
    if not refs:
        return 0
    if args.tags is None:
        remove_tags, clear_tags = None, False
    elif args.tags == []:                                 # BARE --tags: clear the whole field
        remove_tags, clear_tags = None, True
    else:
        remove_tags, clear_tags = args.tags, False
    plans: list[tuple] = []
    for ref in refs:
        identity = _resolve(index, ref)
        path = audio_catalog.shard_path(cat_dir, kind, identity)
        prior = audio_catalog.load_shard(path)
        if prior is None:
            raise CommandError(f"not classified: {identity} (no shard to unset)")
        if args.clear_all:
            plans.append((identity, path, None))
        else:
            plans.append((identity, path, audio_catalog.unset(
                prior, remove_tags=remove_tags, clear_tags=clear_tags,
                clear_description=args.description)))
    for identity, path, shard in plans:
        with audio_catalog.shard_lock(lock_dir, kind, identity):
            if shard is None:
                path.unlink(missing_ok=True)
            else:
                audio_catalog.save_shard(path, shard)
        print(identity)
    return 0


def _classify_status(args, index, kind, cat_dir) -> int:
    on_path = {e.identity.casefold() for e in index.entries}
    classified = len(audio_catalog.classified_refs(cat_dir, kind) & on_path)
    total = len(on_path)
    if args.json:
        print(json.dumps({"classified": classified, "total": total}))
    else:
        print(f"classified {classified} / {total} {kind}s")
    return 0


def _classify_tags(args, kind, cat_dir) -> int:
    shards, bad = audio_catalog.load_all_shards(cat_dir, kind)
    for p in bad:
        print(f"skipping unreadable shard {p}", file=sys.stderr)
    vocab = audio_catalog.tag_vocabulary(shards)
    if args.json:
        print(json.dumps({tag: n for tag, n in vocab}))
    else:
        for tag, n in vocab:
            print(f"{tag}\t{n}")
    return 0


def _run_classify(args, index, project) -> int:
    kind = args.kind
    cat_dir, lock_dir = _catalog_and_locks(project)
    if args.csub == "set":
        return _classify_set(args, index, kind, cat_dir, lock_dir)
    if args.csub == "unset":
        return _classify_unset(args, index, kind, cat_dir, lock_dir)
    if args.csub == "status":
        return _classify_status(args, index, kind, cat_dir)
    if args.csub == "tags":
        return _classify_tags(args, kind, cat_dir)
    raise CommandError(f"unimplemented {kind} classify sub-verb: {args.csub}")


# --------------------------------------------------------------------------- entry point

def run(args) -> int:
    """`sound`/`music` `list`/`show`/`search`/`classify` — offline audio discovery + classification.
    `args.kind` selects the noun; the enumeration is `resources.audio_index` (a mockable seam)."""
    project = resources.resolve_project(args)
    index = resources.audio_index(project, args.kind)
    # One conversion point: an `AudioCatalogError` (bad ref shape, or an unreadable/malformed tracked
    # shard reached via `load_shard` on any read/write path) becomes a clean exit 2, never a traceback.
    try:
        if args.sub == "list":
            return _run_list(args, index, project)
        if args.sub == "show":
            return _run_show(args, index, project)
        if args.sub == "search":
            return _run_search(args, index, project)
        if args.sub == "classify":
            return _run_classify(args, index, project)
    except audio_catalog.AudioCatalogError as e:
        raise CommandError(str(e))
    raise CommandError(f"unimplemented {args.kind} sub-verb: {args.sub}")

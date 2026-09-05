"""`level` command family — operations over a project's levels.

`cli.dispatch` enters through `run(args)`, which routes the subverb: `list`/`create`/`import`/
`reimport`/`materialize`/`photo`/`status`/`doctor`. Ordering the reorg must preserve:

- `level import` resolves its destination and runs the overwrite/path-safety guard BEFORE reading the
  map file (`_resolve_import_dest`);
- `level materialize` validates `--out`, and `level photo` validates its shot/mode flags, BEFORE
  resolving the project or any expensive game resource;
- source resolution honours `--tree`/`$UEDCLI_LEVEL`, and a level taken from the env is announced once
  (`level_sources.announce_env_level`) for the WRITE verbs (materialize/capture), never for a read;
- `photo` keeps its lazy resource provider — the composed dirs/load set/schema resolver are built
  only on a trunk cache miss, never for `--map` or a cache hit.

Level photo stays WITH this family (it was deliberately not folded into `cli.rendering`). This
module uses the shared `cli.ingest`/`cli.resources`/`cli.level_sources` owners and the model/service
modules; it never imports another command family or the router.
"""
from __future__ import annotations

import os
import re
import secrets
import subprocess
import sys
import time
from pathlib import Path

from .. import ingest, level_sources, resources
from ..errors import CommandError, LevelSelectionError
from ... import config, stash_register, stashlib, trunk
from ...model import Level, parse_t3d, parse_t3d_actors
from ...normalize import canonical_actor_t3d
from ...uprops import SchemaError


def run(args) -> int:
    """Route one `level` invocation to its handler, preserving the monolith's dispatch order."""
    if args.sub == "materialize":
        return _level_materialize(args)
    if args.sub == "paths":
        return _level_paths_define(args)
    if args.sub == "photo":
        return _level_preview(args)
    if args.sub == "doctor":
        return _level_doctor(args, level_sources.resolve_level_source(args))
    if args.sub == "create":
        return _level_create(args)
    if args.sub == "import":
        return _level_import(args)
    if args.sub == "reimport":
        return _level_reimport(args)
    if args.sub == "list":
        return _level_list(args)
    if args.sub == "status":
        return _level_status(args)
    raise CommandError(f"unimplemented level sub-verb: {args.sub}")


def _level_actor_counts(level: Level) -> tuple[int, int, int]:
    """(total, brush actors, point actors) for the level."""
    total = len(level.actors)
    brushes = sum(1 for a in level.actors.values() if a.brush is not None)
    return total, brushes, total - brushes


def _git_toplevel(path: Path) -> str | None:
    """The git working-tree root containing `path`, or None if `path` is not inside a git repo.
    Raises OSError/SubprocessError if git itself is unavailable (the caller decides what to do)."""
    r = subprocess.run(["git", "-C", str(path), "rev-parse", "--show-toplevel"],
                       capture_output=True, text=True, timeout=5)
    if r.returncode != 0:
        return None
    return r.stdout.strip() or None


def _tool_repo_toplevel() -> str | None:
    """The git repo uedcli's OWN source lives in — None when installed (pipx/site-packages, not a
    repo). Used to tell a real project repo apart from a scratch project sitting INSIDE the uedcli
    source tree, which would otherwise make git walk up and report uedcli's branch."""
    try:
        return _git_toplevel(Path(__file__).resolve().parent)
    except (OSError, subprocess.SubprocessError):
        return None


_DETECT_TOOL_REPO = object()   # sentinel: "detect from uedcli's install", distinct from a real None


def _git_hint(root: Path, trunk_dir: Path, *, tool_repo_root=_DETECT_TOOL_REPO) -> str | None:
    """Best-effort one-line git state for the LEVEL's OWN project repo (not uedcli's): the branch,
    plus the count of uncommitted changes SCOPED to the level's trunk dir. Returns a "not a git
    repo" note when the project root is not tracked in its own repo — including the case where it
    only lives inside uedcli's OWN source tree (git would otherwise leak uedcli's branch/status,
    the reported bug). None only when git itself is unavailable. `tool_repo_root` is injectable for
    tests (a sentinel default means "detect from uedcli's install location").
    Read-only — uedcli never runs git operations, this only reports (decisions 2026-07-05 19:50)."""
    if tool_repo_root is _DETECT_TOOL_REPO:
        tool_repo_root = _tool_repo_toplevel()
    try:
        proj_top = _git_toplevel(root)
        if proj_top is None:
            return "project is not a git repo"
        if tool_repo_root is not None and proj_top == tool_repo_root:
            # The project isn't its own repo — it's incidentally inside uedcli's source tree.
            return "project is not a git repo (it lives inside the uedcli tool tree, not its own repo)"
        # `branch --show-current` (not `rev-parse --abbrev-ref HEAD`) so a fresh repo with no commits
        # yet — an unborn branch — still reports its branch instead of failing.
        branch = subprocess.run(["git", "-C", str(root), "branch", "--show-current"],
                                capture_output=True, text=True, timeout=5)
        if branch.returncode != 0:
            return "project is not a git repo"
        branch_name = branch.stdout.strip() or "(detached HEAD)"
        dirty = subprocess.run(["git", "-C", str(root), "status", "--porcelain", "--", str(trunk_dir)],
                               capture_output=True, text=True, timeout=5)
        n = len([ln for ln in dirty.stdout.splitlines() if ln.strip()])
        return f"on branch {branch_name}; {n} uncommitted change(s) in this level — see `git status`"
    except (OSError, subprocess.SubprocessError):
        return None


def _level_create(args) -> int:
    """Scaffold a NEW level: `maps/<name>/` with a single `Engine.LevelInfo` actor. Materialize
    REQUIRES a LevelInfo — a level with none inherits `MAP NEW`'s default LevelInfo, which survives
    the re-import and fails post-verify (an actor the trunk lacks). Refuses to clobber an existing
    non-empty level. `Engine.LevelInfo` is the substrate-agnostic base (DeusEx's DeusExLevelInfo
    subclasses it; the base loads in-game — verified live). To edit the new level, export it:
    `export UEDCLI_LEVEL=<name>` (there is no `--select`: a child process can't set the parent
    shell's env — decisions 2026-07-20)."""
    project = resources.resolve_project(args)
    maps_dir = Path(config.project_maps_dir(project))
    name = args.name
    # Leading dot rejected too: `maps/.locks/` is the (self-ignored) lock home — a dotted level
    # would nest inside/beside it and silently hide from git (review fix, 2026-07-18).
    if not name or "/" in name or "\\" in name or name in (".", "..") or name.startswith("."):
        print(f"invalid level name: {name!r}", file=sys.stderr)
        return 2
    level_dir = maps_dir / name
    actors_dir = level_dir / "actors"
    if actors_dir.is_dir() and any(actors_dir.iterdir()):
        print(f"level already exists: {name} (has actors at {actors_dir})", file=sys.stderr)
        return 2
    level = parse_t3d("Begin Map\nBegin Actor Class=Engine.LevelInfo Name=LevelInfo\n"
                      "    Name=\"LevelInfo\"\nEnd Actor\nEnd Map")
    level.order = list(level.actors)
    ranks = {n: trunk.append_rank({}) for n in level.actors}
    trunk.write_level(level_dir, level, ranks)
    print(f"created level: {name}")
    print(f"to edit it: export UEDCLI_LEVEL={name}", file=sys.stderr)
    return 0


def _resolve_import_dest(args, project) -> tuple[str, object, str]:
    """Resolve `level import`'s `--tree KIND/NAME` DESTINATION, which the import CREATES.

    Returns `(kind, handle, name)` — `("level", <level dir Path>, name)` or
    `("stash", <StashRegister>, name)`.

    This is deliberately NOT `level_sources.resolve_level_source`: that one resolves a box that must ALREADY
    exist and errors otherwise, which is the exact opposite of what an import needs. `prefab` is
    rejected outright — a prefab is a small reusable fragment, not somewhere to put a whole level.

    **The overwrite guard runs here, before the map file is read**, so refusing costs nothing and
    touches nothing. "Already exists" for a level means its `actors/` directory holds something: an
    empty or half-created directory does not count, matching `level create`'s rule, so a previous
    failed run does not need `--overwrite` to retry.
    """
    tgt = args.tree
    kind, sep, name = tgt.partition("/")
    if not sep or not name or kind not in ("level", "stash"):
        raise CommandError(
            f"--tree must be level/NAME or stash/NAME for an import, got {tgt!r}"
            + (" (a prefab is not a valid import destination — import a level or a stash)"
               if kind == "prefab" else ""))
    # MANDATORY before building any path from NAME: neither the register nor the trunk validates
    # the top-level name, so `stash/../../x` would otherwise escape the project.
    try:
        stashlib.validate_member_name(name)
    except ValueError as e:
        raise CommandError(str(e))
    if kind == "stash":
        reg = stash_register.for_project(project)
        if reg.exists(name) and not args.overwrite:
            raise CommandError(f"stash already exists: {name!r} — pass --overwrite to replace it")
        return "stash", reg, name
    # A level name is a SINGLE safe segment, unlike a nested stash id: `validate_member_name` allows
    # `/`, so re-check, or a nested name would scatter lock homes / collide with `maps/.locks/`.
    try:
        level_sources.check_safe_level(name)
    except LevelSelectionError as e:
        raise CommandError(str(e))
    level_dir = Path(config.project_maps_dir(project)) / name
    actors_dir = level_dir / "actors"
    if actors_dir.is_dir() and any(actors_dir.iterdir()) and not args.overwrite:
        raise CommandError(f"level already exists: {name} (has actors at {actors_dir}) — "
                             "pass --overwrite to replace it")
    return "level", level_dir, name


def _level_import(args) -> int:
    """`level import MAPFILE --tree level|stash/NAME [--overwrite]` — decode a COMPILED map file
    into a new T3D tree, with no editor, no container and no game in the path.

    This is the inverse of `level materialize`. Materialize drives UnrealEd to turn the tracked T3D
    tree into a compiled `.dx`/`.unr`; import reads such a file's bytes directly and reconstructs
    the same per-actor T3D the editor's own export would write, so an existing map becomes
    queryable, diffable and editable with the ordinary verbs.

    The pipeline, in order, and why each step sits where it does:

    1. **Resolve the destination and run the overwrite guard** — before reading anything, so a
       refusal is free (`_resolve_import_dest`).
    2. **Load the map package** and decode it to `Begin Map … End Map` text (`mapimport`). Any
       malformed byte in the file surfaces as a named error, never a traceback out of a binary
       parser.
    3. **Parse that text into a level**, reusing the same parser every other ingest path uses, so
       the import cannot produce a level shape the rest of the tool would not accept.
    4. **Drop the editor's scratch objects** — the builder brush and the viewport cameras. This
       MUST precede step 5: both are recognised by their SHORT class name, which step 5 rewrites.
    5. **Validate strictly** — qualify every class name to its fully-qualified form, confirm each
       class and each polygon texture really exists on the project's package path, and fail the
       whole import naming the offender if any does not. An import that quietly kept unresolvable
       references would produce a tree that cannot be rebuilt.
    6. **Write the destination** — a level trunk or a stash entry.

    Output follows the producer convention: the imported actor names go to stdout one per line
    (pipe them onward), the human summary to stderr.
    """
    # (1) destination + overwrite guard FIRST — nothing is read until this passes.
    project = resources.resolve_project(args)
    kind, handle, dest_name = _resolve_import_dest(args, project)

    mapfile = Path(args.mapfile)
    if not mapfile.is_file():
        raise CommandError(f"map file not found: {args.mapfile}")

    # (2) decode. The class packages are needed for every property's declared type and for the
    # class defaults the struct member-strip compares against. `resources.class_index` is the one seam that
    # reaches the game's `.u` set, and it raises its own clean error when there is no package path —
    # so this does not repeat the check that step 5's validation already owns.
    index = resources.class_index(project)
    from ... import mapimport, upackage
    try:
        pkg = upackage.load_package(str(mapfile), name=mapfile.stem)
    except SchemaError as e:
        raise CommandError(f"{args.mapfile}: {e}")
    # `notes` collects what the decode SKIPPED (off-roster actor objects, a doubly-listed
    # actor). They are reported on stderr below: skipping is only legitimate if it is said.
    notes: list[str] = []
    text = mapimport.import_map(pkg, index, mapimport.ImportSchema(resolver=index.resolver()),
                                notes=notes)

    # (3) parse. Parse to a LIST first: the level dict is keyed by actor Name, so two exports
    # sharing a name would silently collapse into one and the import would report success while
    # having dropped content.
    ordered = parse_t3d_actors(text)
    seen: set[str] = set()
    dups = sorted({a.name for a in ordered if a.name in seen or seen.add(a.name)})
    if dups:
        raise CommandError(
            f"{args.mapfile}: {len(dups)} actor name(s) appear more than once and would collapse "
            f"into a single actor: {', '.join(dups[:10])}" + (" …" if len(dups) > 10 else ""))
    level = Level(actors={a.name: a for a in ordered}, order=[a.name for a in ordered])

    # (4) the editor's own apparatus, BEFORE qualification (step 5) makes it unrecognisable.
    dropped = mapimport.drop_editor_scratch(level)

    # (5) strict validation — classes qualified + existence-checked, textures existence-checked.
    ingest.validate_ingest_actors(list(level.actors.values()), args)

    # (6) write.
    if kind == "level":
        level_dir = handle
        assert isinstance(level_dir, Path)
        existing, _ranks = trunk.read_level(level_dir)
        stale = set(existing.actors) - set(level.actors)
        ranks: dict[str, str] = {}
        for n in level.order:
            ranks[n] = trunk.append_rank(ranks)
        # `write_level` is a DELTA write that leaves unlisted actor dirs alone (per-actor dirs let
        # concurrent edits compose), so an --overwrite of a level that had OTHER actors must name
        # them as deletions or they would linger and silently merge into the imported level.
        trunk.write_level(level_dir, level, ranks, deleted=frozenset(stale))
    else:
        reg = handle
        full = {n: canonical_actor_t3d(level.actors[n]) for n in level.order}
        reg.write_stash(
            dest_name, full_level=full, order=list(level.order),
            packages=sorted(stashlib.referenced_packages(list(level.actors.values()))),
            meta={"source_map": mapfile.name, "ts": int(time.time() * 1000)},
            folders={n: None for n in level.order}, force=True)

    for n in level.order:
        print(n)
    note = f"imported {len(level.actors)} actor(s) from {mapfile.name} into {kind}: {dest_name}"
    if dropped:
        note += f"; dropped {len(dropped)} editor scratch object(s) ({', '.join(dropped[:6])}" \
                + (" …" if len(dropped) > 6 else "") + ")"
    print(note, file=sys.stderr)
    for n in notes:
        print(f"note: {n}", file=sys.stderr)
    if kind == "level":
        print(f"to edit it: export UEDCLI_LEVEL={dest_name}", file=sys.stderr)
    return 0


def _level_reimport(args) -> int:
    """`level reimport MAPFILE --tree level/NAME [--force]` — fold a hand-edited COMPILED map back
    into the EXISTING trunk that produced it, matching actors by name so unrelated actors,
    folders/labels and CSG order are left untouched.

    Unlike `level import`, the destination must already exist (`level_sources.resolve_level_only`
    — the same level-only resolver `materialize`/`photo` use, so the ambient `$UEDCLI_LEVEL` is
    the default target and a mutation from it is announced once, same as any other trunk write).

    The pipeline:
    1. Resolve the level (must exist) and decode the map file — identical to `level import`'s
       steps 2-5 (`mapimport.import_map` -> parse -> drop editor scratch -> validate).
    2. Diff the decode against the trunk's current on-disk `Level`, by actor name
       (`reimport_ops.diff_actors`).
    3. The blast-radius guard: refuse (exit 2) unless `--force` if more than 20% of the trunk's
       actors would be modified or deleted (`reimport_ops.blast_radius_exceeded`).
    4. Recompute brush `order_value`s only (`reimport_ops.compute_brush_ranks`); point actors and
       unmodified brushes keep their existing rank untouched.
    5. Write through the ordinary trunk delta path (`trunk.write_level`), touching only the actors
       that actually changed body or rank.

    See dev/docs/board/to-plan/level-reimport-reimport-a-hand-edited-dx-unr/spec.md.
    """
    from ... import reimport_ops

    project = resources.resolve_project(args)
    name, from_env = level_sources.resolve_level_only(args, verb="level reimport")
    if from_env:
        level_sources.announce_env_level(name, action="reimporting into")
    level_dir = Path(config.project_maps_dir(project)) / name

    mapfile = Path(args.mapfile)
    if not mapfile.is_file():
        raise CommandError(f"map file not found: {args.mapfile}")

    # decode — identical to `level import` steps 2-5.
    index = resources.class_index(project)
    from ... import mapimport, upackage
    try:
        pkg = upackage.load_package(str(mapfile), name=mapfile.stem)
    except SchemaError as e:
        raise CommandError(f"{args.mapfile}: {e}")
    notes: list[str] = []
    text = mapimport.import_map(pkg, index, mapimport.ImportSchema(resolver=index.resolver()),
                                notes=notes)
    ordered = parse_t3d_actors(text)
    seen: set[str] = set()
    dups = sorted({a.name for a in ordered if a.name in seen or seen.add(a.name)})
    if dups:
        raise CommandError(
            f"{args.mapfile}: {len(dups)} actor name(s) appear more than once and would collapse "
            f"into a single actor: {', '.join(dups[:10])}" + (" …" if len(dups) > 10 else ""))
    new_level = Level(actors={a.name: a for a in ordered}, order=[a.name for a in ordered])
    dropped = mapimport.drop_editor_scratch(new_level)
    ingest.validate_ingest_actors(list(new_level.actors.values()), args)

    # diff against the existing trunk.
    existing_level, existing_ranks = trunk.read_level(level_dir)
    diff = reimport_ops.diff_actors(existing_level, new_level)

    # Folder/label sidecars have no compiled-map equivalent — carry them over from the trunk for
    # every matched actor whose body changed (spec: "Folder/label sidecars are left untouched").
    for n in diff.changed:
        new_level.actors[n].folder = existing_level.actors[n].folder
        new_level.actors[n].labels = existing_level.actors[n].labels

    # Mark every newly added actor with one shared, per-invocation label so they're easy to find
    # and review afterward (owner decision, 2026-08-29) — `actor find --label reimport-<hex>`.
    reimport_label = None
    if diff.added:
        reimport_label = f"reimport-{secrets.token_hex(3)}"
        for n in diff.added:
            new_level.actors[n].labels = frozenset({reimport_label})

    if reimport_ops.blast_radius_exceeded(diff, len(existing_level.actors)) and not args.force:
        blast = len(diff.modified) + len(diff.deleted)
        pct = 100 * blast / len(existing_level.actors)
        raise CommandError(
            f"reimport would modify/delete {blast}/{len(existing_level.actors)} actors "
            f"({pct:.0f}%, over the 20% guard) — pass --force to proceed "
            f"({len(diff.modified)} modified, {len(diff.deleted)} deleted)")

    for n in sorted(diff.modified):
        old_cls = existing_level.actors[n].cls
        new_cls = new_level.actors[n].cls
        if old_cls != new_cls:
            print(f"note: {n} changed class {old_cls} -> {new_cls}", file=sys.stderr)

    # order_value: brushes only (point actors and unmoved brushes keep their existing rank).
    brush_ranks = reimport_ops.compute_brush_ranks(existing_ranks, new_level, diff)
    ranks = dict(existing_ranks)
    ranks.update(brush_ranks)
    for n in sorted(diff.added):
        if new_level.actors[n].brush is None:          # new POINT actors: append-after-all
            ranks[n] = trunk.append_rank(ranks)

    only = diff.changed | {n for n in new_level.actors if ranks.get(n) != existing_ranks.get(n)}
    trunk.write_level(level_dir, new_level, ranks, deleted=diff.deleted, only=only)

    for n in new_level.order:
        print(n)
    print(f"reimported {len(new_level.actors)} actor(s) from {mapfile.name} into level: {name} "
          f"({len(diff.added)} added, {len(diff.deleted)} deleted, {len(diff.changed)} changed)",
          file=sys.stderr)
    if reimport_label:
        print(f"note: {len(diff.added)} added actor(s) labeled '{reimport_label}' — "
              f"`actor find --label {reimport_label}` to review them", file=sys.stderr)
    if dropped:
        print(f"note: dropped {len(dropped)} editor scratch object(s) ({', '.join(dropped[:6])}"
              + (" …" if len(dropped) > 6 else "") + ")", file=sys.stderr)
    for n in notes:
        print(f"note: {n}", file=sys.stderr)
    return 0


def _level_list(args) -> int:
    """`level list` — enumerate the project's levels (trunk dirs under <maps>), one name per line to
    stdout (the producer convention — pipe-friendly), a count + the ambient `$UEDCLI_LEVEL` to stderr.
    `--json` emits a JSON array of {name, active} to stdout. Needs a project but NO ambient level
    (routed before the trunk-level resolution, like `project show`). The marker reads the RAW env
    (stripped, unvalidated): `level list` is exactly the command you'd run to NOTICE a bad export, so
    it must never itself error/crash on one — a malformed or stale value simply shows as `(not
    listed)`, never a `LevelSelectionError`."""
    project = resources.resolve_project(args)
    maps_dir = Path(config.project_maps_dir(project))
    levels = level_sources.list_levels(maps_dir)
    active = (os.environ.get("UEDCLI_LEVEL") or "").strip() or None   # raw; never validated here
    if getattr(args, "json", False):
        import json
        print(json.dumps([{"name": n, "active": n == active} for n in levels]))
    else:
        for n in levels:
            print(n)
    # Keep the stderr note consistent with the listing/JSON: a stale/bad $UEDCLI_LEVEL (its level
    # since deleted, its actors/ tree removed, or a malformed value) is flagged as not-listed, not
    # silently reported as present — otherwise stderr would name an "active" level absent from stdout.
    if not active:
        act_note = "no level set ($UEDCLI_LEVEL unset)"
    elif active in levels:
        act_note = f"$UEDCLI_LEVEL={active}"
    else:
        act_note = f"$UEDCLI_LEVEL={active} (not listed)"
    print(f"{len(levels)} level(s); {act_note}", file=sys.stderr)
    return 0


def _level_status(args) -> int:
    import json
    project = resources.resolve_project(args)
    root = Path(project.root)
    target = getattr(args, "tree", None)
    want_json = getattr(args, "json", False)
    # The friendly "no level" hint (a 0-exit, not an error) applies ONLY when defaulting with NO
    # ambient level set. With an explicit --tree there's a target; with a SET-but-bad $UEDCLI_LEVEL
    # the resolve below raises the real exit-2 error (a stale export is a mistake worth surfacing).
    if target is None and not (os.environ.get("UEDCLI_LEVEL") or "").strip():
        if want_json:
            print(json.dumps({"selected": None}))   # explicit null so a script can detect "no level"
        else:
            print(level_sources.NO_LEVEL_MSG)
        return 0
    # An explicit --tree (incl. "") is NOT the friendly-hint path — it resolves below, so `--tree ""`
    # errors ("must be KIND/NAME") instead of silently reading the ambient level.
    src = level_sources.resolve_level_source(args)               # honors --tree; else the ambient level (bad → exit 2)
    level = src.load()                              # populates src._ranks (trunk) / leaves it {} (box)
    total, brushes, points = _level_actor_counts(level)
    dups = trunk.duplicate_ranks(src._ranks)        # a box has no order_value sidecar → {} → no warning
    # The git hint is a level-trunk concept only (a stash/prefab box has no repo); None for a box.
    git_hint = _git_hint(root, src.trunk_dir) if isinstance(src, level_sources.TrunkLevelSource) else None
    # Texture-only: class/mesh/sound packages aren't string-derivable from a T3D (referenced_packages).
    pkgs = sorted(stashlib.referenced_packages(list(level.actors.values())))
    if want_json:
        print(json.dumps({
            "kind": src.kind, "name": src.display_name,
            "actors": {"total": total, "brush": brushes, "point": points},
            "duplicate_order_values": len(dups),
            "git": git_hint,                        # the one-line hint string, or null (box / git absent)
            "texture_packages": pkgs,
        }, indent=2))
        return 0
    print(f"{src.kind}: {src.display_name}")        # e.g. "level: castle", "stash: bay", "prefab: door"
    print(f"actors: {total}  ({brushes} brush, {points} point)")
    if dups:
        print(f"WARNING: {len(dups)} order_value(s) shared by 2+ actors — arbitrary CSG order; "
              "run `level doctor`")
    if git_hint:
        print(git_hint)
    print(f"texture packages: {', '.join(pkgs) if pkgs else '(none referenced)'}")
    return 0


def _level_materialize(args) -> int:
    from ... import apply, packages
    if not args.out:                                    # check before computing the load set
        print("level materialize requires --out <path>", file=sys.stderr)
        return 2
    project = resources.resolve_project(args)
    maps_dir = Path(config.project_maps_dir(project))
    # Level-only: `--tree level/<name>` or the ambient $UEDCLI_LEVEL (a stash/prefab has no world to
    # build). Announce the level when it came from the env — materialize WRITES a map, so a stale
    # export would silently build the wrong level (decisions 2026-07-20).
    name, from_env = level_sources.resolve_level_only(args, verb="materialize")
    if from_env:
        level_sources.announce_env_level(name, action="materializing")
    src = level_sources.TrunkLevelSource(maps_dir / name)
    level = src.load()
    # Advisory (owner 2026-08-02): a level that references no loadable package AND composes 0 packages
    # is a likely games-config misconfiguration — but a valid reference-free greybox still builds, so
    # note it and continue (rc unaffected). The hard guarantee is `run_materialize`'s referenced-package
    # gate; this fires only when there is genuinely nothing to drop.
    referenced = [p for p in apply._level_referenced_packages(level)
                  if p not in packages._ALWAYS_LOADED]
    if not referenced and not resources.composed_load_set(project):
        print("note: composed package search path resolved 0 packages — check the games config "
              "paths", file=sys.stderr)
    dups = trunk.duplicate_ranks(src._ranks)
    if dups:
        print(f"WARNING: {len(dups)} order_value(s) shared by 2+ actors — arbitrary CSG order; "
              "run `level doctor`", file=sys.stderr)
    result = apply.run_materialize(level=level,
                                   search_dirs=resources.composed_dirs(project),
                                   schema_resolver=resources.schema_resolver_for(project),
                                   out_path=args.out, overwrite=args.overwrite,
                                   state_dir=config.state_dir(project.root, create=True),
                                   no_verify=getattr(args, "no_verify", False),
                                   keep_build=getattr(args, "keep_build", False),
                                   no_bsp_check=getattr(args, "no_bsp_check", False),
                                   ignore_props=resources.ignore_props_for(project),
                                   pathing=resources.resolved_pathing(project))
    if result.rc != 0:
        print(result.message, file=sys.stderr)
        return result.rc
    print(result.message)
    if result.bsp_notes:                                # advisory BSP health → stderr, rc unchanged
        print(result.bsp_notes, file=sys.stderr)
    return 0


def _level_paths_define(args) -> int:
    """`level paths define` — UED22's `createPaths` auto-placement over the trunk (spec §5), the
    native world build + mover models as the collision world. Created and moved names to stdout
    (producer convention); stripped names and counts to stderr."""
    from ...classdefaults import ClassDefaults
    from ...classindex import ClassRefError
    from ...native.materialize import NativeBuildError
    from ...native import pathplace
    verb = "level paths define"
    project = resources.resolve_project(args)
    if resources.pathing_for(project, verb=verb) == "none":
        raise CommandError(f'{verb}: [games.{project.game}].pathing is "none" -- placement needs '
                           f"the reachability test; set it to deusex-1112fm or ued22-469")
    maps_dir = Path(config.project_maps_dir(project))
    name, from_env = level_sources.resolve_level_only(args, verb=verb)
    if from_env:
        level_sources.announce_env_level(name, action="placing path nodes in")
    index = resources.class_index(project)
    if index.empty:
        raise CommandError(f"{verb}: {resources.NO_PACKAGE_PATH}")
    src = level_sources.TrunkLevelSource(maps_dir / name)
    level = src.load()
    try:
        result = pathplace.define_paths(
            level, index=index, defaults=ClassDefaults(resources.schema_resolver_for(project)))
    except (pathplace.PathPlaceError, NativeBuildError, ClassRefError, SchemaError) as e:
        raise CommandError(f"{verb}: {e}")
    src.save(verb="paths define", args={}, level=level,
             touched=[*result.created, *result.moved])
    for n in result.stripped:
        print(f"removed previous auto node: {n}", file=sys.stderr)
    for n in [*result.created, *result.moved]:
        print(n)
    print(f"batch label: {result.token}", file=sys.stderr)
    print(f"starts walked: {result.starts}; created: {len(result.created)}; "
          f"merged: {len(result.removed)}; moved: {len(result.moved)}; "
          f"removed: {len(result.stripped) + len(result.removed)}", file=sys.stderr)
    return 0


def _level_preview(args) -> int:
    """`level photo` — freely-posed still shots of the current level. The DEFAULT backend
    is `--game` (the faithful tier, spec 2026-07-13): it delivers the map into a WARM per-user
    headless-game container and captures truly-lit first-person frames (real lighting/sky/
    meshes). `--native` is the opt-in offline DRAFT tier (spec 2026-07-16): the Rust CSG core
    carves the trunk in-process and software-rasterizes flat-shaded stills — fast, no editor/
    container/game, but no lighting/meshes/sky. `use_game = not args.native` picks the tier
    (the two flags are mutually exclusive; neither given ⇒ game). All SHOT tokens validate up
    front, all-or-nothing, before any work."""
    from ...preview_native import DEFAULT_FOV, NativePreviewError, render_shots
    from ...preview_shots import parse_shot

    use_game = not args.native          # --game is the DEFAULT tier; --native is the opt-in draft

    if use_game and args.fov is not None:
        print("--fov requires --native (the in-game tier renders at the game's own FOV)",
              file=sys.stderr)
        return 2
    if use_game and args.faces is not None:
        print("--faces requires --native (the in-game tier renders solid lit faces, "
              "not a wireframe)", file=sys.stderr)
        return 2
    if not use_game:
        for value, flag in ((args.map, "--map"), (args.rebuild, "--rebuild"),
                            (args.keep_alive, "--keep-alive")):
            if value:
                print(f"{flag} requires --game (the in-game photo tier)", file=sys.stderr)
                return 2
    # `--tree` selects a TRUNK level; `--map` renders a retail map file — the two are mutually
    # exclusive (a --map photo never resolves a trunk level, so a --tree would be silently ignored).
    if getattr(args, "tree", None) and args.map:
        print("--tree names a trunk level; it cannot be combined with --map (a retail map file)",
              file=sys.stderr)
        return 2
    m = re.fullmatch(r"(\d+)x(\d+)", args.size.strip())
    if not m or int(m.group(1)) < 1 or int(m.group(2)) < 1:
        print(f"invalid --size {args.size!r}: expected WxH in pixels, e.g. 1280x960",
              file=sys.stderr)
        return 2
    size = (int(m.group(1)), int(m.group(2)))
    list_cls = getattr(args, "list_actors", None)
    if list_cls:
        if not use_game or not args.map:
            print("--list-actors is a --game --map query (it inspects a retail map's actors)",
                  file=sys.stderr)
            return 2
        if args.shots:
            print("--list-actors is a query — drop the SHOT tokens", file=sys.stderr)
            return 2
    else:
        if not args.out_dir:
            print("--out-dir is required (unless --list-actors)", file=sys.stderr)
            return 2
        if not args.shots:
            print("need at least one SHOT token (or use --list-actors to discover @Actor refs)",
                  file=sys.stderr)
            return 2
    if getattr(args, "sample", 0):
        if not list_cls:
            print("--sample only applies with --list-actors", file=sys.stderr)
            return 2
        if args.sample < 0:
            print(f"--sample must be >= 0, got {args.sample}", file=sys.stderr)
            return 2
    try:
        shots = [parse_shot(t) for t in args.shots]         # all-or-nothing (exit 2)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2

    project = resources.resolve_project(args)
    user_config = config.load_user_config()
    if user_config is None:                                 # same hard error as materialize
        print("no per-user games config (~/.uedcli/config.toml): photo resolves packages "
              "over the game's base paths; create it with a [games.<name>] paths dir list",
              file=sys.stderr)
        return 2

    if use_game:
        from ...preview_game import GamePreviewError
        from ... import preview_game
        if list_cls:                            # QUERY mode: print the map's actors, no screenshots
            try:
                out = preview_game.list_actors(
                    project=project, user_config=user_config, game=project.game,
                    map_path=args.map, cls=list_cls, sample=getattr(args, "sample", 0))
            except GamePreviewError as e:
                print(str(e), file=sys.stderr)
                return 2
            sys.stdout.write(out)
            return 0
        level = name = None
        if args.map is None:                    # trunk mode needs a level (--map renders a retail map)
            maps_dir = Path(config.project_maps_dir(project))
            name, _ = level_sources.resolve_level_only(       # level-only; photo is a READ → no echo
                args, verb="photo",
                alt_hint="use `stash diagram` / `prefab diagram` to render a captured set")
            level = level_sources.TrunkLevelSource(maps_dir / name).load()

        def _provide_resources():
            # The project-resolved materialize inputs, built ONLY when the preview backend actually
            # needs them (a trunk cache miss) — never for `--map` or a cache hit.
            dirs = resources.composed_dirs(project)
            schema = resources.schema_resolver_for(project)
            return preview_game.MaterializeResources(
                composed_dirs=dirs, schema_resolver=schema,
                pathing=resources.resolved_pathing(project))

        try:
            n = preview_game.render_shots(
                shots=shots, out_dir=Path(args.out_dir), size=size, project=project,
                user_config=user_config, game=project.game, provide_resources=_provide_resources,
                level=level, level_name=name,
                map_path=args.map, rebuild=args.rebuild, keep_alive=args.keep_alive)
        except GamePreviewError as e:
            print(str(e), file=sys.stderr)
            return 2
        print(f"wrote {n} shot(s) to {args.out_dir}")
        return 0

    maps_dir = Path(config.project_maps_dir(project))
    name, _ = level_sources.resolve_level_only(               # native draft is always trunk mode; READ → no echo
        args, verb="photo",
        alt_hint="use `stash diagram` / `prefab diagram` to render a captured set")
    src = level_sources.TrunkLevelSource(maps_dir / name)
    level = src.load()

    if (args.faces or "textured") == "wire":
        # wire is a content-free schematic: no CSG solve, no class hierarchy (mover-ness is
        # name-guessed), no native extension. Point-actor render data is resolved HERE (dispatch owns
        # schema/texture resolution) and passed down, keeping preview_wire resolver-free.
        from .. import rendering
        from ... import preview_wire
        points = rendering._preview_point_data(list(level.actors.values()), args, set())
        try:
            n = preview_wire.render_shots(
                level=level, shots=shots, out_dir=Path(args.out_dir), points=points, size=size,
                fov=args.fov if args.fov is not None else DEFAULT_FOV)
        except NativePreviewError as e:
            print(str(e), file=sys.stderr)
            return 2
        print(f"wrote {n} shot(s) to {args.out_dir}")
        return 0

    search_files = config.composed_search_files(project, user_config)
    try:
        n = render_shots(level=level, shots=shots, out_dir=Path(args.out_dir), size=size,
                         fov=args.fov if args.fov is not None else DEFAULT_FOV,
                         search_files=search_files,
                         index=resources.mover_index(args, "level photo --native", project=project))
    except NativePreviewError as e:
        print(str(e), file=sys.stderr)
        return 2
    print(f"wrote {n} shot(s) to {args.out_dir}")
    return 0


def _level_doctor(args, src) -> int:
    """Static, offline BSP/geometry lint (no editor). Exit code reflects ALL findings (a
    suppressed-from-display ERROR still fails); --severity/--category filter DISPLAY only. Reads the
    box via the LevelSource seam — $UEDCLI_LEVEL by default, or a `--tree level|stash|prefab`
    box (a stash/prefab has no order_value sidecar, so `_ranks` is empty → no duplicate-order finding,
    which is correct: a box doesn't carry CSG precedence)."""
    import json
    from ... import doctor

    level = src.load()
    level_name = src.display_name
    findings = doctor.sort_findings(
        doctor.run_doctor(level, resources.mover_index(args, "level doctor"))
        + doctor.check_duplicate_order(src._ranks))
    exit_severity = doctor.worst(findings)        # over ALL findings, before display filtering

    if args.categories:
        valid_cf = {c.casefold(): c for c in doctor.CATEGORIES}
        for v in args.categories:                 # first value matching nothing is named (all-or-nothing)
            if v.casefold() not in valid_cf:
                raise CommandError(f"no category {v!r}; valid: {', '.join(sorted(doctor.CATEGORIES))}")
        wanted = {v.casefold() for v in args.categories}
        shown = [f for f in findings if f.category.casefold() in wanted]
    else:
        shown = findings
    if args.severity:
        floor = doctor._RANK[doctor.Severity(args.severity)]
        shown = [f for f in shown if doctor._RANK[f.severity] >= floor]

    if args.json:
        print(json.dumps([{**f.__dict__, "severity": f.severity.value} for f in shown], indent=2))
    else:
        print(doctor.format_report(shown, level_name))
    return 1 if exit_severity is doctor.Severity.ERROR else 0

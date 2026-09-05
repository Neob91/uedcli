"""Project and game-resource resolution shared across command families.

The public seams here (`resolve_project`, `composed_dirs`, `class_defaults`, `mover_index`, and the
rest) are what command families and cross-family orchestrators call, and what tests patch. Callers
use module-qualified lookup (`resources.mover_index(...)`) so an owner-module patch replaces them.
See spec "Cross-family seams → Resources". Resolution stays lazy: a command that needs no project,
schema, texture or index must not start needing one because code moved here.
"""
from __future__ import annotations

import os
from pathlib import Path

from .. import audioindex, classindex, config, packages, propedit, rotation, uprops, utexture
from ..uprops import SchemaError
from .errors import CommandError, ProjectError


def resolve_project(args) -> config.Project:
    """Resolve the current project (--project > UEDCLI_PROJECT > walk-up from cwd to the nearest
    `uedcli.toml`). Errors clearly if none is found — every level/content verb needs a project. On
    the failure path only, a cheap child-dir scan detects a RETIRED old-layout project
    (`<child>/config.toml`) and names the migration (spec 2026-07-17 §8)."""
    proj = config.resolve_project(
        project_flag=getattr(args, "project", None),
        env_project=os.environ.get("UEDCLI_PROJECT"),
        cwd=os.getcwd(),
    )
    if proj is None:
        msg = ("not in a uedcli project (no uedcli.toml found here or above); "
               "pass --project <root>")
        old = config.find_old_layout_project_dir(os.getcwd())
        if old:
            parent = os.path.dirname(old)
            msg += (f"\nfound old-layout project dir {old}/ — this layout is retired; move its "
                    f"config.toml to {os.path.join(parent, 'uedcli.toml')} (see docs) and delete "
                    f"its tmp/")
        raise ProjectError(msg)
    return proj

def prefab_root(args):
    """The prefab library root: the explicit `--prefab-dir` override, else the resolved project's
    `prefabs` dir (`uedcli.toml` `prefabs` key, default `<root>/prefabs/`). With neither a flag nor
    a project → clean `ProjectError` exit 2 (spec 2026-07-17 §6 — the old repo-root/env fallback
    is retired, so prefab verbs outside a project need the flag)."""
    if getattr(args, "prefab_dir", None):
        return Path(args.prefab_dir)
    return Path(config.project_prefabs_dir(resolve_project(args)))

def composed_load_set(project) -> list[str]:
    """The whole composed-search-path load set for materialize/preview (decision 2026-07-05 23:00):
    config.composed_search_files (project overlay shadows game base) → bare package names for
    ensure_load. Hard-errors without a per-user games config (decision 2026-07-06 05:12)."""
    from ..packages import search_path_package_names
    user_config = config.load_user_config()
    if user_config is None:                             # hard error — decision 2026-07-06 05:12
        raise ProjectError(
            "no per-user games config (~/.uedcli/config.toml): materialize needs the game's base "
            "package paths; create it with a [games.<name>] paths dir list")
    return search_path_package_names(config.composed_search_files(project, user_config))

def composed_dirs(project) -> list[str]:
    """The WHOLE composed config dir set (host) that becomes the editor/game/build `/resources/<n>`
    mounts for materialize/preview (one uniform set — dev/docs/direction/containers.md 2026-07-14, no content-vs-code
    split). `/stubs` is first on the crafted Paths, so a v69 stub shadows any same-named v68 `.u` a
    code dir contributes. Hard-errors without a per-user games config (decision 2026-07-06 05:12)."""
    user_config = config.load_user_config()
    if user_config is None:                             # hard error — decision 2026-07-06 05:12
        raise ProjectError(
            "no per-user games config (~/.uedcli/config.toml): materialize needs the game's base "
            "package paths; create it with a [games.<name>] paths dir list")
    return config.composed_search_dirs(project, user_config)


def ignore_props_for(project) -> tuple[str, ...]:
    """The game's `ignore_props` (`Package.Class.prop` the post-verify ignores — authored props the
    game's engine adds to a base class the materialize editor's engine package lacks). Empty when no
    games config resolves (the verify then compares every authored prop)."""
    user_config = config.load_user_config()
    if user_config is None:
        return ()
    try:
        return config.select_substrate(project, user_config).ignore_props
    except config.ConfigError:
        return ()


def texture_resolver(project, class_index=None):
    """A `utexture.TextureResolver` over the project's composed package files, or None when no
    config / no packages (a sprite then can't resolve → its actor degrades to a marker). MOCKABLE
    seam (tests patch it offline). Tolerant of a broken/absent games config (returns None).

    `class_index` WIDENS which exports the resolver treats as textures from the exact `Texture`
    class to every `Engine.Texture` descendant — the asset catalog passes it (so procedurals and
    subclasses resolve and enumerate); every other caller (actor/sprite preview) leaves it None and
    keeps the exact match."""
    try:
        user_config = config.load_user_config()
        if user_config is None:
            return None
        files = config.composed_search_files(project, user_config)
    except config.ConfigError:
        return None
    if not files:
        return None
    return utexture.TextureResolver(files, class_index=class_index)

def class_schema(cls: str, project=None) -> dict:
    """{casefold(name): Prop} for `cls`, extracted offline from the real game `.u` (P1). Raises
    `uprops.SchemaError` on an unbuildable/unknown schema — no fallback (decision 2026-06-26 14:10).
    The schema SEAM: tests patch this to run offline without the gitignored v68 install.

    The schema code path is the config-driven code dirs (dev/docs/direction/containers.md 2026-07-14 03:30 — same
    source stubs come from). `project` is the invocation's RESOLVED project, threaded from the
    `actor prop` handler so a `--project <dir>` override reaches the schema path (asset-wiring Part
    B); if omitted it is re-resolved from cwd/env (any direct/legacy caller). A `None` project or
    absent games config → an empty code path → a clean `SchemaError` miss. A PRESENT-but-broken
    config (malformed TOML, ambiguous project, or a game named by the project but missing from the
    games config) raises `config.ConfigError` here, which `dispatch()` catches → exit 2 (never a
    traceback either way)."""
    if project is None:
        project = config.resolve_project(env_project=os.environ.get("UEDCLI_PROJECT"),
                                         cwd=os.getcwd())
    user_config = config.load_user_config()
    resolver = packages.schema_resolver(project, user_config)
    return {p.name.casefold(): p for p in uprops.resolve_class_properties(cls, resolver=resolver)}

def schema_resolver_for(project):
    """The schema-path resolver for `project` (None → cwd/env re-resolution), shared by the
    defaults/struct-member/enum seams below."""
    if project is None:
        project = config.resolve_project(env_project=os.environ.get("UEDCLI_PROJECT"),
                                         cwd=os.getcwd())
    return packages.schema_resolver(project, config.load_user_config())

def class_defaults(cls: str, project=None) -> dict:
    """{(casefold(prop), array_index): canonical text} — the class's EFFECTIVE defaults, every
    ancestor's defaults block overlaid root→leaf, decoded offline from the game's own `.u`
    (uprops.resolve_class_defaults; spec §5.2). The second MOCKABLE seam beside `class_schema`
    — tests patch it to run offline. Raises `uprops.SchemaError` when unbuildable (no
    fallback)."""
    return uprops.resolve_class_defaults(cls, resolver=schema_resolver_for(project))

def struct_members(prop, project=None) -> list:
    """A StructProperty's ORDERED member Props (uprops.struct_members via the declaring
    package) — powers dot-path member validation + struct rendering. Mockable seam."""
    resolver = schema_resolver_for(project)
    pkgs: dict = {}
    owner_pkg_name = prop.owner.split(".", 1)[0]
    path = resolver(owner_pkg_name)
    if path is None:
        raise SchemaError(f"package {owner_pkg_name!r} not found on the schema search path "
                          f"(needed to resolve {prop.owner}.{prop.name})")
    dp = uprops.load_package(path, name=owner_pkg_name)
    tp, ti = uprops.resolve_type_export(dp, prop.type_ref, "Struct",
                                         resolver=resolver, _pkgs=pkgs)
    return uprops.struct_members(tp, ti, owner=prop.type_name or prop.name)

def enum_names(prop, project=None) -> tuple:
    """A ByteProperty's enum value names, cross-package (spec §4). Mockable seam."""
    resolver = schema_resolver_for(project)
    owner_pkg_name = prop.owner.split(".", 1)[0]
    path = resolver(owner_pkg_name)
    if path is None:
        raise SchemaError(f"package {owner_pkg_name!r} not found on the schema search path "
                          f"(needed to resolve {prop.owner}.{prop.name})")
    dp = uprops.load_package(path, name=owner_pkg_name)
    return uprops.resolve_enum_names(prop, dp, resolver=resolver)

def class_ctx(cls: str, args) -> "propedit.ClassCtx":
    """The lazy per-class schema bundle the prop verbs consume: every load routes through the
    mockable seams (`class_schema`/`class_defaults`/`struct_members`/`enum_names`), and the
    project resolves lazily + tolerantly (a no-project context is a clean SchemaError miss on
    first schema-needing token, never an early exit — spec §2.4)."""
    def proj():
        try:
            return resolve_project(args)
        except ProjectError:
            return None
    return propedit.ClassCtx(
        cls=cls,
        load_schema=lambda: class_schema(cls, proj()),
        load_defaults=lambda: class_defaults(cls, proj()),
        load_members=lambda p: struct_members(p, proj()),
        load_enums=lambda p: enum_names(p, proj()),
    )

def default_location_for(args):
    """`actor -> Decimal triple | None`, the class's default `Location`, for `best_grid_pivot` and
    the `--by` orbit.

    Consulted ONLY for an actor that does not state a Location, so an ordinary rotate stays offline
    and schema-free; the cost (and the need for a resolvable package path) is paid exactly when the
    answer depends on it. `Engine.Camera` defaults `Location=(X=-500,Y=-300,Z=300)`, so assuming zero
    would pivot 655 uu from where the engine puts the actor — the "the default is zero" bug
    `architecture.md` records the typed compare as existing to remove.

    Three things this has to get right, each of which it got WRONG on arrival (build review, round 3):

    * **Resolve the project.** `args.project` is argparse's RAW STRING; `class_defaults` wants a
      `config.Project`. Passing the string reached `config._composed_dirs_with_provenance` and raised
      `AttributeError: 'str' object has no attribute 'paths'` — a traceback, exit 1, on any
      `--project` invocation touching a Location-less actor. `Engine.Brush` without a `Location` line
      is ordinary: 5 of the 9 committed LUM probe trunks contain one.
    * **Memoize per CLASS.** `class_defaults` builds a fresh resolver and package map per call
      (~50 ms for `Engine.Camera`, 250 ms for `DeusEx.DeusExMover`), and both the pivot scan and the
      orbit ask for the same actor — so 500 Location-less actors cost 1000 resolutions and **59.9 s**
      against 1.07 s for the same set with Locations stated. `test_normalize.py`'s PERF GUARD says
      this in as many words: resolving per-ACTOR turns a ~1 s job into a ~2 min one. A level has
      5-60 distinct classes across hundreds of actors.
    * **Name the actor on failure.** A `SchemaError` reading `class must be fully qualified: ''`
      leaves the user to grep a 500-actor level for it, and says nothing about why a *rotate* wanted
      the schema at all. Same remedy as `apply.py`'s `cannot verify actor 'X' — …`."""
    memo: dict[str, tuple | None] = {}
    resolved: list = []          # the project, resolved at most once, and only if actually needed

    def _lookup(actor):
        fqcn = actor.cls
        if fqcn not in memo:
            try:
                if not resolved:
                    # LAZY: resolving eagerly demanded a project from every rotate, including the
                    # ones that never consult the schema — which contradicts the promise that an
                    # ordinary rotate stays offline, and broke 25 offline tests.
                    resolved.append(resolve_project(args))
                text = class_defaults(fqcn, resolved[0]).get(("location", 0))
            except (SchemaError, ProjectError) as e:
                raise CommandError(
                    f"actor {actor.name!r} states no Location, so its class default is needed to "
                    f"place the pivot — {e}. Qualify the class as Package.Class and put its package "
                    f"on the project's search paths, or state a Location on the actor") from None
            memo[fqcn] = rotation.parse_fvector(text) if text else None
        return memo[fqcn]

    return _lookup

def class_index(project=None) -> "classindex.ClassIndex":
    """Build the offline `ClassIndex` for the resolved project's composed `.u` path. The MOCKABLE
    seam (tests patch it to run offline without the gitignored v68 install), mirroring
    `class_schema`. A None project is re-resolved from cwd/env (tolerant of a no-project context —
    the caller turns an empty index into a clean 'no package path' error)."""
    if project is None:
        project = config.resolve_project(env_project=os.environ.get("UEDCLI_PROJECT"),
                                         cwd=os.getcwd())
    user_config = config.load_user_config()
    if user_config is None:                 # absent games config → clean exit 2, never AttributeError
        raise CommandError(NO_GAMES_CONFIG)
    return classindex.ClassIndex.from_project(project, user_config)

def audio_index(project, kind: str) -> "audioindex.AudioIndex":
    """Build the offline `AudioIndex` for `project` and `kind` ('sound'|'music') over the composed
    package path. The MOCKABLE seam (tests patch it to run offline without a game install), mirroring
    `class_index`. An absent games config or an empty composed path exits 2 cleanly (never an
    AttributeError / a silent empty result)."""
    user_config = config.load_user_config()
    if user_config is None:                 # absent games config → clean exit 2, never AttributeError
        raise CommandError(NO_GAMES_CONFIG)
    files = config.composed_search_files(project, user_config)
    if not files:
        raise CommandError(NO_PACKAGE_PATH)
    return audioindex.AudioIndex.from_files(files, kind)

def catalog_dir(project) -> str:
    """The tracked asset-catalog dir for `project` (`config.project_catalog_dir` —
    the `uedcli.toml` `catalog` key, default `<root>/texture-catalog/`). The class
    classification store shards live under `<catalog>/classified/class/`. A
    MOCKABLE seam so `class classify`/`show`/`list` tests point it at a tmp dir
    without a full project on disk."""
    return config.project_catalog_dir(project)

def mover_index(args, verb: str, project=None) -> "classindex.ClassIndex":
    """The class resolver the schema-aware mover gate needs. `movers.is_mover` decides mover-ness by
    walking the class hierarchy to `Engine.Mover` (dev/docs/direction/conventions.md 2026-07-25 10:18 UTC), so EVERY verb
    that asks "is this actor a Mover?" — `mover key`, `level doctor`, `event graph`, `brush
    scale`/`apply-transform`/`intersect`/`deintersect`, `stash capture`, the native preview/build —
    now needs the game's `.u` packages, hence a project and the per-user games config. A missing
    games config is a clean exit 2 naming the verb and the requirement (a missing PROJECT surfaces
    as the standard `ProjectError`); never a traceback, and never a report that silently calls
    every mover a static brush. `project` skips re-resolution where the caller already has one."""
    try:
        index = class_index(project if project is not None else resolve_project(args))
    except ProjectError:                            # a missing PROJECT keeps the house message
        raise
    except CommandError as e:                      # no per-user games config
        raise CommandError(f"{verb}: {e.message}; {MOVER_RESOLVER_WHY}") from None
    if index.empty:                                  # config present, but it resolves no packages
        raise CommandError(f"{verb}: {NO_PACKAGE_PATH}; {MOVER_RESOLVER_WHY}")
    return index

def package_path_or_exit(args):
    """Resolve the project (exit 2 if none) and return `(project, user_config, composed_files)`,
    raising one canonical `CommandError` if the composed package path is empty. The single seam all
    author-time validation goes through, so the empty-path wording is identical everywhere."""
    project = resolve_project(args)                              # exit 2 (clean) if not in a project
    user_config = config.load_user_config()
    if user_config is None:                 # absent games config → clean exit 2, never AttributeError
        raise CommandError(NO_GAMES_CONFIG)
    files = config.composed_search_files(project, user_config)
    if not files:
        raise CommandError(NO_PACKAGE_PATH)
    return project, user_config, files


def texture_dims_resolver(args):
    """A `ref -> (USize, VSize)` callable over the project's composed package files, built ONCE so
    its cache (`utexture.TextureResolver._dims_cache`) is shared across every ref a single command
    invocation looks up. Exits 2 (via `package_path_or_exit`) if the CLI is not run inside a
    resolvable project — a precondition to building a resolver at all, not a content check.

    The callable RAISES `ValueError` naming the ref and why on any failure, rather than returning a
    `TextureError` — `apply_scale`'s `--to` path lives in `surface.py`, which does not import
    `polyalign`, so a plain `ValueError` (which every step-5 caller already catches, `PolyAlignError`
    included, since it is a `ValueError` subclass) needs no new dispatch wiring. This is the one seam
    `align run --fit-perimeter`, `align one-tile` and `scale --to` all go through, so the wording is
    identical everywhere `_validate_texture_ref`'s already is."""
    _project, _user_config, files = package_path_or_exit(args)
    resolver = utexture.TextureResolver(files)

    def resolve_dims(ref: str) -> tuple[int, int]:
        result = resolver.dimensions(ref)
        if isinstance(result, utexture.TextureError):
            raise ValueError(f"texture not found: {ref} — {result.detail}")
        return result

    return resolve_dims


# The one explanation appended to both of `mover_index`'s failure messages (a review fix: the
# "exits 2 naming the verb" promise held on only one of the two routes).
MOVER_RESOLVER_WHY = ("a class resolver is required because mover detection resolves the actor's "
                       "class against Engine.Mover")

# One canonical message for "the resolved project has no game packages on its path" — used by every
# author-time validation site so the wording never diverges (a review fix).
NO_PACKAGE_PATH = ("no package search path: this project resolves no game packages (check the games "
                    "config `paths` and that the project targets a game)")

# One canonical message for "no per-user games config" on the author-time validation paths (the
# materialize/texture/stub verbs carry their own verb-specific variants). A review fix: an absent
# `~/.uedcli/config.toml` must exit 2 cleanly here, never reach `composed_search_files` as None.
NO_GAMES_CONFIG = ("no per-user games config (~/.uedcli/config.toml): needed to resolve the game's "
                    "base package paths; create it with a [games.<name>] paths dir list")

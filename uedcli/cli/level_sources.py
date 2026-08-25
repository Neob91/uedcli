"""Level, stash and prefab sources: loading, saving, selection and the ambient-level announcement.

`resolve_level_source` maps this invocation (default ambient `$UEDCLI_LEVEL`, or an explicit
`--tree KIND/NAME`) to a concrete source: a `TrunkLevelSource` on a level's on-disk trunk, a
`StashLevelSource`, or a `PrefabLevelSource`. `resolve_level_only` is the level-only variant for
build/preview verbs. This module folds the former `level_select.py` helpers (`resolve_level`,
`list_levels`, `check_safe_level`, `NO_LEVEL_MSG`).

It uses `cli.resources` for project/prefab resolution and `stash_register.for_project` for the stash
register; nothing here is imported back by `resources` (leftward order errors <- resources <-
level_sources). Persistence behavior — trunk delta writes, per-level locking, rank overrides,
folder/label sidecars, `--tree` validation and path-safety, level-only rejection, and the one-time
`$UEDCLI_LEVEL` announcement inside `TrunkLevelSource.save` — is preserved exactly.
"""
from __future__ import annotations

import fcntl
import os
import sys
from pathlib import Path

from .. import config, stash_register, stashlib, trunk
from ..model import Level, parse_t3d
from ..normalize import canonical_actor_t3d
from . import resources
from .errors import CommandError, LevelSelectionError


class TrunkLevelSource:
    """Git-native level source: the on-disk T3D trunk `maps/<level>/`. Holds the actors' order_values
    between load and save so a mutation preserves every surviving actor's rank and mints one (after all
    of them) for a newly-added actor. `save(ranks=…)` is the CSG-order OVERRIDE channel by which
    `actor order`/`actor add --order` reassign or off-append a rank (spec 2026-07-18 §3)."""
    kind = "level"                                       # uniform box label (level status / doctor)
    # True only when this source was resolved from the ambient $UEDCLI_LEVEL (not an explicit
    # `--tree`). A mutation (`save`) then echoes the level once to stderr — the visibility guard
    # against editing the wrong level via a stale export (decisions 2026-07-20). Class default so a
    # directly-constructed source (materialize/preview build one) is silent unless it opts in.
    from_env = False

    def __init__(self, trunk_dir: Path):
        self.trunk_dir = Path(trunk_dir)
        self._ranks: dict[str, str] = {}
        self._loaded_names: set[str] = set()
        self._loaded_bodies: dict[str, str] = {}
        self._loaded_folders: dict[str, str | None] = {}
        self._loaded_labels: dict[str, frozenset[str]] = {}
        self._loaded = False
        self._announced = False                          # echo the from_env level at most once

    @property
    def display_name(self) -> str:
        return self.trunk_dir.name

    def load(self) -> Level:
        try:
            (level, self._ranks, self._loaded_bodies,
             self._loaded_folders) = trunk.read_level_with_bodies(self.trunk_dir)
        except (OSError, ValueError) as e:               # corrupt actor.t3d/sidecar → clean, not a traceback
            raise CommandError(f"cannot read level {self.trunk_dir.name!r}: {e}")
        # Labels ride on `level.actors[name].labels` (read_actor_tree loads the sidecar there, not
        # into the returned tuple), so derive the baseline from the model — same as folders.
        self._loaded_labels = {n: level.actors[n].labels for n in level.actors}
        self._loaded_names = set(self._ranks)           # the on-disk set THIS process saw at load
        self._loaded = True
        return level

    def save(self, *, verb: str, args: dict, level: Level, touched: list[str],
             ranks: dict[str, str] | None = None) -> None:
        # verb/args/touched ignored — git is the history; packages derive on demand at build.
        # `ranks` is the CSG-order OVERRIDE channel (spec 2026-07-18 §3): a name present in it takes
        # the override value instead of the default rule below — the ONLY way a `Level` (which carries
        # no per-actor order_value) can move an existing actor's rank (`actor order`) or place a new
        # one off the append point (`actor add --order`). It flows straight into `write_level`, and
        # the `changed` diff below fires because the override differs from the UNTOUCHED `self._ranks`
        # snapshot — so we must NOT mutate `self._ranks` before the write, or the diff self-cancels.
        if not self._loaded:                            # guard the whole-level re-rank footgun
            raise RuntimeError("TrunkLevelSource.save requires a prior load() (it preserves the "
                               "existing order_values)")
        # Visibility guard (decisions 2026-07-20): a trunk WRITE resolved from the ambient
        # $UEDCLI_LEVEL announces the level once, so a stale export can't silently edit the wrong
        # one. save() is the actual mutation seam — reads never reach here, so this is self-limiting
        # to writes without any per-verb enumeration. Explicit `--tree` leaves from_env False (silent).
        if self.from_env and not self._announced:
            announce_env_level(self.display_name)
            self._announced = True
        override = ranks or {}
        resolved: dict[str, str] = {}
        for name in level.order:
            # membership test, not truthiness, so a legit empty stored rank is preserved not re-minted;
            # rank a new actor after the union of ALL existing + already-assigned ranks (never a partial
            # max) so it can't collide with a not-yet-emitted actor.
            if name in override:
                resolved[name] = override[name]
            else:
                resolved[name] = (self._ranks[name] if name in self._ranks
                                  else trunk.append_rank({**self._ranks, **resolved}))
        ranks = resolved
        # DELTA write under a short per-level flock (dev/docs/direction/trunk-and-editor.md 2026-07-18 — concurrent trunk
        # writers): write ONLY the actors whose body or rank differs from THIS process's load
        # snapshot (content-diff, not `touched` — robust to any verb under-reporting), and prune
        # ONLY this process's own deletions (loaded set minus current set). An actor another
        # process added, edited, or deleted meanwhile is therefore never stomped/resurrected from
        # our stale model — disjoint concurrent edits compose (equal freshly-minted order_values
        # stay harmless via the name tiebreak, decisions 2026-07-05 15:11). The flock serializes
        # savers so one saver's prune/replace can never race another mid-write. Resource-adjacent
        # like the catalog locks: `<maps-dir>/.locks/`, self-ignoring.
        deleted = self._loaded_names - set(level.actors)
        new_bodies = {name: trunk.dump_actor_body(actor) for name, actor in level.actors.items()}
        # The changed set fires on a body, rank, OR FOLDER delta vs the load snapshot. Folder is a
        # sidecar (not in the body), so a folder-ONLY change — INCLUDING `"x"`→None (unset) — leaves
        # body+rank identical; without this comparison the write is silently dropped (spec §2 trap).
        changed = {name for name, body in new_bodies.items()
                   if body != self._loaded_bodies.get(name)
                   or ranks[name] != self._ranks.get(name)
                   or level.actors[name].folder != self._loaded_folders.get(name)
                   or level.actors[name].labels != self._loaded_labels.get(name, frozenset())}
        lock_home = config.self_ignoring_dir(self.trunk_dir.parent / ".locks", create=True,
                                             what="trunk lock dir")
        with open(lock_home / f"level-{self.trunk_dir.name}.lock", "w") as lf:
            fcntl.flock(lf, fcntl.LOCK_EX)
            trunk.write_level(self.trunk_dir, level, ranks, deleted=deleted, only=changed)
        self._ranks = ranks
        self._loaded_names = set(level.actors)
        self._loaded_bodies = new_bodies                # the written state is the next diff baseline
        self._loaded_folders = {name: actor.folder for name, actor in level.actors.items()}
        self._loaded_labels = {name: actor.labels for name, actor in level.actors.items()}


class StashLevelSource:
    """A stash register entry (`--tree stash/<id>`) as a `LevelSource`. Mirrors
    `TrunkLevelSource`'s `load()`/`save(*, verb, args, level, touched)` seam so every content verb
    edits a stash exactly as it edits the trunk. Stash/prefab use a flat `order` list (no per-actor
    `order_value` sidecar), so `_ranks` is empty — no content verb reads it (only `level
    status`/`doctor` do, and those are level-only). `save` recomputes the texture-only `packages`
    from the edited actors and preserves `meta` (the capture anchor); `write_stash(force=True)` swaps
    atomically."""
    kind = "stash"                                       # uniform box label (level status / doctor)
    from_env = False                                     # a box is never the ambient env level (attr parity)

    def __init__(self, reg: "stash_register.FileStashRegister", stash_id: str):
        self.reg = reg
        self.id = stash_id
        self._ranks: dict[str, str] = {}
        self._meta: dict = {}

    @property
    def display_name(self) -> str:
        return self.id

    def load(self) -> Level:
        try:
            blobs, order, _pkgs, self._meta, folders = self.reg.read_stash(self.id)
        except (OSError, ValueError) as e:               # corrupt meta.json/state → clean, not a traceback
            raise CommandError(f"cannot read stash {self.id!r}: {e}")
        # `if n in blobs` guards a stored order that names a missing blob (never a bare KeyError).
        keep = [n for n in order if n in blobs]
        level = parse_t3d("Begin Map\n" + "\n".join(blobs[n] for n in keep) + "\nEnd Map\n")
        level.order = keep
        for n in keep:                                   # re-attach each member's stored folder (a
            level.actors[n].folder = folders.get(n)      # T3D blob drops it) so an edit preserves it
        return level

    def save(self, *, verb: str, args: dict, level: Level, touched: list[str],
             ranks: dict[str, str] | None = None) -> None:
        # `ranks` (the CSG-order override) is IGNORED here: the ordering verbs reject a stash target
        # before ever reaching this save (the internal order_value sidecar is not exposed to them), so
        # a real override never arrives. Folders ARE preserved (persisted per member since the
        # unify-T3D-trees change) so an edit that doesn't touch a member's folder keeps it.
        full = {n: canonical_actor_t3d(level.actors[n]) for n in level.order if n in level.actors}
        folders = {n: level.actors[n].folder for n in level.order if n in level.actors}
        self.reg.write_stash(
            self.id, full_level=full, order=[n for n in level.order if n in level.actors],
            packages=sorted(stashlib.referenced_packages(list(level.actors.values()))),
            meta=self._meta, folders=folders, force=True)


class PrefabLevelSource:
    """A durable prefab library entry (`--tree prefab/<name>`) as a `LevelSource`. Same shape as
    `StashLevelSource` but backed by `stashlib.read_prefab`/`write_prefab` — a per-actor T3D tree
    `<name>/{actors/…, packages, meta.json}` (unify-T3D-trees, decisions 2026-07-18 23:01 UTC). The
    split-sibling `meta.json` holds ONLY the capture extras (`anchor`/`ts`), so passing it straight
    back to `write_prefab` cannot clobber the fresh order/packages (they are the sidecar/order_value
    files now, not JSON keys)."""
    kind = "prefab"                                      # uniform box label (level status / doctor)
    from_env = False                                     # a box is never the ambient env level (attr parity)

    def __init__(self, root: Path, name: str):
        self.root = Path(root)
        self.name = name
        self._ranks: dict[str, str] = {}
        self._meta: dict = {}

    @property
    def display_name(self) -> str:
        return self.name

    def load(self) -> Level:
        try:
            blobs, order, _pkgs, self._meta, folders = stashlib.read_prefab(self.root, self.name)
        except stashlib.OldFormatPrefab as e:            # HARD CUTOVER: actionable, never a traceback
            raise CommandError(str(e))
        except (OSError, ValueError) as e:               # corrupt per-actor tree/sidecar → clean, not a traceback
            raise CommandError(f"cannot read prefab {self.name!r}: {e}")
        keep = [n for n in order if n in blobs]
        level = parse_t3d("Begin Map\n" + "\n".join(blobs[n] for n in keep) + "\nEnd Map\n")
        level.order = keep
        for n in keep:                                   # re-attach each member's stored folder
            level.actors[n].folder = folders.get(n)
        return level

    def save(self, *, verb: str, args: dict, level: Level, touched: list[str],
             ranks: dict[str, str] | None = None) -> None:
        # `ranks` (the CSG-order override) is IGNORED here: the ordering verbs reject a prefab target
        # (the internal order_value sidecar is not exposed to them). Folders ARE preserved per member.
        full = {n: canonical_actor_t3d(level.actors[n]) for n in level.order if n in level.actors}
        folders = {n: level.actors[n].folder for n in level.order if n in level.actors}
        stashlib.write_prefab(
            self.root, self.name, full_level=full,
            order=[n for n in level.order if n in level.actors],
            packages=sorted(stashlib.referenced_packages(list(level.actors.values()))),
            meta=self._meta, folders=folders, force=True)


def resolve_level_source(args):
    """The level source for this invocation. Default (no `--tree`): the ambient `$UEDCLI_LEVEL` level
    on the git-native trunk — the env fallback marks the returned source `from_env=True`, so a
    subsequent mutation echoes which level it edited (the visibility guard against a stale export —
    decisions 2026-07-20). With `--tree KIND/NAME` (KIND ∈ level|stash|prefab): the named box
    EXPLICITLY — a `StashLevelSource`, `PrefabLevelSource`, or a `TrunkLevelSource` on a NAMED level's
    trunk (no echo; the user named the target). `config.resolve_project` returns None (→ our clean
    `ProjectError`) for a missing project, though a bare-NAME `--project` still raises
    `config.ConfigError` (a hard user error, caught by `dispatch()` → exit 2)."""
    tgt = getattr(args, "tree", None)
    if tgt is not None:                                  # explicit --tree (incl. "" → a clear error,
        kind, sep, name = tgt.partition("/")             # not a silent fallback to the ambient level)
        if not sep or kind not in ("level", "stash", "prefab") or not name:
            raise CommandError(
                f"--tree must be KIND/NAME (KIND ∈ level|stash|prefab), got {tgt!r}")
        # MANDATORY before constructing any source: read_stash/read_level do NOT validate the top
        # name, so `--target stash/../../x` would otherwise escape on both load AND the later save.
        try:
            stashlib.validate_member_name(name)
        except ValueError as e:
            raise CommandError(str(e))
        project = resources.resolve_project(args)                 # all three boxes live under the project
        if kind == "stash":
            reg = stash_register.for_project(project)
            if not reg.exists(name):                     # meta.json-keyed (nested + emptied-safe)
                raise CommandError(f"stash not found: {name!r}")
            return StashLevelSource(reg, name)
        if kind == "prefab":
            root = resources.prefab_root(args)
            if name not in stashlib.list_prefabs(root):
                raise CommandError(f"prefab not found: {name!r}")
            return PrefabLevelSource(root, name)
        # kind == "level": a NAMED level's trunk (edit a level without exporting $UEDCLI_LEVEL).
        # Levels are SINGLE safe segments (unlike nested stash/prefab names) — `validate_member_name`
        # allows `/`, so re-check here: a nested/dotted name would scatter lock homes or edit the
        # self-ignored `maps/.locks/` as a level (review fix, 2026-07-18).
        try:
            check_safe_level(name)
        except LevelSelectionError as e:
            raise CommandError(str(e))
        maps_dir = Path(config.project_maps_dir(project))
        if not (maps_dir / name).is_dir():
            raise CommandError(f"level not found: {name!r}")
        return TrunkLevelSource(maps_dir / name)         # explicit --tree → from_env stays False (no echo)

    # No --tree: the ambient $UEDCLI_LEVEL (decisions 2026-07-20 — env passed IN, mirroring
    # config.resolve_project). A missing/blank/malformed value raises LevelSelectionError → exit 2.
    project = resources.resolve_project(args)                     # no project → ProjectError → exit 2
    maps_dir = Path(config.project_maps_dir(project))
    name = resolve_level(env_level=os.environ.get("UEDCLI_LEVEL"), maps_dir=maps_dir)
    src = TrunkLevelSource(maps_dir / name)
    src.from_env = True                                  # env fallback → a mutation announces the level
    return src


def announce_env_level(name: str, *, action: str = "editing") -> None:
    """Echo the ambient level to STDERR (pipe-safe — the CLI ethos routes human notes there) when a
    mutating verb resolved it from `$UEDCLI_LEVEL` rather than an explicit `--tree`. The visibility
    guard against a stale export silently hitting the wrong level (decisions 2026-07-20). `action` is
    the verb-appropriate word: `editing` (trunk write), `materializing` (build), `capturing from`."""
    print(f"{action} level {name!r} (from $UEDCLI_LEVEL)", file=sys.stderr)


def resolve_level_only(args, *, verb: str, alt_hint: str | None = None) -> tuple[str, bool]:
    """Resolve the level for a build/preview verb that operates on a LEVEL only (materialize, preview
    trunk mode). Same precedence as `resolve_level_source` (explicit `--tree` > ambient
    `$UEDCLI_LEVEL`) but constrained to the `level` kind — `--tree stash|prefab` is rejected with a
    clear exit 2, since a captured actor-set has no world to build or walk (dedicated `stash preview`/
    `prefab preview` exist). Returns `(level_name, from_env)`; the caller uses the name to build a
    `TrunkLevelSource` and `from_env` to decide whether to announce the level."""
    project = resources.resolve_project(args)                     # no project → ProjectError → exit 2
    maps_dir = Path(config.project_maps_dir(project))
    tgt = getattr(args, "tree", None)
    if tgt is not None:                                  # explicit --tree (incl. "" → clear error)
        kind, sep, name = tgt.partition("/")
        if not sep or kind not in ("level", "stash", "prefab") or not name:
            raise CommandError(
                f"--tree must be KIND/NAME (KIND ∈ level|stash|prefab), got {tgt!r}")
        if kind != "level":
            msg = f"{verb} operates on a level, not --tree {kind}/…"
            if alt_hint:
                msg += f"; {alt_hint}"
            raise CommandError(msg)
        try:
            check_safe_level(name)         # single safe segment (nested/dotted → error)
        except LevelSelectionError as e:
            raise CommandError(str(e))
        if not (maps_dir / name).is_dir():
            raise CommandError(f"level not found: {name!r}")
        return name, False                               # explicit → no echo
    name = resolve_level(env_level=os.environ.get("UEDCLI_LEVEL"), maps_dir=maps_dir)
    return name, True                                    # ambient → caller may echo


def check_safe_level(level: str) -> None:
    """A level name must be a single safe directory segment (it becomes `maps/<level>/`). A
    leading dot is rejected too: `.locks` is the maps-dir lock home (self-ignored), so a dotted
    level would collide with it / hide from git (review fix, 2026-07-18)."""
    if (not level or level in (".", "..") or level.startswith(".")
            or "/" in level or "\\" in level or "\n" in level):
        raise LevelSelectionError(f"invalid level name: {level!r}")


def list_levels(maps_dir: Path) -> list[str]:
    """Every level under `maps_dir`: an immediate subdirectory that holds an `actors/` tree (the
    structural marker of a T3D trunk — `level create` scaffolds exactly this). Dotted dirs (`.locks`,
    the maps-dir lock home) are skipped. Sorted case-insensitively, ties broken by exact name, for a
    stable human- and pipe-friendly order. Returns [] when `maps_dir` is absent or not a directory."""
    maps_dir = Path(maps_dir)
    if not maps_dir.is_dir():
        return []
    names = [
        d.name for d in maps_dir.iterdir()
        if d.is_dir() and not d.name.startswith(".") and (d / "actors").is_dir()
    ]
    return sorted(names, key=lambda n: (n.lower(), n))


# The "no level" error names BOTH ways to set the level (decisions 2026-07-20 — clean break from the
# old pointer; the message is the whole migration story, so it must be self-contained).
NO_LEVEL_MSG = (
    "no level: set the environment variable (export UEDCLI_LEVEL=<name>) "
    "or pass a level explicitly (--tree level/<name>)"
)


def resolve_level(*, env_level: str | None, maps_dir: Path) -> str:
    """The ambient level from `$UEDCLI_LEVEL` (passed in as `env_level`) — the default source when a
    verb gets no explicit `--tree`. Normalization order (exact): strip → blank ⇒ unset → single-safe-
    segment check → must exist under `maps_dir`. Raises `LevelSelectionError` (→ the CLI's exit 2)
    when unset, malformed, or nonexistent — never a silent empty-level read.

    A value containing `/` is the common mistake of copying the flag's `KIND/NAME` shape into the
    bare-name env var; its error hints the grammar rather than the opaque `invalid level name`."""
    name = (env_level or "").strip()
    if not name:                                          # unset or blank/whitespace ⇒ no level
        raise LevelSelectionError(NO_LEVEL_MSG)
    if "/" in name or "\\" in name:                       # grammar hint: env is a BARE name, not KIND/NAME
        raise LevelSelectionError(
            f"$UEDCLI_LEVEL is a bare level name, not KIND/NAME: {name!r} "
            "(use e.g. UEDCLI_LEVEL=castle, or --tree level/castle on the command)")
    check_safe_level(name)                               # dotted/empty/backslash/newline → clean error
    if not (Path(maps_dir) / name).is_dir():
        raise LevelSelectionError(f"$UEDCLI_LEVEL names a level that does not exist: {name!r}")
    return name

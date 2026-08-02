"""Global-CLI config + package-path resolution (project layout: direction/projects-and-config.md 2026-07-17 20:58;
directory model: direction/containers.md 2026-07-14 03:30).

Pure, side-effect-light (the one side effect is `state_dir(create=True)`'s mkdir + self-ignore).
Loads the two config files and resolves package paths. `paths` are bare **directories**
(colon-separated), NOT globs — uedcli owns the five package extensions (`.u .dx .utx .uax .umx`)
and scans the dirs itself:

- **Per-user** `~/.uedcli/config.toml` — one `[games.<name>]` block per game, each with a `paths`
  colon-separated list of ABSOLUTE directories. Nothing else (no `[defaults]`, no `image`, no
  `container`).
- **Per-project** `<root>/uedcli.toml` — a free-standing marker file at the repo root (à la
  `pyproject.toml`): the dir containing it IS the **project root**. Keys: `game` (required) +
  optional `paths`/`catalog`/`prefabs`/`maps`, ALL relative to the root (absolute allowed);
  omitted dir keys default root-relative to `maps/`, `prefabs/`, `texture-catalog/`. Discovery is
  a plain walk-up to the first ancestor containing an `uedcli.toml` file (nearest wins) — no
  child-dir scan, no schema sniffing.

Machine-local, never-tracked project state (stash, delivered preview maps, locks, staging)
lives in the **self-ignoring `<root>/.uedcli/`** (`state_dir`): on first
creation uedcli writes `.uedcli/.gitignore` containing `*`, so it can never be committed.

The composed effective search is *project dirs first, then the game's base dirs* — deduped by
directory for the mounts (`composed_search_dirs`), and by case-folded package **stem** for the
load-set files scanned out of those dirs (`composed_search_files`; identity is the bare name
regardless of extension) — so a project dir/package shadows a same-named base one.

Deliberately does **NOT** import `packages.py` (dependency direction — packages.py imports this).

Deferred/on-hold (direction/projects-and-config.md 2026-07-01): name-based `--project` needs a project registry (dead
since 2026-07-05) — `resolve_project` handles only path-based + walk-up resolution (a bare name
errors unless a `resolve_name` hook is injected). The internal term stays `substrate` (`Substrate`,
`select_substrate`) though the user-facing TOML key is `game`.
"""
from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

# The recognized Unreal package extensions. Duplicated from packages._PKG_EXTS on purpose:
# config.py must not import packages.py (dependency direction). Kept in sync by a regression test.
PKG_EXTS = (".u", ".dx", ".utx", ".uax", ".umx")

# Top-level keys that mark a PROJECT config (vs the per-user games config). Used both to reject
# unknown project keys and to classify a config by schema. (`id`/`name` were DROPPED with the
# registry — direction/projects-and-config.md 2026-07-17 20:58 §2; a file carrying them gets the unknown-key error.)
_PROJECT_KEYS = {"game", "paths", "catalog", "prefabs", "maps"}

# A Windows drive-letter colon (`Z:\` / `Z:/`) inside a value — the `:` is our list separator, so a
# pasted container path must be a named error, never a silent split. Anchored to an element boundary
# (string start or a separator `:`) so a normal `foo.utx:/next` separator colon is NOT mistaken for a
# drive.
_WIN_DRIVE = re.compile(r"(?:^|:)[A-Za-z]:[\\/]")


class ConfigError(ValueError):
    """A user-facing config problem (bad TOML shape, unknown key, wrong schema, bad path, …).
    Carries a message naming the offending file/key/value; dispatch turns it into exit 2."""


# --------------------------------------------------------------------------- value objects

@dataclass(frozen=True, kw_only=True)
class Substrate:
    """A game's base packages (internal term "substrate"; user-facing TOML key `[games.<name>]`)."""
    name: str
    paths: str                      # colon-separated DIRECTORIES, MUST be absolute


@dataclass(frozen=True, kw_only=True)
class UserConfig:
    games: dict[str, Substrate]
    source: str = ""                # the config.toml path it was loaded from


@dataclass(frozen=True, kw_only=True)
class Project:
    root: str                       # abspath of the dir holding uedcli.toml — the project root
    game: str                       # required — selects a [games.<name>]
    paths: str | None = None        # colon-separated DIRECTORIES, relative to `root` (or absolute)
    catalog: str | None = None      # raw, relative to `root`; see project_catalog_dir()
    prefabs: str | None = None
    maps: str | None = None
    source: str = ""                # the uedcli.toml path


# --------------------------------------------------------------------------- schema classification

def _classify(raw: dict, where: str = "config") -> Literal["user", "project"]:
    """Classify a parsed config as "user" (has a [games.*] table) or "project" (has a top-level
    project key). A hybrid (both) or neither is a ConfigError — the two schemas are mutually
    exclusive so the shared per-user/project loading is unambiguous. `where` (the file path) is
    folded into the errors so they name the offending file (a review fix)."""
    has_games = isinstance(raw.get("games"), dict)
    project_keys = _PROJECT_KEYS & set(raw)
    if has_games and project_keys:
        raise ConfigError(
            f"{where}: ambiguous config: has a [games.*] table AND project key(s) "
            f"{', '.join(sorted(project_keys))} — a config is EITHER the per-user games config "
            "OR a project config, never both")
    if has_games:
        return "user"
    if project_keys:
        return "project"
    raise ConfigError(
        f"{where}: config matches neither schema: no [games.*] table and no project key "
        f"({', '.join(sorted(_PROJECT_KEYS))})")


# --------------------------------------------------------------------------- directory resolution

def pkg_stem(filename: str) -> str | None:
    """The package name (basename sans recognized extension), or None if not a package file.
    Case-insensitive on the extension (UE1 FName semantics)."""
    base = os.path.basename(filename)
    stem, ext = os.path.splitext(base)
    return stem if ext.lower() in PKG_EXTS else None


def _dedup_by_stem(files: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Keep the FIRST (path, provenance) per case-folded package stem. First-wins is what makes
    'project shadows base' fall out when project entries precede base ones. Identity is the bare
    stem regardless of extension (UE1's package namespace is flat by name)."""
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for path, prov in files:
        stem = pkg_stem(path)
        key = stem.casefold() if stem is not None else os.path.basename(path).casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append((path, prov))
    return out


def reject_windows_drive(paths_str: str, where: str = "") -> None:
    """Raise the shared "Windows-style drive?" `ConfigError` if `paths_str` holds a drive-letter
    colon (`C:\\DX\\System`, `Z:/work`).

    Both places that read a colon-separated dir list call this, and that is the point. A pasted
    Windows path is the single most likely way to get a `:` into a value where `:` is the LIST
    SEPARATOR, and without a dedicated message the split is silent: `C:\\DX\\System` becomes the two
    elements `C` and `\\DX\\System`, and the user is told `dir must be absolute: 'C'` — a message
    about a path they never typed. The check therefore has to run on the WHOLE string, before any
    split, everywhere such a string is read: `resolve_dirs` (compose time) AND `load_user_config`
    (load time, which runs first and used to produce exactly that confusing error).

    `where` prefixes the message with the offending file/table when the caller knows it."""
    if _WIN_DRIVE.search(paths_str):
        prefix = f"{where}: " if where else ""
        raise ConfigError(
            f"{prefix}path element contains a ':' (Windows-style drive?) — values are POSIX and "
            f"':' is the list separator: {paths_str!r}")


def resolve_dirs(paths_str: str, base: str, *, require_absolute: bool = False) -> list[str]:
    """Resolve a colon-separated DIRECTORY list to absolute host dirs, in order (direction/containers.md
    2026-07-14 03:30 — `paths` are bare dirs now, NOT globs). No file globbing: uedcli scans each
    dir itself for the five package extensions elsewhere.

    Each element is stripped, resolved against `base` (a relative element joins `base`; an absolute
    one is honored verbatim), abspath-normalized, and included **only if it is an existing
    directory** — a NON-existent dir is SKIPPED, not an error, so offline model verbs still run for a
    user without the base game installed (materialize's `missing_packages` fail-fast still catches an
    actually-needed missing package). Order preserved; NO dedup here (the composers dedup). An
    empty/None string → []. Named errors (never a traceback): a `:` inside an element (Windows-style
    drive), and a leftover glob char `*` (the dirs-not-globs migration); `require_absolute` (the
    games config, which has no project root to anchor to) rejects any relative element."""
    if not paths_str:
        return []
    reject_windows_drive(paths_str)
    out: list[str] = []
    for element in paths_str.split(":"):
        element = element.strip()
        if not element:
            continue
        if "*" in element:
            raise ConfigError(
                f"paths are directories now, not globs: drop the /*.ext from {element!r}")
        if require_absolute and not os.path.isabs(element):
            raise ConfigError(
                f"path must be absolute (no project root to anchor to): {element!r}")
        abspath = os.path.abspath(element if os.path.isabs(element) else os.path.join(base, element))
        if os.path.isdir(abspath):          # a non-existent dir is silently skipped (offline-safe)
            out.append(abspath)
    return out


# --------------------------------------------------------------------------- TOML loading

def _read_toml(path: str) -> dict:
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{path}: invalid TOML: {e}") from e
    except OSError as e:
        # An unreadable config (e.g. a permission-denied uedcli.toml found by walk-up) is a HARD,
        # named error — never silently climbed past, never a raw OSError traceback (spec §4).
        raise ConfigError(f"{path}: cannot read: {e.strerror or e}") from e


def _reject_unknown(d: dict, allowed: set[str], where: str) -> None:
    extra = set(d) - allowed
    if extra:
        raise ConfigError(f"{where}: unknown key(s): {', '.join(sorted(extra))} "
                          f"(allowed: {', '.join(sorted(allowed))})")


def _user_home() -> Path:
    """The per-user uedcli home: `$UEDCLI_HOME` if set (expanded + resolved), else `~/.uedcli`.
    The single resolution point for everything that lives under the per-user home (config +
    the derivable cache)."""
    home = os.environ.get("UEDCLI_HOME")
    return Path(os.path.expanduser(home)).resolve() if home else Path.home() / ".uedcli"


def user_config_path(override: str | None = None) -> str:
    """The per-user config.toml path: --config override, else $UEDCLI_HOME/config.toml, else
    ~/.uedcli/config.toml."""
    if override:
        return os.path.abspath(os.path.expanduser(override))
    return str(_user_home() / "config.toml")


def user_cache_home() -> Path:
    """The per-user, cross-project, DERIVABLE cache root: `<$UEDCLI_HOME or ~/.uedcli>/cache`.
    Holds `stubs/` (v69 stub packages) and `textures/` (decoded image cache) — never committed,
    regenerable. Distinct from the per-project TRACKED `texture-catalog/` classification store."""
    return _user_home() / "cache"


def stub_cache_root(*, create: bool = False) -> Path:
    """Where built v69 stub packages + their sidecars are cached (gitignored, copyright-derived):
    the per-user, cross-project `<user_cache_home>/stubs/`. `create=True` `mkdir -p`s it (for cache
    init / editor spin-up, which need the host source to exist before a `/stubs` bind-mount); the
    default is a pure path (a read-only remap must NOT create the dir as a side effect). (Folded in
    from the deleted `repo_paths.py`, dropping its vestigial `start` arg — layout reorg slice 3.)"""
    root = user_cache_home() / "stubs"
    if create:
        root.mkdir(parents=True, exist_ok=True)
    return root


def texture_images_root() -> Path:
    """The gitignored, regenerable exported texture PNGs: the per-user, cross-project
    `<user_cache_home>/textures/`. (Folded in from the deleted `repo_paths.py`.) NOTE: locks are
    NOT derived from this root — they live in the project state dir (`state_subdir(root,
    "locks")`)."""
    return user_cache_home() / "textures"


def schema_cache_root(*, create: bool = False) -> Path:
    """The gitignored, regenerable per-package decoded-schema cache: the per-user, cross-project
    `<user_cache_home>/schema/`, sibling to `stubs/`/`textures/`
    (`dev/docs/architecture.md` "Package schema cache"). Holds one marshal blob per `(package
    realpath, size, mtime_ns)` stat tuple under a `v<N>/` decoder-version subdir; `schema_cache.py`
    owns the layout. `create=True` `mkdir -p`s it; the default is a pure path (a read must not create
    the dir as a side effect)."""
    root = user_cache_home() / "schema"
    if create:
        root.mkdir(parents=True, exist_ok=True)
    return root


def load_user_config(override: str | None = None) -> UserConfig | None:
    """Load the per-user `[games.*]` config. Returns None if absent (→ caller uses the legacy path).
    Raises ConfigError on a malformed file, wrong schema, unknown key, missing/relative game dir."""
    path = user_config_path(override)
    if not os.path.isfile(path):
        return None
    raw = _read_toml(path)
    if _classify(raw, path) != "user":
        raise ConfigError(
            f"{path}: expected a per-user games config ([games.*]) but it looks like a project "
            "config (has top-level project keys)")
    _reject_unknown(raw, {"games"}, path)
    games_raw = raw["games"]
    if not games_raw:
        raise ConfigError(f"{path}: at least one [games.<name>] table is required")
    games: dict[str, Substrate] = {}
    for name, tbl in games_raw.items():
        where = f"{path} [games.{name}]"
        if not isinstance(tbl, dict):
            raise ConfigError(f"{where}: must be a table")
        _reject_unknown(tbl, {"paths"}, where)
        paths = tbl.get("paths")
        if not isinstance(paths, str) or not paths.strip():
            raise ConfigError(f"{where}: required key 'paths' (a colon-separated dir list) is missing")
        # BEFORE the split, so a pasted `C:\DX\System` gets the dedicated drive-letter error rather
        # than splitting into `C` + `\DX\System` and being reported as "dir must be absolute: 'C'".
        reject_windows_drive(paths, where)
        for pat in (p.strip() for p in paths.split(":") if p.strip()):
            if not os.path.isabs(pat):
                raise ConfigError(f"{where}: dir must be absolute: {pat!r}")
        games[name] = Substrate(name=name, paths=paths)
    return UserConfig(games=games, source=path)


def _project_toml_path(dir_or_toml: str) -> str:
    p = os.path.abspath(dir_or_toml)
    if os.path.isdir(p):
        return os.path.join(p, "uedcli.toml")
    # A file path must BE an `uedcli.toml` — spec §4: "the root dir or the uedcli.toml itself".
    # Accepting any project-schema TOML under any name would silently bless mis-pointed
    # --project/UEDCLI_PROJECT values (review fix).
    if os.path.basename(p) != "uedcli.toml":
        raise ConfigError(f"not a project marker: {p} (pass the project ROOT dir or its uedcli.toml)")
    return p          # possibly nonexistent — caller's isfile check fires


def load_project(dir_or_toml: str) -> Project:
    """Load a project `uedcli.toml` (given the project ROOT dir or the file itself). Validates
    schema + keys; the dir containing the file IS the project root. `game` is required; `paths`
    stays relative (resolved against `root` later); `catalog`/`prefabs`/`maps` are relative to the
    root (defaults `texture-catalog`/`prefabs`/`maps` — direction/projects-and-config.md 2026-07-17 20:58 §2)."""
    toml_path = _project_toml_path(dir_or_toml)
    if not os.path.isfile(toml_path):
        raise ConfigError(f"no uedcli.toml at {toml_path}")
    raw = _read_toml(toml_path)
    if _classify(raw, toml_path) != "project":
        raise ConfigError(
            f"{toml_path}: expected a project config (top-level 'game', …) but it looks like a "
            "per-user games config ([games.*])")
    _reject_unknown(raw, _PROJECT_KEYS, toml_path)
    game = raw.get("game")
    if game is not None and (not isinstance(game, str) or not game.strip()):
        raise ConfigError(f"{toml_path}: key 'game' must be a non-empty string, got {game!r}")
    if not game:
        raise ConfigError(f"{toml_path}: required key 'game' is missing")
    # Every optional key must be a non-empty string — a `maps = 3` or `prefabs = ""` would otherwise
    # surface downstream as a raw TypeError / silently alias the project root (review fix).
    for key in ("paths", "catalog", "prefabs", "maps"):
        v = raw.get(key)
        if v is not None and (not isinstance(v, str) or not v.strip()):
            raise ConfigError(f"{toml_path}: key {key!r} must be a non-empty string, got {v!r}")
    return Project(root=os.path.dirname(toml_path), game=game, paths=raw.get("paths"),
                   catalog=raw.get("catalog"), prefabs=raw.get("prefabs"), maps=raw.get("maps"),
                   source=toml_path)


def _project_subdir(project: Project, raw_value: str | None, default_name: str) -> str:
    """Resolve a managed-dir key (catalog/prefabs/maps) against the PROJECT ROOT (its default is a
    bare name under the root); an absolute override is honored verbatim."""
    rel = raw_value if raw_value is not None else default_name
    return os.path.normpath(rel if os.path.isabs(rel) else os.path.join(project.root, rel))


def project_catalog_dir(project: Project) -> str:
    return _project_subdir(project, project.catalog, "texture-catalog")


def project_prefabs_dir(project: Project) -> str:
    return _project_subdir(project, project.prefabs, "prefabs")


def project_maps_dir(project: Project) -> str:
    return _project_subdir(project, project.maps, "maps")


# --------------------------------------------------------------------------- project state dir

def state_dir(root: str | os.PathLike, *, create: bool = False) -> Path:
    """The project's machine-local state dir `<root>/.uedcli` — stash, delivered preview maps,
    locks, staging/tmp. Derivable, throwaway, never tracked. With
    `create=True` the dir is made and, IFF it was absent at the start of THIS call, a
    self-ignoring `.gitignore` containing `*` is written into it (the cargo/direnv pattern —
    direction/projects-and-config.md 2026-07-17 20:58 §3). Detection is `mkdir` catching `FileExistsError` (never a
    blind `exist_ok=True`), so an existing dir is left alone — a user who deliberately deleted
    the ignore file isn't fought."""
    return self_ignoring_dir(Path(root) / ".uedcli", create=create, what="state dir")


def self_ignoring_dir(d: Path, *, create: bool = False, what: str = "dir") -> Path:
    """The shared make-a-self-ignoring-dir mechanic (the cargo/direnv pattern — direction/projects-and-config.md
    2026-07-17 20:58 §3): with `create=True` the dir is made and, IFF it was absent at the start
    of THIS call, a `.gitignore` containing `*` is written into it. Used by `state_dir`
    (`<root>/.uedcli/`) and the catalog-adjacent texture-lock dir (`<catalog>/.locks/`). Every
    failure is a named ConfigError, never a raw OSError traceback."""
    if create:
        try:
            d.mkdir(parents=True)
        except FileExistsError:
            if not d.is_dir():          # path occupied by a FILE → named error, not a
                raise ConfigError(      # NotADirectoryError traceback downstream (review fix)
                    f"{what} path exists but is not a directory: {d} (remove or rename it)")
        except OSError as e:            # unwritable parent (read-only checkout, …) → clean exit 2
            raise ConfigError(f"cannot create {what} {d}: {e}") from e
        else:
            (d / ".gitignore").write_text("*\n")
    return d


def state_subdir(root: str | os.PathLike, name: str, *, create: bool = False) -> Path:
    """A named subdir of the state dir (`stash`/`preview`/`locks`/`tmp`). With `create=True` the
    subdir — and the state dir itself, with its self-ignore — is created."""
    d = state_dir(root, create=create) / name
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d


# --------------------------------------------------------------------------- composition

def select_substrate(project: Project | None, user_config: UserConfig) -> Substrate:
    """The game's base substrate for `project.game`. No default and no sole-game fallback — a project
    must name a game that exists in the user config, else ConfigError listing the known games."""
    if project is None or not project.game:
        raise ConfigError("no game selected: the project must declare `game`")
    sub = user_config.games.get(project.game)
    if sub is None:
        raise ConfigError(f"game {project.game!r} is not in the user config "
                          f"({', '.join(sorted(user_config.games))})")
    return sub


def _composed_dirs_with_provenance(project: Project | None,
                                   user_config: UserConfig) -> list[tuple[str, str]]:
    """The composed search DIRECTORIES, each tagged provenance ('project'|'base'), deduped by
    directory keep-first. Project overlay dirs (resolved against `project.root`) come first, then the
    selected game's base dirs (absolute). A dir listed in BOTH keeps its FIRST ('project') tag — the
    engine's own project-shadows-base search-path shadowing, at directory granularity."""
    tagged: list[tuple[str, str]] = []
    if project is not None and project.paths:
        tagged.extend((d, "project") for d in resolve_dirs(project.paths, project.root))
    base = select_substrate(project, user_config)
    tagged.extend((d, "base") for d in resolve_dirs(base.paths, "/", require_absolute=True))
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for d, prov in tagged:
        if d in seen:
            continue
        seen.add(d)
        out.append((d, prov))
    return out


def composed_search_dirs(project: Project | None, user_config: UserConfig) -> list[str]:
    """The composed search directories (project overlay first, then the game's base), deduped by
    directory keep-first — the absolute HOST dirs that drive the editor/game container mounts
    (direction/containers.md 2026-07-14 03:30). Distinct from `composed_search_files`'s stem-dedup: this is
    directory-dedup (for the mounts), that is package-name-dedup (for the load set)."""
    return [d for d, _prov in _composed_dirs_with_provenance(project, user_config)]


def composed_search_files(project: Project | None,
                          user_config: UserConfig) -> list[tuple[str, str]]:
    """The effective package FILE list — the load-set source consumed by
    `packages.search_path_package_names` / `resources.composed_load_set` and printed by
    `project show`. Each composed dir (`composed_search_dirs`, project-before-base) is SCANNED flat
    (non-recursive, case-INSENSITIVE extension match) for the five package extensions; the resolved
    files are returned as `(host_file, provenance)` tuples, **stem-deduped keep-first** so an
    earlier (project/shadowing) dir's package wins over a same-named later (base) one. Files within a
    dir are ordered case-folded by name for determinism."""
    files: list[tuple[str, str]] = []
    for d, prov in _composed_dirs_with_provenance(project, user_config):
        try:
            names = sorted(os.listdir(d), key=str.casefold)
        except OSError:
            continue
        for name in names:
            if os.path.splitext(name)[1].lower() not in PKG_EXTS:
                continue
            full = os.path.join(d, name)
            if os.path.isfile(full):        # a package-named SUBDIR must not shadow a real package
                files.append((full, prov))
    return _dedup_by_stem(files)


# --------------------------------------------------------------------------- project resolution

def _looks_like_path(token: str) -> bool:
    """Path vs registry-name, by SYNTAX only — never `os.path.exists` (a bare project name that
    happens to match a cwd dir must NOT be silently treated as a path). A path has a separator,
    is `.`/`..`, is absolute, or ends in `.toml`. A bare `name` → registry lookup."""
    return (os.path.sep in token or (os.altsep is not None and os.altsep in token)
            or token in (".", "..") or os.path.isabs(token) or token.endswith(".toml"))


def walk_up_root(start: str) -> str | None:
    """Walk up from `start`; the FIRST ancestor directory containing an `uedcli.toml` FILE is the
    project root (nearest wins — a nested project shadows an outer one, `.git`-style). Returns the
    root dir, None if none found. No child-dir scan, no schema sniffing — the distinctive filename
    is the marker. **A marker that cannot be read or trusted is NEVER climbed past** — climbing
    past one binds the caller to an OUTER project and silently edits the wrong tree — but the two
    cases raise in different places, which matters when tracing an error:

    - **Unreadable/untrustworthy HERE:** a marker this function cannot stat (EACCES) or that is not
      a regular file (a dangling symlink, a symlink loop, a directory) raises `ConfigError` from
      inside `walk_up_root` itself, before any load is attempted.
    - **Malformed at the CALLER:** a marker that stats fine is RETURNED as the root; its content is
      the caller's problem, and `load_project`/`_read_toml` raise the hard `ConfigError` on bad TOML
      or an unreadable-at-open file (spec §4)."""
    cur = Path(start).resolve()
    for anc in (cur, *cur.parents):
        marker = anc / "uedcli.toml"
        try:
            if marker.is_file():
                return str(anc)
            # A present-but-not-a-regular-file marker (dangling symlink, directory) is a hard
            # error, not a skip: climbing past it would bind a nested repo to an OUTER project —
            # the same hazard the unreadable-marker rule forbids (review fix).
            if os.path.lexists(marker):
                raise ConfigError(
                    f"project marker exists but is not a regular file: {marker} "
                    "(dangling symlink or directory? fix or remove it)")
        except OSError as e:
            # An ancestor whose marker cannot even be STAT'ed is a STOP, not a skip. `continue` here
            # contradicted this function's own rule ("an unreadable marker is NOT climbed past") and
            # was actively dangerous: the walk sailed past a project it could not read and bound the
            # caller to an OUTER project, silently editing the wrong tree.
            #
            # In practice this branch is EACCES — a directory the process may not stat into.
            # `Path.is_file` swallows ENOENT, ENOTDIR, EBADF and ELOOP (`pathlib._IGNORED_ERRNOS`)
            # and answers False, so plain absence never reaches here, and neither does a
            # SELF-REFERENCING symlink: ELOOP is ignored, `is_file()` is False, `lexists()` is True,
            # and it lands in the "not a regular file" branch above (verified on CPython 3.12.9,
            # 2026-07-26). Do not describe a symlink loop as reaching this branch — it does not.
            raise ConfigError(
                f"cannot check for a project marker at {marker}: {e.strerror or e} — refusing to "
                "climb past it, since an outer project would then be used instead") from e
    return None


def find_old_layout_project_dir(start: str) -> str | None:
    """Best-effort detection of a RETIRED old-layout project — a `<child>/config.toml` with the
    project schema under some ancestor (the pre-2026-07-17 layout, conventionally `uedcli/`).
    Run ONLY on the no-project failure path to sharpen the error message (spec §8); never a
    supported discovery path. Returns the old project DIR, or None."""
    cur = Path(start).resolve()
    for anc in (cur, *cur.parents):
        try:
            children = sorted(os.listdir(anc))
        except OSError:
            continue
        for c in children:
            child = anc / c
            toml = child / "config.toml"
            try:
                if not child.is_dir() or not toml.is_file():
                    continue
                if _classify(_read_toml(str(toml))) == "project":
                    return str(child)
            except (ConfigError, OSError):
                continue
    return None


def resolve_project(*, project_flag: str | None = None, env_project: str | None = None,
                    cwd: str | None = None, resolve_name=None) -> Project | None:
    """Resolve the current project by the spec §4 precedence — highest wins, no silent default:
      1. `project_flag` (a path to the root dir or the uedcli.toml → load; a bare name →
         `resolve_name` hook, else error: no registry)
      2. `env_project` (UEDCLI_PROJECT; same path/name handling)
      3. walk-up: the nearest ancestor directory containing an `uedcli.toml` file
      4. None (caller decides the error)"""
    cwd = cwd or os.getcwd()
    for source, token in (("--project", project_flag), ("UEDCLI_PROJECT", env_project)):
        if not token:
            continue
        if _looks_like_path(token):
            return load_project(token)
        if resolve_name is not None:
            return resolve_name(token)
        raise ConfigError(
            f"{source}={token!r}: name-based project lookup needs the project registry "
            "(not available yet); pass a path to the project root instead")
    found = walk_up_root(cwd)
    return load_project(found) if found else None

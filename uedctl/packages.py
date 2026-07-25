"""Package-path resolution + fail-fast for materialize. The stored manifest (DIRECT deps,
dxpkg.direct_packages) is the preload list; before MAP NEW + import we resolve every manifest
package to a file on the substrate's package path and, if ANY is missing, fail fast naming the
COMPLETE set — UCC's own `Can't find file for package 'X'` reports only the first miss and
aborts, so checking the full set up front gives the operator the whole list at once. See the
Deus Ex-install spike (dev/docs/spikes/2026-06-18-deusex-content-install.md) for the ensure-load
(absolute `Paths`) mechanism."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

_PKG_EXTS = (".u", ".dx", ".utx", ".uax", ".umx")
# Substrate code packages, already loaded at editor startup (EditPackages) — never explicitly
# OBJ LOAD these: they aren't resolved via the content search dirs the same way, and reloading
# a CODE package live is a different (riskier) operation than reloading a content package.
_ALWAYS_LOADED = {"Engine", "Core", "Editor"}


def editor_search_dirs(search_dirs) -> list[str]:
    """The HOST package search path the editor/game load path resolves manifest packages against,
    in `[Core.System] Paths` precedence order (decisions.md 2026-07-14, stubs-first):

        [ built-stub cache (host), UED22 substrate (host), *composed search dirs (host) ]

    `search_dirs` is the WHOLE composed config dir set (one uniform set — no code/content split). The
    stub cache is FIRST, so a package that has a v69 stub resolves to the stub, shadowing any
    same-named v68 `.u` a composed code dir contributes — the editor never loads the game's own v68
    `.u` for a package it has stubbed. (An UNstubbed v68-only package referenced by a level would
    resolve to its v68 `.u` here — the caller is responsible for stubbing referenced packages first;
    the lazy trigger in `qualify.export_and_qualify` does exactly that.)

    Returns HOST paths — the calling Python process runs on the host and must `os.listdir()` real
    directories. The CONTAINER view (`/stubs`, `/opt/UED22`, `/resources/<n>`) is reached ONLY at
    the one translation boundary `_remap_to_container`, driven by the SAME `mounts` list the caller
    bind-mounted (never recomputed). The stub cache is per-user (`config.stub_cache_root`); UED22
    is the committed substrate, PACKAGE-RELATIVE (`tool_assets.uned_dir()/UED22` — decisions.md
    2026-07-17 20:58 §6, no repo-root walk)."""
    from . import config, tool_assets
    ued22 = tool_assets.uned_dir() / "UED22"
    return [str(config.stub_cache_root()), str(ued22),
            *[str(d) for d in search_dirs]]


def schema_search_dirs(project, user_config) -> list[str]:
    """The dirs for offline class-property SCHEMA extraction (`actor prop` validation, decision
    2026-06-26 14:10) — the WHOLE composed config search path (`config.composed_search_dirs`, one
    uniform set — decisions.md 2026-07-14). `schema_resolver` resolves `<pkg>.u` by extension within
    these, so it finds the game's REAL v68 `.u` (a content dir simply has no `.u` for the name); it is
    NEVER pointed at the v69 stub cache or the UED22 (UT-lineage) substrate, whose `.u` would
    mis-answer inherited `Engine`/`Core` properties. Honest cost: buildability depends on the game's
    v68 code dir being on the config `paths` and present on disk; absent ⇒ a resolve miss ⇒ a hard
    `SchemaError` (no fallback).

    `project is None` or no per-user games config → `[]` (no game selected → no schema code path,
    which the caller turns into a clean `SchemaError`, never a traceback)."""
    if project is None or user_config is None:
        return []
    from . import config
    return config.composed_search_dirs(project, user_config)


def schema_resolver(project, user_config):
    """A resolver `(package_name) -> its real-game `.u` path | None` over `schema_search_dirs`, the
    argument `uprops.resolve_class_properties` consumes to walk a class's Super chain across packages.
    A None result is the no-fallback miss the caller turns into a `SchemaError`."""
    dirs = schema_search_dirs(project, user_config)
    return lambda pkg_name: _first_match({(pkg_name + ".u").lower()}, dirs)


def _present(pkg: str, search_dirs: list[str]) -> bool:
    want = {(pkg + ext).lower() for ext in _PKG_EXTS}
    for d in search_dirs:
        try:
            entries = os.listdir(d)
        except OSError:
            continue
        if any(name.lower() in want for name in entries):
            return True
    return False


def missing_packages(manifest: list[str], search_dirs: list[str]) -> list[str]:
    """The manifest packages with no file on `search_dirs` (case-insensitive), sorted."""
    return sorted(p for p in manifest if not _present(p, search_dirs))


def ensure_load_message(missing: list[str]) -> str:
    return (f"level needs {', '.join(missing)}; not on the package path — materialize aborted "
            "(supply these packages or point the substrate package path at a Deus Ex install)")


def obj_load_entries(manifest: list[str], search_dirs: list[str]) -> list[tuple[str, str]]:
    """(package, absolute file path) pairs to explicitly `OBJ LOAD` before materializing —
    being on `[Core.System] Paths` does NOT auto-demand-load a package referenced only via a
    qualified `Texture=` (unrealed/quirks.md "T3D format" / t3d.md, confirmed live 2026-06-20); every
    manifest content package must be loaded explicitly. Skips `_ALWAYS_LOADED` substrate code
    packages. Silently omits an unresolved package — `missing_packages`'s fail-fast already
    gates materialize before this runs, so every entry here is expected to resolve."""
    out: list[tuple[str, str]] = []
    for pkg in manifest:
        if pkg in _ALWAYS_LOADED:
            continue
        want = {(pkg + ext).lower() for ext in _PKG_EXTS}
        if (entry := _first_match(want, search_dirs)) is not None:
            out.append((pkg, entry))
    return out


def unloadable_v68_packages(entries: list[tuple[str, str]], mounts) -> list[str]:
    """The packages among `obj_load_entries(...)` whose resolved file is a v68 `.u` under a
    config-mount (`/resources/<n>`) — i.e. the game's OWN v68 code, NOT a v69 stub or the UED22
    substrate (those resolve under `/stubs` / `/opt/UED22`, which are never `mounts`). `OBJ LOAD`ing a
    v68 `.u` into the v69 editor GPFs / silently wedges it (the substrate-split incompatibility), so
    the editor-load path must REFUSE these with a clean, named error rather than attempt the load
    (decisions.md 2026-07-14 19:21 — uniform mounts put the game's v68 `.u` on the editor's resolution
    path, guarded only by the v69 stub that shadows it; an UNstubbed one lands here). A resolver
    `remap(file, mounts) is not None` means the file is under a mounted config dir; combined with a
    `.u` extension, that is exactly a game v68 code package with no stub. Returns the offending package
    names, sorted; empty when every entry is a stub / substrate / content package (the safe case)."""
    from . import container_assets
    bad = [pkg for pkg, file_path in entries
           if file_path.lower().endswith(".u") and container_assets.remap(file_path, mounts) is not None]
    return sorted(bad)


def unstubbed_v68_message(packages: list[str]) -> str:
    return (f"level references v68 code package(s) with no v69 stub: {', '.join(packages)} — "
            f"the v69 editor cannot load a v68 `.u` directly; build the stub(s) first "
            f"(`uedctl substrate stub <pkg>`) or the referencing level cannot materialize")


def search_path_package_names(files: list[tuple[str, str]]) -> list[str]:
    """The bare package NAMES on a composed search path (config.composed_search_files output) — the
    load set for `level materialize`/`level preview` (decision 2026-07-05 23:00: load the whole
    composed search path; no per-level derivation, no closure walk). One name per package file, in the
    caller's already-stem-deduped order. NOTE: ensure_load re-resolves each name against its threaded
    HOST `search_dirs` (`editor_search_dirs(search_dirs)` = stub cache + UED22 + the whole composed
    dirs) and remaps to the container-visible roots via the SAME `mounts` (asset-wiring cutover
    2026-07-14) — a name whose file resolves under a bind-mounted config dir loads at its
    `/resources/<n>` path."""
    from .config import pkg_stem
    return [s for host_path, _prov in files if (s := pkg_stem(host_path)) is not None]


def _first_match(want: set[str], search_dirs: list[str]) -> str | None:
    for d in search_dirs:
        try:
            entries = os.listdir(d)
        except OSError:
            continue
        for name in entries:
            if name.lower() in want:
                return os.path.join(d, name)
    return None


# Flat and lowercase -- confirmed live 2026-06-20 against both the persistent dx-lum-uned
# container and a fresh ephemeral (per-command) editor container; no "System/" subdirectory exists anywhere in this
# substrate. The previous "/opt/UED22/System/UnrealTournament.ini" was wrong and, being
# integration-only, had apparently never actually been exercised against a live container.
_EDITOR_INI = "/opt/UED22/unrealtournament.ini"


def write_paths_and_reload(container: str, path_lines: list[str]) -> None:
    """LIVE ini edit: ensure the given `[Core.System] Paths=…` lines are present so
    MAP NEW/IMPORTADD/LOAD can resolve the manifest packages (Deus Ex-install spike).
    Integration-only (the offline suite never calls this). `path_lines` are FULL, ready-to-write
    ini lines (`"Paths=/resources/r000/*"`, …) — the container-visible wildcard set from
    `container_assets.paths_ini_lines(mounts)` (asset-wiring cutover 2026-07-14 — was the
    per-manifest-package absolute-path list). `ensure_editor` already writes this same set into the
    ini PRE-LAUNCH via a byte-exact bind-mount, so live this is an idempotent belt-and-suspenders
    (any line already present is skipped). Shared by `apply._materialize` (before a FULL RE-IMPORT)
    and `qualify.export_and_qualify` (before a `MAP LOAD`)."""
    existing = subprocess.run(["docker", "exec", container, "cat", _EDITOR_INI],
                              text=True, capture_output=True, check=True).stdout
    new = [ln for ln in path_lines if ln not in existing]
    if not new:
        return
    # GNU sed's `a` one-liner form (`a text`) only accepts a SINGLE line — a literal embedded
    # newline terminates its text early and leaves the remainder as an invalid dangling command
    # ("extra characters after command"). Confirmed live 2026-06-20: this had never actually
    # been exercised with 2+ paths before (integration-only). The correct multi-line form needs
    # a backslash-continued newline between `a\` and EVERY line, including between entries.
    script = "/^\\[Core.System\\]/a\\\n" + "\\\n".join(new)
    subprocess.run(["docker", "exec", container, "sed", "-i", script, _EDITOR_INI],
                   check=True, capture_output=True, text=True)


# Container baked/host-cached prefixes for resolved host package files NOT under a `/resources`
# content mount (asset-wiring cutover 2026-07-14 — the `/deusex` + `/content` roots are gone; all
# config CONTENT is a `/resources/<n>` bind mount reached via `container_assets.remap`). UED22 is
# baked into the image; the built-stub cache is a baked-adjacent `/stubs` mount.
_BAKED_UED22 = "/opt/UED22"
_STUBS_MOUNT = "/stubs"


def _stub_cache_dir() -> Path:
    """The built-stub cache dir — the SINGLE source of truth, `config.stub_cache_root()`
    (per-user `~/.uedctl/cache/stubs/`)."""
    from . import config
    return config.stub_cache_root()


def _is_relative_to(p: Path, base: Path) -> bool:
    try:
        p.relative_to(base)
        return True
    except ValueError:
        return False


def _remap_to_container(host_path: str, mounts) -> str:
    """Map a HOST-resolved package file path to where it is visible INSIDE the container, using the
    SAME `mounts` list the caller bind-mounted (never recomputed — decisions.md 2026-07-14). Three
    container-visible roots, in this order:
      - a file under a config CONTENT mount → its `/resources/<n>/…` (`container_assets.remap`);
      - a built-stub-cache file → `/stubs/…`;
      - a UED22 substrate file → `/opt/UED22/…`.
    Raises ValueError on a path under none of them (a resolution bug — fail loud). The `/deusex` and
    `/content` roots are gone (asset-wiring cutover — all content is a `/resources` mount); the
    UED22 host root is PACKAGE-RELATIVE (`tool_assets.uned_dir()` — 2026-07-17 20:58 §6)."""
    from . import container_assets, tool_assets
    cont = container_assets.remap(host_path, mounts)
    if cont is not None:
        return cont
    p = Path(host_path)
    ued22 = tool_assets.uned_dir() / "UED22"
    stub_cache = _stub_cache_dir()
    if _is_relative_to(p, stub_cache):
        return f"{_STUBS_MOUNT}/{p.relative_to(stub_cache).as_posix()}"
    if _is_relative_to(p, ued22):
        return f"{_BAKED_UED22}/{p.relative_to(ued22).as_posix()}"
    raise ValueError(f"package file {host_path!r} is under no container-visible root "
                     f"(a /resources content mount, the /stubs cache, or /opt/UED22)")


def ensure_load(driver, manifest: list[str], *, search_dirs: list[str], mounts) -> None:
    """The full ensure-load: the `Paths` ini-edit (so any OTHER indirect package resolution still
    works) PLUS an explicit `OBJ LOAD` per resolvable package (2026-06-20 — being on `Paths` alone
    does NOT auto-demand-load a package a qualified `Texture=` references, confirmed live both for
    `MAP IMPORTADD` and `MAP LOAD`; see `unrealed/quirks.md` "T3D format" / `unrealed/t3d.md` and
    `unrealed/quirks.md` "Stability"). Skips `_ALWAYS_LOADED` substrate code packages.

    `search_dirs` are HOST dirs (`editor_search_dirs(dirs)` = `[stub cache, UED22, *composed
    dirs]`) — required, since the calling Python process runs on the host and must `os.listdir()`
    real directories. `obj_load_entries` resolves each manifest package to its HOST file over them.
    `mounts` is the SAME `container_assets.resource_mounts(dirs)` list threaded from the
    caller (asset-wiring cutover 2026-07-14): the `[Core.System] Paths` is the FULL container-visible
    wildcard set (`container_assets.paths_ini_lines(mounts)`, incl. `/stubs`+`/opt/UED22`, REGENERATED
    — not the old per-package absolute list), and every resolved host path is remapped to its
    container path via `_remap_to_container(…, mounts)` at this one boundary before reaching either
    container-facing call."""
    from . import container_assets
    entries = obj_load_entries(manifest, search_dirs)
    # GATE (decisions.md 2026-07-14 19:21): with the uniform mounts the game's v68 `.u` is on the
    # editor's resolution path, safe ONLY where a v69 stub shadows it. Refuse to `OBJ LOAD` any
    # package that resolves to a v68 `.u` under a config-mount with no stub — a clean named error
    # BEFORE any editor command, never a silent v69-loads-v68 wedge.
    if bad := unloadable_v68_packages(entries, mounts):
        raise RuntimeError(unstubbed_v68_message(bad))
    write_paths_and_reload(driver.container, container_assets.paths_ini_lines(mounts))
    for pkg, file_path in entries:
        # A prior OBJ LOAD's garbage-collect pass can pop the "Cleaning up…" dialog (quirks.md
        # "Stability"), which blocks the NEXT command's keystrokes from reaching the Command box —
        # so a later OBJ LOAD wedges/times out with an empty error (the crash-prone editor amplified
        # by many loads). Dismiss it before each, exactly as dump_obj_dependencies does defensively.
        driver.dismiss_blocking_dialog()
        driver.obj_load(pkg, _remap_to_container(file_path, mounts))

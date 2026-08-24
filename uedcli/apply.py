"""level materialize orchestration — build a TRUNK Level into a `.dx`/`.unr` map file.

PURE BUILD (git-native): `run_materialize` spins a per-command ephemeral editor, FULL RE-IMPORTs
the merged level, MAP SAVEs it, H3-post-verifies it offline in that same container, and atomically
swaps the artifact in. No session, no 3-way merge, no backup, no git wrapping — those (and the whole
session-store core) were deleted in git-native slice 6.

H3/D-G: the post-verify oracle is the INTENDED level built from the result (`_expected_level`), in
the materialized (LevelInfo-first) order — NEVER a re-export of the ephemeral editor we just drove
(a self-referential verify is no verify)."""
from __future__ import annotations

import errno
import os
import re
import shutil
import struct
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path

from .driver import Driver, DriverError
from .editor import ensure_editor, stop_editor
from .uuid7 import uuid7
from .verify import verify_dx_matches


@dataclass(frozen=True, kw_only=True)
class ApplyResult:
    rc: int
    blocked: bool = False
    message: str = ""
    apply_uuid: str | None = None
    bsp_notes: str = ""        # advisory BSP-health stderr text (never affects rc; see run_materialize)


def _materialized_order(result: dict[str, str], result_order: list[str]) -> list[str]:
    """The order the editor actually imports in: LevelInfo first, then every point actor, then
    every brush (D-I; see `levelinfo_first_order`'s docstring). expected, the result snapshot,
    AND the import all use THIS order so post-verify's order-hash agrees with the on-disk order
    (M1 — a raw result_order with LevelInfo not-first, or points/brushes interleaved, would
    mis-match the on-disk order)."""
    from .materialize import levelinfo_first_order
    from .model import parse_t3d
    parsed = {n: next(iter(parse_t3d(result[n]).actors.values())) for n in result}
    classes = {n: a.cls for n, a in parsed.items()}
    has_brush = {n: a.brush is not None for n, a in parsed.items()}
    return levelinfo_first_order(result_order, classes, has_brush)


def _level_referenced_packages(level) -> list[str]:
    """The package names the level's own actors REFERENCE — the SET materialize must `OBJ LOAD` so
    those refs bind, derived from each actor's qualified `Class=` (`Package.Class`) and each brush
    poly's `Texture=` (`Package[.Group].Name`). Only these, NOT the whole composed install
    (decision 2026-07-14, superseding the 2026-07-05 "wire the whole composed search path" load): a
    real Deus Ex install is ~240 packages, and `OBJ LOAD`ing every one is both O(install) and a
    reliability sink — each command is another chance for the crash-prone editor to wedge silently
    (mass-load reproduced: 214 `OBJ LOAD`s for a castle that references ONE package). The whole
    composed set still populates the `[Core.System] Paths` (via the mounts) so any INDIRECT
    demand-load still resolves; only the explicit preload shrinks to what the level actually uses. A
    BARE ref (no `Package.` qualifier) contributes nothing here — it has no package to name; its
    resolution rides the Paths. Engine/Core/Editor are dropped by `obj_load_entries`' `_ALWAYS_LOADED`
    filter downstream.

    Also every OBJECT/CLASS ref in a prop value (`Sound'MoverSFX.door.X'`, `Class'DeusEx.Ammo10mm'`,
    …): a mover imported via `MAP IMPORTADD` drops a `ClosedSound=Sound'MoverSFX…'` whose package the
    editor has not loaded (unlike a MAP-LOADed import, an IMPORTADD ref does not demand-load), so its
    package must be preloaded too. The level's OWN package (its intra-level `LevelInfo'<map>.…'`/nav
    refs) is excluded — it is not a loadable dependency."""
    pkgs: set[str] = set()
    self_pkgs = {m.group(1) for a in level.actors.values() for _k, v in a.props
                 for m in _NAV_SELF_REF.finditer(v)}
    for a in level.actors.values():
        if a.cls and "." in a.cls:
            pkgs.add(a.cls.split(".", 1)[0])
        if a.brush is not None:
            for p in a.brush.polys:
                if p.texture and "." in p.texture:
                    pkgs.add(p.texture.split(".", 1)[0])
        for _k, v in a.props:
            for m in _OBJ_REF_PKG.finditer(v):
                pkgs.add(m.group(1))
    return sorted(pkgs - self_pkgs - {"MyLevel"})


# An object/class ref value `Class'Package[.Group].Name'` -> its root package. The level's own
# package is stripped separately (via `_NAV_SELF_REF`, the same nav/zone-ref probe `_materialize`
# uses to detect the self-package).
_OBJ_REF_PKG = re.compile(r"[A-Za-z_]\w*'([A-Za-z0-9_]+)\.")
_NAV_SELF_REF = re.compile(r"'([A-Za-z0-9_]+)\.(?:PathNode|PatrolPoint|HidePoint|ZoneInfo|LevelInfo)\d")


def _expected_level(result: dict[str, str], materialized_order: list[str]):
    """The INTENDED level (design D-G/H3) — built from the result, NOT from re-exporting the
    ephemeral editor we just drove (a self-referential verify is no verify)."""
    from .model import Level, parse_t3d
    lv = Level()
    for name in materialized_order:
        lv.actors[name] = next(iter(parse_t3d(result[name]).actors.values()))
    lv.order = list(materialized_order)
    return lv


def _materialize(driver, *, result: dict[str, str], materialized_order: list[str],
                 packages: list[str], search_dirs: list[str] | None = None,
                 mounts=None) -> None:
    """Build the merged level via an assembled UNBUILT `.dx` + `MAP LOAD` — never `MAP NEW` +
    `EDIT PASTE`. The editor's paste GPFs building the brush model of complex retail geometry (e.g.
    `02_NYC_Warehouse`, high-poly curved brushes); `MAP LOAD` of a `.dx` whose brush shapes AND
    typed actor props we WROTE ourselves (`native.unbuilt.assemble_unbuilt`) avoids the add path
    entirely, and carries every authored value (structs, arrays, movers' keyframes, `PrePivot`) no
    console verb can express. EVERY actor -- movers included -- is written into the package in trunk
    order, so the built `Actors` array is 100% faithful (no `MAP IMPORTADD` append). Movers carry
    their key-0 base pose in `BasePos`/`BaseRot` (`set_base_pose`), which the editor derives on IMPORT
    but not on `MAP LOAD`; `MAP REBUILD` then builds each mover's private model and the world CSG.
    Records into the caller's `begin_script` EXEC batch; the eager side-effects
    (assembling the `.dx`, writing the /work files, the ini `Paths` edit) run live so the script's
    inputs exist before it runs.

    `search_dirs`/`mounts` are the config-derived HOST search path + `/resources` bind mounts
    (asset-wiring cutover 2026-07-14); the SAME `mounts` drives the ini `Paths` and the host→
    container remap. Integration-exercised (no live driver in the offline suite)."""
    import sys
    from .model import Level, parse_t3d
    from .native.unbuilt import assemble_unbuilt, substrate_schema
    from .packages import ensure_load
    from .driver import to_z_path

    # The trunk keeps some intra-level refs (nav/zone build-output: `previousPath`, `FootRegion.Zone`,
    # `Paths`, …) qualified with the ORIGINAL map's package name; `assemble_unbuilt` treats a ref as
    # internal only when it reads `MyLevel.`, so anything else becomes a package import that `MAP
    # LOAD` refuses ("Can't import private object PathNode …") — and a failed load silently saves an
    # EMPTY map. `EDIT PASTE` tolerated these; `MAP LOAD` does not. These refs are regenerated by
    # PATHS BUILD / on load, so rewriting the level's own package to `MyLevel` does not change the
    # built result. Detect the self-package from a nav/zone ref, then rewrite it everywhere.
    self_pkgs = {m for text in result.values() for m in _NAV_SELF_REF.findall(text)}
    self_pkgs.discard("MyLevel")
    if self_pkgs:
        result = dict(result)
        for name, text in result.items():
            for pkg in self_pkgs:
                text = text.replace(f"{pkg}.", "MyLevel.")
            result[name] = text

    # Build the merged level in materialized (CSG-precedence) order — LevelInfo first, points, then
    # brushes; the brush subsequence keeps its order_value order, which is what CSG reads.
    level = Level()
    for name in materialized_order:
        a = next(iter(parse_t3d(result[name]).actors.values()))
        a.name = name
        level.actors[name] = a
    level.order = list(materialized_order)

    pkg_dirs = [str(d) for d in (search_dirs or [])]
    from pathlib import Path as _P
    from .classindex import ClassIndex
    from .movers import set_base_pose
    index = ClassIndex.from_files([(f.stem, str(f)) for d in pkg_dirs
                                   for f in sorted(_P(d).glob("*.u"))])
    # Movers carry their key-0 base pose in BasePos/BaseRot; the editor derives those on IMPORT but
    # NOT on MAP LOAD, so write them ourselves or REBUILD zeroes the mover's Location.
    for name in level.order:
        set_base_pose(level.actors[name], index)

    # Assemble the unbuilt .dx (EVERY actor -- movers included -- with real brush polys) and stage it
    # in /work. Movers go into the package like any other brush actor, in their trunk order, so the
    # built `Actors` array is 100% faithful (no `MAP IMPORTADD` append). MAP REBUILD builds each
    # mover's private brush Model from its polys, exactly as it builds the world model.
    # The writer types every prop against the SAME schema set the EDITOR loads (`substrate_schema`
    # over the editor search path: UED22 `Engine.u` + the game `.u`), NOT the game-only schema the
    # post-verify uses. They differ on the Engine.Actor props DeusEx added (`bOwned`,
    # `DistanceFromPlayer`, …): serializing a prop the editor's Engine class does not know wedges its
    # MAP LOAD. The dropped props are handled on the verify side (the edit-rule + editor-schema-gap
    # list) — never by feeding the editor a tag it cannot parse.
    dx_bytes, warnings = assemble_unbuilt(level, schema=substrate_schema(*pkg_dirs),
                                          pkg_dirs=pkg_dirs)
    for w in warnings:
        print(f"warning: {w}", file=sys.stderr)
    unbuilt_path = driver.write_work_file(dx_bytes, ext="dx")

    # Record the drive: OBJ LOAD the referenced packages, MAP LOAD the unbuilt .dx, MAP REBUILD.
    # `ensure_load` writes the ini Paths (eager) and records the OBJ LOADs.
    ensure_load(driver, packages, search_dirs=pkg_dirs, mounts=mounts or [])
    driver.exec(f"MAP LOAD FILE={to_z_path(unbuilt_path)}")
    driver.rebuild()


def _install_atomic(*, staging_host: str, target_host: str) -> None:
    """Move the verified .dx from host staging onto the target by atomic rename. The default
    staging dir is `.uedcli/tmp/` (same filesystem as an in-repo target → os.replace is atomic,
    no leak). `os.replace` raises EXDEV only for an out-of-repo target on a DIFFERENT filesystem
    (a SUPPORTED input, spec B3): copy host-side (the bytes are already on the host in
    `staging_host` by the time this runs) into a temp IN the target's own directory and rename
    from there — same-fs by construction.

    Cleans up BOTH the staging temp and, on the EXDEV path, the target-dir temp — on EVERY exit,
    including a failed second rename — so no dotfile is ever stranded beside the target."""
    target_dir_tmp = None
    try:
        try:
            os.replace(staging_host, target_host)
            return
        except OSError as e:
            if e.errno != errno.EXDEV:
                raise
        target_dir_tmp = os.path.join(os.path.dirname(target_host) or ".",
                                      f".{uuid.uuid4().hex}.uedcli-tmp.dx")
        shutil.copyfile(staging_host, target_dir_tmp)
        os.replace(target_dir_tmp, target_host)
        target_dir_tmp = None        # renamed away — nothing left for the finally to clean up
    finally:
        Path(staging_host).unlink(missing_ok=True)
        if target_dir_tmp is not None:
            Path(target_dir_tmp).unlink(missing_ok=True)


def _level_defaults(level, *, resolver):
    """Resolve the CLASS DEFAULTS of every distinct class in `level`, BEFORE any container exists.
    Returns a `classdefaults.ClassDefaults`.

    The post-verify resolves both compare sides to their effective TYPED values against these
    (`normalize.compare_view`), so a class whose schema/defaults cannot be decoded is fatal — there
    is deliberately no "assume zero" fallback, since assuming zero is the bug the typed compare
    removes. Resolving up front means an unresolvable class costs ~0.1 s and a clean exit 2 instead
    of surfacing after a ~100 s editor build. Cost is per-CLASS, not per-actor (one shared package
    map + memo): ~0.1-0.3 s for the first class (a package load, the Super-chain property walk, the
    defaults decode and every struct/enum layout), ~0.01-0.03 s each after.

    The error names the ACTOR as well as the class — a bare `Class=Camera` is a property of one
    actor in the trunk, and "class 'Camera' is not fully qualified" alone leaves the user to grep
    the whole level for it — and it names the two remedies, because this check REFUSES cases that
    used to build: a bare class that the live editor's own loaded-class set would have resolved
    (`qualify.requalify_classes_to_loaded` leaves a class bare only when the editor offers 0 or 2+
    candidates), and a class in a package that is not on the project's `paths`."""
    from .classdefaults import ClassDefaults
    from .uprops import SchemaError
    first_actor: dict[str, str] = {}
    for name in sorted(level.actors):
        first_actor.setdefault(level.actors[name].cls, name)
    defaults = ClassDefaults(resolver)
    for cls in sorted(first_actor):
        try:
            defaults.for_class(cls)
        except SchemaError as e:
            raise SchemaError(
                f"cannot verify actor {first_actor[cls]!r} — {e}. Qualify the class as "
                f"Package.Class and make sure its package is on the project's search paths, or "
                f"re-run with --no-verify to build without the post-verify") from None
    return defaults


def _save_and_swap_verified(ed, dx_path: str, expected, *, work_out, defaults, state_dir, index,
                            schema, no_verify: bool = False, keep_build: bool = False,
                            ignore: frozenset[tuple[str, str]] = frozenset()) -> None:
    """Given the map ALREADY saved to `work_out` (the `MAP SAVE` is the last line of the build
    script `run_materialize` runs), `cp_out` it to host staging (`<state_dir>/tmp/<uuid>.dx`),
    H3-verify it OFFLINE from that file (`verify_dx_matches` decodes the `.dx` directly — no second
    editor round-trip), then atomic host `os.replace` onto the target (EXDEV fallback for an
    out-of-project target). No container-written temp ever lands in the repo tree.

    `state_dir` is the resolved project's `.uedcli/` state dir, threaded from dispatch — staging
    lives under its `tmp/` precisely so `os.replace` onto an in-project `--out` stays same-filesystem.
    `index`/`schema` type the offline decode. `no_verify` skips the verify gate; `keep_build` copies
    the built map to `<state_dir>/tmp/materialize-rejected.dx` on a verify FAILURE for inspection."""
    from . import xfer
    tmp_dir = Path(state_dir) / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    staging = tmp_dir / f"{uuid.uuid4().hex}.dx"
    # A relative --out resolves against the CWD (standard CLI semantics — direction/projects-and-config.md
    # 2026-07-17 20:58; the repo-root join + legacy `/repo/` remap died with repo_paths).
    target_host = os.path.abspath(dx_path)
    try:
        xfer.cp_out(ed.container, work_out, str(staging))    # host copy: verified offline AND swapped in
        if not no_verify:
            vr = verify_dx_matches(dx_path=str(staging), expected=expected, defaults=defaults,
                                   index=index, schema=schema, ignore=ignore)
            if not vr.ok:
                msg = vr.message
                if keep_build:                       # preserve the rejected build for inspection
                    kept = tmp_dir / "materialize-rejected.dx"
                    shutil.copyfile(str(staging), str(kept))
                    msg += f"\n(--keep-build: built map kept at {kept} for inspection)"
                raise RuntimeError(msg)
        # _install_atomic is the SOLE owner of staging cleanup on its own paths.
        _install_atomic(staging_host=str(staging), target_host=target_host)
    finally:
        Path(staging).unlink(missing_ok=True)                # if verify raised before the swap
        # Always reclaim the editor's /work temp — including when map_save/verify raise (the editor
        # is crash-prone), not just on the success path.
        xfer.remove(ed.container, work_out)


_MAP_EXTS = (".dx", ".unr")


def run_materialize(*, level, out_path, overwrite, state_dir, schema_resolver,
                    search_dirs=None, no_verify=False, keep_build=False,
                    no_bsp_check=False, ignore_props=()) -> ApplyResult:
    """Materialize a TRUNK Level into `out_path` (.dx/.unr) via a PER-COMMAND EPHEMERAL editor, H3-
    post-verify it offline in that same container, and swap it in. PURE BUILD (git-native slice 3):
    no session, no 3-way merge, no backup, no git wrapping. Refuses to overwrite unless `overwrite`.
    `search_dirs` is the whole composed config dir set (`resources.composed_dirs`); the `mounts`
    (`/resources/<n>` bind mounts) and the HOST resolution list are computed ONCE here from it and
    threaded to `ensure_editor` +
    `ensure_load` — the single mount list drives the ini `Paths`, the docker `-v` args, and the
    host→container remap (direction/containers.md 2026-07-14 — one uniform dir set; `/stubs` first on Paths so a
    v69 stub shadows any same-named v68 `.u`). `state_dir` is the resolved project's `.uedcli/`
    state dir (`config.state_dir(project.root, create=True)`, threaded from dispatch/preview) —
    hosts the ephemeral editor's crafted inis and the staging temps. `schema_resolver` is the
    package-name→path resolver (`packages.schema_resolver(project, user_config)`) the post-verify
    decodes the class schema + defaults through — REQUIRED, because the verify resolves both
    compare sides to their effective typed values against the real class defaults and has no zero
    fallback. The live drive is
    integration-exercised; every guard below is offline-testable with a mocked editor."""
    from .normalize import canonical_actor_t3d
    from .uprops import SchemaError
    if not out_path:
        return ApplyResult(rc=2, message="level materialize requires --out <path>")
    if Path(out_path).suffix.lower() not in _MAP_EXTS:
        return ApplyResult(rc=2, message=f"--out needs a .dx or .unr path: {out_path}")
    # Resolve to the SAME host path the write will use: a relative --out joins the CWD (standard
    # CLI semantics), so the overwrite guard and `_save_and_swap_verified`'s target agree.
    host_out = Path(os.path.abspath(out_path))
    if host_out.is_dir():
        return ApplyResult(rc=2, message=f"--out is a directory: {out_path}")
    if host_out.exists() and not overwrite:
        return ApplyResult(rc=2, message=f"refusing to overwrite existing file: {out_path} "
                                         "(pass --overwrite to rebuild in place)")
    result = {n: canonical_actor_t3d(a) for n, a in level.actors.items()}
    mo = _materialized_order(result, level.order)
    # Per-game `ignore_props` (`Package.Class.prop`): authored props the game adds to a base class
    # that the materialize editor's engine package lacks, so they can never round-trip. The compare
    # ignores them -- but NEVER silently: warn once, naming each, since the built map genuinely drops
    # authored content (the fix is a patched editor engine package, tracked separately).
    ignore = frozenset((c.casefold(), p.casefold())
                       for c, _, p in (e.rpartition(".") for e in ignore_props))
    if ignore and not no_verify:
        stated = {k.split("(")[0].casefold() for a in level.actors.values() for k, _ in a.props}
        present = sorted({f"{c}.{p}" for c, p in ignore if p in stated})
        if present:
            import sys as _sys
            print(f"warning: post-verify ignoring per-game props (editor engine lacks them, so "
                  f"materialize drops them): {', '.join(present)}", file=_sys.stderr)
    # Class defaults FIRST — before the ~100 s editor build, so an unresolvable class fails in
    # ~0.1 s with a message naming the actor. `no_verify` skips the post-verify entirely, so it
    # must not require them either (that flag exists precisely for a broken/unavailable verify).
    defaults = None
    if not no_verify:
        try:
            defaults = _level_defaults(level, resolver=schema_resolver)
        except SchemaError as e:
            return ApplyResult(rc=2, message=f"materialize failed (nothing written): {e}")
    # The whole composed config dir set drives the mounts (bind mounts + ini Paths) and the HOST
    # resolution list, computed ONCE and threaded to ensure_editor + ensure_load (one uniform dir
    # set — direction/containers.md 2026-07-14). `/stubs` stays first on Paths, so a v69 stub shadows any
    # same-named v68 `.u` a code dir puts on the editor's Paths.
    from .container_assets import resource_mounts
    from .packages import editor_search_dirs, missing_packages, ensure_load_message, _ALWAYS_LOADED
    search_dirs = search_dirs or []
    mounts = resource_mounts(search_dirs)
    host_search_dirs = editor_search_dirs(search_dirs)
    # The offline post-verify decodes the built `.dx` itself (no editor round-trip) -> it needs a
    # ClassIndex + ImportSchema over the game `.u`. Built ONCE here and threaded to the verify.
    verify_index = verify_schema = None
    if not no_verify:
        from pathlib import Path as _P
        from .classindex import ClassIndex
        from .mapimport import ImportSchema
        verify_index = ClassIndex.from_files([(f.stem, str(f)) for d in host_search_dirs
                                              for f in sorted(_P(d).glob("*.u"))])
        verify_schema = ImportSchema(resolver=schema_resolver)
    # Fail-fast BEFORE the ~100 s editor build: a package the level REFERENCES but that is absent from
    # the host search path would otherwise be silently dropped (every face's `Texture=` / actor's
    # `Class=` gone) and surface only as an opaque post-verify mismatch — or, under `--no-verify`, ship
    # a wrong map with no signal. So the gate is verify-INDEPENDENT. `_ALWAYS_LOADED` is substrate code
    # always resident, excluded exactly as `obj_load_entries` excludes it, so a level referencing
    # `Engine.Light` does not false-miss.
    referenced = [p for p in _level_referenced_packages(level) if p not in _ALWAYS_LOADED]
    if missing := missing_packages(referenced, host_search_dirs):
        return ApplyResult(rc=2, message="materialize failed (nothing written): "
                                         f"{ensure_load_message(missing)}")
    ed_id = uuid7()                                    # bare uuid → editor_container keeps all groups
    bsp_notes = ""
    try:
        ed = Driver(container=ensure_editor(ed_id, mounts=mounts, state_dir=state_dir))
        # OBJ LOAD only the packages the level REFERENCES (not the whole composed `packages` set —
        # `_level_referenced_packages`, decision 2026-07-14): the whole set still lands in `Paths`
        # via `mounts`, so indirect demand-loads resolve, but the explicit preload shrinks from
        # ~240 to what the level uses — O(level), and far fewer chances for the editor to wedge.
        # Record the log offset BEFORE the build so the BSP build-output check can read the
        # MAP REBUILD warnings out of the slice (guarded: a failure here just skips that check).
        bsp_log_off = None
        if not no_bsp_check:
            try:
                bsp_log_off = ed.log_size()
            except Exception:
                bsp_log_off = None
        # The whole write-only drive goes into ONE `EXEC <file>` (spike 2026-07-18): the engine runs
        # the verbs in-order through its own exec loop, so no slow verb (a retail `MAP REBUILD` runs
        # ~90 s+) can swallow the next verb's keystroke the way the typed console does — the failure
        # that left `MAP SAVE` unheard and wedged every real map. `begin_script` buffers each
        # `exec`-routed verb; the eager side-effects inside `_materialize` (the ini `Paths` edit, the
        # IMPORTADD source files, the paste clipboard) still run live so the script's files exist
        # before it runs. `run_script` submits the EXEC and waits for the `MAP SAVE` .dx.
        from . import xfer
        from .driver import to_z_path
        work_out = xfer.work_path("dx")
        ed.begin_script()
        _materialize(ed, result=result, materialized_order=mo,
                     packages=_level_referenced_packages(level),
                     search_dirs=host_search_dirs, mounts=mounts)
        ed.light_apply()                               # _materialize's MAP REBUILD wiped lighting
        ed.exec(f"MAP SAVE FILE={to_z_path(work_out)}")
        ed.run_script(produces=work_out)
        host_out.parent.mkdir(parents=True, exist_ok=True)
        _save_and_swap_verified(ed, out_path, _expected_level(result, mo), work_out=work_out,
                                defaults=defaults, state_dir=state_dir, index=verify_index,
                                schema=verify_schema, no_verify=no_verify,
                                keep_build=keep_build, ignore=ignore)
        # Build+save succeeded: run the two advisory BSP health checks (owner design 2026-08-03).
        # ADVISORY ONLY — the map is already written; these must never turn a good build into a
        # failure, so the whole block is guarded and the rc stays 0 no matter what they find/raise.
        if not no_bsp_check:
            try:
                from .bsp.checks import run_bsp_checks
                bsp_notes = "\n".join(run_bsp_checks(ed, log_offset=bsp_log_off,
                                                     dx_path=str(host_out)))
            except Exception as e:
                bsp_notes = f"materialize: BSP health check skipped ({type(e).__name__}: {e})"
    except (DriverError, RuntimeError, TimeoutError, ValueError, OSError,
            struct.error, subprocess.CalledProcessError) as e:
        # OSError covers the crafted-ini write in ensure_editor (`_write_engine_ini`) and any
        # host-fs failure (unwritable .uedcli/tmp, missing base ini) — never a bare traceback.
        # ValueError covers `uprops.SchemaError` (a ValueError subclass): the post-verify resolves
        # class defaults for the RE-EXPORTED map too, whose classes are requalified against the
        # live editor and can still come back bare (0 or 2+ candidates) — a clean exit 2, not a
        # traceback, and nothing is written because the swap happens after the verify.
        return ApplyResult(rc=2, message=f"materialize failed (nothing written): {e}")
    finally:
        stop_editor(ed_id, state_dir)                  # always tear the ephemeral container down
    return ApplyResult(rc=0, message=f"materialized {out_path}", bsp_notes=bsp_notes)

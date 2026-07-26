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
import shutil
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
    filter downstream."""
    pkgs: set[str] = set()
    for a in level.actors.values():
        if a.cls and "." in a.cls:
            pkgs.add(a.cls.split(".", 1)[0])
        if a.brush is not None:
            for p in a.brush.polys:
                if p.texture and "." in p.texture:
                    pkgs.add(p.texture.split(".", 1)[0])
    return sorted(pkgs)


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
                 packages: list[str], search_dirs: list[str] | None = None, mounts=None) -> None:
    """FULL RE-IMPORT the merged level into the live editor (D-I order). Integration-exercised
    (H-1) — the live driver/UCC path. ensure_load (`packages.ensure_load`, shared with
    `qualify.export_and_qualify` since 2026-06-20) writes the container-visible `Paths` set AND
    explicitly `OBJ LOAD`s every package before the import — both integration-only (offline suite
    never reaches them — no live driver). `search_dirs`/`mounts` are the config-derived HOST search
    path + `/resources` bind mounts threaded from `run_materialize` (asset-wiring cutover
    2026-07-14); the SAME `mounts` drives both the ini `Paths` and the host→container remap."""
    from .materialize import materialize
    from .model import parse_t3d
    from .geometry import validate_brush
    from .packages import ensure_load
    from . import writes

    def parse_actor(t3d):
        return next(iter(parse_t3d(t3d).actors.values()))

    materialize(driver=driver,
                current_actors={}, merged_actors=result,
                current_order=[], merged_order=materialized_order,
                parse_actor=parse_actor, validate_brush=validate_brush,
                re_add=lambda actors: writes._re_add(driver, actors),
                delete_named=lambda names: None, rebuild=driver.rebuild,
                packages=packages,
                ensure_load=lambda pkgs: ensure_load(driver, pkgs, search_dirs=search_dirs or [],
                                                     mounts=mounts or []))


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


def _save_and_swap_verified(ed, dx_path: str, expected, *, defaults, state_dir,
                            no_verify: bool = False, keep_build: bool = False) -> None:
    """MAP SAVE to /work → H3 verify in the EDITOR container (B1: the editor's /work is private to
    it, so the saved temp must be re-exported there, not in the substrate container) → cp_out to
    `<state_dir>/tmp/<uuid>.dx` → atomic host `os.replace` onto the target (EXDEV fallback for an
    out-of-project target). No container-written temp ever lands in the repo tree. D-Q3: the verify
    ALSO qualifies the re-exported actual via `ed` — the SAME live editor that just materialized +
    saved it, no second container. Integration-exercised.

    `state_dir` is the resolved project's `.uedcli/` state dir (`config.state_dir`), threaded from
    dispatch — staging lives under its `tmp/` precisely so `os.replace` onto an in-project `--out`
    stays same-filesystem. `no_verify` skips the verify gate entirely (write the .dx regardless —
    debugging / known-buggy verify). `keep_build` cp's the built map out to
    `<state_dir>/tmp/materialize-rejected.dx` on a verify FAILURE so the operator can inspect what
    was actually built (the black-box-materialize fix)."""
    from . import xfer
    work_out = xfer.work_path("dx")
    try:
        ed.map_save(work_out)
        if not no_verify:
            vr = verify_dx_matches(container=ed.container, dx_path=work_out, expected=expected,
                                   defaults=defaults, qualify_driver=ed)
            if not vr.ok:
                msg = vr.message
                if keep_build:                       # preserve the rejected build for inspection
                    tmp = Path(state_dir) / "tmp"
                    tmp.mkdir(parents=True, exist_ok=True)
                    kept = tmp / "materialize-rejected.dx"
                    xfer.cp_out(ed.container, work_out, str(kept))
                    msg += f"\n(--keep-build: built map kept at {kept} for inspection)"
                raise RuntimeError(msg)
        tmp_dir = Path(state_dir) / "tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        staging = tmp_dir / f"{uuid.uuid4().hex}.dx"
        # A relative --out resolves against the CWD (standard CLI semantics — decisions.md
        # 2026-07-17 20:58; the repo-root join + legacy `/repo/` remap died with repo_paths).
        target_host = os.path.abspath(dx_path)
        xfer.cp_out(ed.container, work_out, str(staging))
        # _install_atomic is the SOLE owner of staging cleanup (unlinks on every exit path).
        _install_atomic(staging_host=str(staging), target_host=target_host)
    finally:
        # Always reclaim the editor's /work temp — including when map_save/verify raise (the editor
        # is crash-prone), not just on the !vr.ok and success paths.
        xfer.remove(ed.container, work_out)


_MAP_EXTS = (".dx", ".unr")


def run_materialize(*, level, packages, out_path, overwrite, state_dir, schema_resolver,
                    search_dirs=None, no_verify=False, keep_build=False) -> ApplyResult:
    """Materialize a TRUNK Level into `out_path` (.dx/.unr) via a PER-COMMAND EPHEMERAL editor, H3-
    post-verify it offline in that same container, and swap it in. PURE BUILD (git-native slice 3):
    no session, no 3-way merge, no backup, no git wrapping. Refuses to overwrite unless `overwrite`.
    `packages` is the whole composed-search-path load set (decision 2026-07-05 23:00), resolved and
    remapped by `ensure_load` to the container-visible substrate subset. `search_dirs` is the whole
    composed config dir set (`dispatch._composed_dirs`); the `mounts` (`/resources/<n>` bind mounts)
    and the HOST resolution list are computed ONCE here from it and threaded to `ensure_editor` +
    `ensure_load` — the single mount list drives the ini `Paths`, the docker `-v` args, and the
    host→container remap (decisions.md 2026-07-14 — one uniform dir set; `/stubs` first on Paths so a
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
    # set — decisions.md 2026-07-14). `/stubs` stays first on Paths, so a v69 stub shadows any
    # same-named v68 `.u` a code dir puts on the editor's Paths.
    from .container_assets import resource_mounts
    from .packages import editor_search_dirs
    search_dirs = search_dirs or []
    mounts = resource_mounts(search_dirs)
    host_search_dirs = editor_search_dirs(search_dirs)
    ed_id = uuid7()                                    # bare uuid → editor_container keeps all groups
    try:
        ed = Driver(container=ensure_editor(ed_id, mounts=mounts, state_dir=state_dir))
        # OBJ LOAD only the packages the level REFERENCES (not the whole composed `packages` set —
        # `_level_referenced_packages`, decision 2026-07-14): the whole set still lands in `Paths`
        # via `mounts`, so indirect demand-loads resolve, but the explicit preload shrinks from
        # ~240 to what the level uses — O(level), and far fewer chances for the editor to wedge.
        _materialize(ed, result=result, materialized_order=mo,
                     packages=_level_referenced_packages(level),
                     search_dirs=host_search_dirs, mounts=mounts)
        ed.light_apply()                               # _materialize's MAP REBUILD wiped lighting
        host_out.parent.mkdir(parents=True, exist_ok=True)
        _save_and_swap_verified(ed, out_path, _expected_level(result, mo), defaults=defaults,
                                state_dir=state_dir, no_verify=no_verify, keep_build=keep_build)
    except (DriverError, RuntimeError, TimeoutError, ValueError, OSError,
            subprocess.CalledProcessError) as e:
        # OSError covers the crafted-ini write in ensure_editor (`_write_engine_ini`) and any
        # host-fs failure (unwritable .uedcli/tmp, missing base ini) — never a bare traceback.
        # ValueError covers `uprops.SchemaError` (a ValueError subclass): the post-verify resolves
        # class defaults for the RE-EXPORTED map too, whose classes are requalified against the
        # live editor and can still come back bare (0 or 2+ candidates) — a clean exit 2, not a
        # traceback, and nothing is written because the swap happens after the verify.
        return ApplyResult(rc=2, message=f"materialize failed (nothing written): {e}")
    finally:
        stop_editor(ed_id, state_dir)                  # always tear the ephemeral container down
    return ApplyResult(rc=0, message=f"materialized {out_path}")

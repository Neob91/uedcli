"""Editor-driving glue for the parity report: derive a T3D trunk from an OG `.dx` (offline UCC
batchexport, no live editor) and self-build the lit UED22 golden (`MAP NEW` -> `EDIT PASTE` ->
`MAP REBUILD` -> `LIGHT APPLY` -> `MAP SAVE`).

Reuses the existing, already-proven harness scripts AS SUBPROCESSES rather than re-implementing
their editor-driving logic:
  - extraction: `dev/docs/spikes/2026-07-15-native-materialize/harness/ingest_dx_trunk.py`
  - golden build: `dev/docs/spikes/2026-08-27-native-light-apply-parity/harness/build_ued_lit_golden.py`

NEVER `MAP LOAD`s the original `.dx` -- both reused scripts build via `MAP NEW`+`EDIT PASTE`, per the
owner ruling recorded in `dev/docs/native-materialize-findings.md` ("Golden .dx provenance -- CONFIRMED,
closed"): a `MAP LOAD` of a shipped file carves a DIFFERENT world BSP from the same brushes and is not
a valid comparison target.

Not unit tested (needs docker + the Wine editor container) -- exercised end to end via
`parity_report.py` against UNATCO/Wanchai. The pure cache-state/geometry-math logic this glue feeds
lives in `parity_lib.py` and IS unit tested.
"""
from __future__ import annotations

import datetime
import os
import shutil
import subprocess
import sys
from pathlib import Path

import parity_lib as pl

ROOT = Path(__file__).resolve().parents[5]
INGEST_SCRIPT = ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness/ingest_dx_trunk.py"
GOLDEN_SCRIPT = (ROOT / "dev/docs/spikes/2026-08-27-native-light-apply-parity/harness"
                 / "build_ued_lit_golden.py")


# Written into `trunk_dir` only after extraction AND class-qualification both fully succeed --
# the sole completion signal `ensure_golden` trusts. A bare `actors/`-exists check would also match
# a CRASHED, partial extraction (per-actor writes are individually atomic, but the whole set is
# not), silently reusing a truncated trunk on the next run.
_TRUNK_COMPLETE_MARKER = ".extraction-complete"


class PipelineError(Exception):
    """A clean, named failure extracting a trunk or self-building a golden -- carries the stage and
    the subprocess's own log tail so it can be diagnosed without re-running. Never a raw
    subprocess/timeout exception or traceback reaches the CLI."""


def _tail(path: Path, n: int) -> str:
    try:
        lines = path.read_text(errors="replace").splitlines()
    except OSError:
        return ""
    return "\n".join(lines[-n:])


def _run(cmd: list[str], *, log_path: Path, timeout: float, stage: str,
        env: dict[str, str] | None = None) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w") as log:
        log.write(f"$ {' '.join(cmd)}\n\n")
        log.flush()
        try:
            proc = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, timeout=timeout, env=env)
        except subprocess.TimeoutExpired as e:
            raise PipelineError(f"{stage} timed out after {timeout:.0f}s -- see {log_path}\n"
                                 f"{_tail(log_path, 40)}") from e
    if proc.returncode != 0:
        raise PipelineError(f"{stage} failed (exit {proc.returncode}) -- see {log_path}\n"
                             f"{_tail(log_path, 40)}")


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def level_name(dx_path: Path) -> str:
    """A filesystem/project-safe level key derived from the input `.dx`'s own filename -- no
    per-level registry: any OG `.dx` gets a key this way, and whether the pipeline actually SUCCEEDS
    for it is a runtime fact (a clean `PipelineError`), not something precomputed by a lookup table."""
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in Path(dx_path).stem)
    return safe.lower()


def build_root(hash_hex: str) -> Path:
    """Where the extracted T3D trunk (and its own `.uedcli/` build scratch) lives for one cache
    entry -- under the REPO TREE (`_scratch/`), never under `/tmp`. `dev/docs/parallel-editors.md`
    ("Isolation requirements") documents why: `ephemeral_build_container` bind-mounts a crafted ini
    under the trunk's own `.uedcli/tmp/`, and a sandboxed shell's `/tmp` is private to the sandbox --
    the docker daemon resolves that host path against ITS OWN `/tmp`, finds nothing, and the
    file-onto-file mount fails ("not a directory"). Only the FINAL golden `.dx` + `meta.json` (never
    bind-mounted, only `docker cp`) are cached under `/tmp/uedcli-parity-cache/` per spec -- this is
    a build-time working dir, not part of that cache contract."""
    return ROOT / "_scratch" / "uedcli-parity-cache" / hash_hex / "trunk"


def _substrate_search_dirs(game: str) -> list[str]:
    sys.path.insert(0, str(ROOT))
    from uedcli import config
    user_config = config.load_user_config()
    project = config.Project(root=str(ROOT), game=game)
    return config.composed_search_dirs(project, user_config)


def _ensure_scratch_project(project_root: Path, game: str) -> None:
    """Write a minimal `uedcli.toml` at `project_root` if none exists yet -- same recipe as
    `build_ued_golden.py`'s own `_scratch_project` (declares only `game`; `composed_search_dirs`
    then resolves the real substrate paths from the per-user `~/.uedcli/config.toml`, so this file
    carries no host-specific paths of its own). `class_index()` (needed by `ingest_dx_trunk.py` for
    mover detection) requires a resolvable project via `UEDCLI_PROJECT`; this is the one, self-
    contained under the build root -- no dependency on any other project directory existing."""
    project_root.mkdir(parents=True, exist_ok=True)
    toml = project_root / "uedcli.toml"
    if not toml.exists():
        toml.write_text(f'game = "{game}"\nmaps = "maps"\n')


def extract_trunk(dx_path: Path, trunk_dir: Path, *, game: str, log_path: Path,
                  timeout: float) -> None:
    """Offline T3D trunk extraction via `ingest_dx_trunk.py` (UCC batchexport, no live editor) --
    the SAME mechanism that produced `dev/games/trunks/tmp-wanchai-market` and the UNATCO trunks
    cited throughout `dev/docs/native-materialize-findings.md`."""
    search_dirs = _substrate_search_dirs(game)
    if not search_dirs:
        raise PipelineError(
            f"no search dirs resolved for game {game!r} from ~/.uedcli/config.toml -- "
            f"set up the substrate (dev/docs/deusex-assets-setup.md) before running this level")
    if trunk_dir.exists():
        shutil.rmtree(trunk_dir)
    trunk_dir.parent.mkdir(parents=True, exist_ok=True)
    project_root = trunk_dir.parent.parent
    _ensure_scratch_project(project_root, game)
    cmd = [sys.executable, str(INGEST_SCRIPT), str(dx_path), str(trunk_dir)]
    for d in search_dirs:
        cmd += ["--search", d]
    env = {**os.environ, "UEDCLI_PROJECT": str(project_root)}
    _run(cmd, log_path=log_path, timeout=timeout, stage="trunk extraction", env=env)
    if not (trunk_dir / "actors").is_dir():
        raise PipelineError(
            f"trunk extraction for {dx_path} reported success but left no actors/ at {trunk_dir} "
            f"-- see {log_path}")
    _qualify_trunk_classes(trunk_dir, project_root, game)
    (trunk_dir / _TRUNK_COMPLETE_MARKER).touch()


def trunk_is_complete(trunk_dir: Path) -> bool:
    return (trunk_dir / _TRUNK_COMPLETE_MARKER).exists()


def _qualify_trunk_classes(trunk_dir: Path, project_root: Path, game: str) -> None:
    """Qualify every actor's class name to its FQCN in place. `ingest_dx_trunk.py`'s own extraction
    is explicitly "NOT a materialize-grade ingest" (its docstring) -- UCC batchexport can leave some
    actors (e.g. `LevelInfo`) BARE, and `gather_lights`/`ClassDefaults` (needed for the golden's
    LIGHT APPLY and for native's own lighting build) require every actor's class fully qualified.
    Reuses the SAME production mechanism the real ingest gate uses (`uedcli/cli/ingest.py`'s
    `validate_ingest_actors`, backed by `classindex.ClassIndex.qualify_and_validate`) rather than a
    new qualification scheme -- just the class half, not that gate's texture-existence check (this
    trunk's textures are already qualified by `ingest_dx_trunk.py`'s own import-table pass, and
    texture *existence* on this host's package path isn't this tool's concern)."""
    sys.path.insert(0, str(ROOT))
    from uedcli import config
    from uedcli import trunk as trunk_mod
    from uedcli.classindex import ClassIndex, ClassRefError

    project = config.load_project(str(project_root))
    user_config = config.load_user_config()
    class_index = ClassIndex.from_project(project, user_config)

    level, ranks = trunk_mod.read_level(trunk_dir)
    try:
        class_index.qualify_and_validate(list(level.actors.values()))
    except ClassRefError as e:
        raise PipelineError(f"class qualification failed for trunk at {trunk_dir}: {e}") from e
    trunk_mod.write_level(trunk_dir, level, ranks)


def build_golden(trunk_dir: Path, golden_path: Path, *, game: str, log_path: Path,
                 timeout: float) -> None:
    """Self-build the lit UED22 golden via `build_ued_lit_golden.py` -- `MAP NEW` -> `EDIT PASTE` ->
    `MAP REBUILD` -> `LIGHT APPLY` -> `MAP SAVE`, never `MAP LOAD` on the original."""
    if golden_path.exists():
        golden_path.unlink()
    cmd = [sys.executable, str(GOLDEN_SCRIPT), "--trunk", str(trunk_dir), "--out", str(golden_path),
           "--game", game, "--overwrite"]
    _run(cmd, log_path=log_path, timeout=timeout, stage="golden self-build (MAP REBUILD + LIGHT APPLY)")
    if not golden_path.exists():
        raise PipelineError(
            f"golden self-build reported success but {golden_path} is missing -- see {log_path}")


def ensure_golden(dx_path: Path, *, cache_root: Path, game: str = "deusex",
                  rebuild_timeout: float = 3600.0) -> tuple[pl.CacheLayout, str, Path, bool]:
    """Ensure a self-built lit golden exists in the cache for `dx_path`, building it (extract +
    self-build) if the cache is cold. Returns `(layout, level_name, trunk_dir, cache_hit)`. The
    cache key is the INPUT `.dx`'s own content hash (`parity_lib.content_hash`) -- the shipped
    file's bytes never change, so a repeat run against the same file always hits.

    On a cache HIT the trunk is re-extracted anyway if missing (e.g. a wiped `_scratch/`) -- the
    golden is the expensive, cached half; the trunk is comparatively cheap and is read fresh on
    EVERY run regardless of hit/miss (the native side always builds from it live)."""
    h = pl.content_hash(dx_path)
    layout = pl.cache_layout(cache_root, h)
    name = level_name(dx_path)
    trunk_dir = build_root(h) / "maps" / name

    cache_hit = pl.is_cache_complete(layout)
    trunk_exists = trunk_is_complete(trunk_dir)
    if cache_hit and trunk_exists:
        return layout, name, trunk_dir, True

    if not trunk_exists:
        # A genuine cold start writes "extracting"; a cache HIT missing only its (comparatively
        # cheap, `_scratch`-scratch) trunk -- e.g. a wiped `_scratch/` -- repairs it WITHOUT
        # touching `meta.json`, so a completed golden never regresses to "extracting"/"building"
        # for a rebuild it doesn't need.
        if not cache_hit:
            pl.write_meta(layout, {"status": "extracting", "source_dx": str(dx_path),
                                   "content_hash": h, "level_name": name, "started_at": _now()})
        extract_trunk(dx_path, trunk_dir, game=game, log_path=layout.root / "extract.log",
                     timeout=1800.0)

    if cache_hit:
        return layout, name, trunk_dir, True

    pl.write_meta(layout, {"status": "building", "source_dx": str(dx_path), "content_hash": h,
                           "level_name": name, "started_at": _now()})
    build_golden(trunk_dir, layout.golden, game=game, log_path=layout.build_log,
                timeout=rebuild_timeout)

    pl.write_meta(layout, {"status": "complete", "source_dx": str(dx_path), "content_hash": h,
                           "level_name": name, "built_at": _now()})
    return layout, name, trunk_dir, False

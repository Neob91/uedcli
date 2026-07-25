"""Package-stubbing pipeline orchestrator: decompile a v68 Deus Ex `.u` code package + extract its
meshes, munge the source into a body-free v69 "stub", recompile, rename, and cache.

The whole round-trip was live-validated end-to-end against the real `DeusExItems` on 2026-06-22
(all five spec gates G-A/B/C/D/uc resolved). `assemble_stub_source` is the pure munge+assemble
heart (offline); `build_stub` wraps it with the container UCC/umodel legs. See
`dev/docs/specs/2026-06-21-uedctl-package-stubbing-design.md`.
"""

from __future__ import annotations

import functools
import shutil
import subprocess
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from .uscript_rewrite import (
    CrossPackageRef,
    flag_cross_package_refs,
    parse_class,
    parse_meshmap_scales,
    read_uc,
    reconcile_meshmap_scale,
    rehome_self_refs,
    rename_group_prefixed_pcx,
    render_stub,
    rewrite_imports,
)


class StubBuildError(RuntimeError):
    """A stub could not be built (decompile/umodel/make failure, or a malformed substrate). A
    `RuntimeError` so it rides every `.dx`-resolution site's existing `RuntimeError` guard to a
    clean exit rather than a bare traceback (uedctl house rule)."""


def inject_edit_package(ini_text: str, package: str) -> str:
    """Insert `EditPackages=<package>` right AFTER the last existing `EditPackages=` line — i.e.
    WITHIN the `[Editor.EditorEngine]` section. Appending at EOF lands outside the section and
    `UCC make` silently skips the entry (learned live 2026-06-22). Idempotent."""
    target = f"EditPackages={package}"
    lines = ini_text.splitlines()
    edit_lines = [i for i, line in enumerate(lines) if line.strip().startswith("EditPackages=")]
    if not edit_lines:
        raise StubBuildError("no `EditPackages=` section found in the editor ini")
    if any(lines[i].strip() == target for i in edit_lines):
        return ini_text
    lines.insert(edit_lines[-1] + 1, target)
    return "\n".join(lines) + ("\n" if ini_text.endswith("\n") else "")


def inject_stub_cache_path(ini_text: str) -> str:
    """Add `/stubs` (the mounted v69 stub cache) to `[Core.System] Paths` so a cache-stub dep
    resolves during `make` alongside the substrate-v69 ones. Inserts after the last `Paths=` line;
    idempotent; a no-op if the ini has no `Paths=` section."""
    target = "Paths=/stubs/*.u"
    lines = ini_text.splitlines()
    path_lines = [i for i, line in enumerate(lines) if line.strip().startswith("Paths=")]
    if not path_lines or any(lines[i].strip() == target for i in path_lines):
        return ini_text
    lines.insert(path_lines[-1] + 1, target)
    return "\n".join(lines) + ("\n" if ini_text.endswith("\n") else "")


@dataclass(frozen=True, kw_only=True)
class AssembledStub:
    source_dir: Path                              # <TEMP>/ holding Classes/Models/Textures
    cross_package_refs: tuple[CrossPackageRef, ...]  # flagged (deferred), build proceeds


def assemble_stub_source(
    *, classes_dir: Path | str, umodel_dir: Path | str, textures_dir: Path | str,
    out_dir: Path | str, package: str,
) -> AssembledStub:
    """Munge the raw decompile + umodel output into a buildable `<out_dir>/{Classes,Models,Textures}`
    temp package. Pure host-side (Phase 1 munger); the caller does the container UCC/umodel I/O.

    - Classes: each `.uc` parsed → `#exec` import paths rewritten → `MESHMAP SCALE` reconciled
      against umodel's per-mesh `.uc` → self-refs re-homed to the temp package name → body-free
      stub rendered.
    - Models: umodel's `<Mesh>_a.3d`/`_d.3d` pairs moved in (the `#exec MESH IMPORT` now points
      at `Models\\<Mesh>_…`).
    - Textures: the decompiled group-prefixed PCX renamed to bare names.
    Cross-package asset refs are flagged (deferred), never fatal.
    """
    out = Path(out_dir)
    for sub in ("Classes", "Models", "Textures"):
        (out / sub).mkdir(parents=True, exist_ok=True)

    scales: dict = {}
    for uc in sorted(Path(umodel_dir).rglob("*.uc")):
        scales.update(parse_meshmap_scales(read_uc(uc)))

    flags: list[CrossPackageRef] = []
    for uc in sorted(Path(classes_dir).glob("*.uc")):
        cls = parse_class(read_uc(uc))
        flags.extend(flag_cross_package_refs(cls, package=package))
        cls = reconcile_meshmap_scale(rewrite_imports(cls), scales)
        cls = rehome_self_refs(cls, package=package, temp=out.name)
        (out / "Classes" / uc.name).write_text(render_stub(cls), encoding="utf-8")

    for mesh_3d in Path(umodel_dir).rglob("*.3d"):
        shutil.copy(mesh_3d, out / "Models" / mesh_3d.name)
    for pcx in Path(textures_dir).glob("*.pcx"):
        shutil.copy(pcx, out / "Textures" / pcx.name)
    rename_group_prefixed_pcx(out / "Textures")

    return AssembledStub(source_dir=out, cross_package_refs=tuple(flags))


# --- container orchestration (integration-only; mocked/skipped in the offline suite) ----------

_EDITOR_INI = "/opt/UED22/unrealtournament.ini"
_UCC = "/opt/UED22/UCC.exe"


def _exec(container: str, *args: str, input_text: str | None = None) -> str:
    cmd = ["docker", "exec", *(["-i"] if input_text is not None else []), container, *args]
    r = subprocess.run(cmd, input=input_text, capture_output=True, text=True)
    if r.returncode != 0:
        raise StubBuildError(f"`{' '.join(args)}` failed in {container}: {r.stderr.strip() or r.stdout.strip()}")
    return r.stdout


def build_stub(
    *, container: str, name: str, source_u_dir: str,
    out_u_path: Path | str, temp_name: str = "DXIStub", code_deps: tuple[str, ...] = (),
) -> Path:
    """Decompile + umodel + munge + `make` the v68 `<name>` into a v69 `.u` at `out_u_path`, using
    a throwaway `<temp_name>` package. `code_deps` are the target's DIRECT v69 code deps that must
    be on `EditPackages` BEFORE `<temp_name>` so its classes' superclasses resolve (e.g.
    `DeusExDeco` needs `DeusExItems`; only deps already baked into the committed ini can be omitted).
    Drives the build `container` (ephemeral, `LAUNCH_UED=0`, `/umodel` mounted). Integration-only.

    `source_u_dir` is the CONTAINER path of the mount holding `<name>.u` — a `/resources/<n>`
    read-only bind mount (config-driven, decisions.md 2026-07-14): the SAME uniform `resource_mounts`
    scheme the editor uses, over the full composed set (content + code) for this build container. The
    v68 `.u` SOURCE is read from it by explicit path (`batchexport`/`umodel -path`), NOT resolved via
    `[Core.System] Paths`. The caller remaps `<name>`'s host code dir to this container path
    (`container_assets.remap`) so it always matches an actual mount."""
    from .driver import to_z_path

    def _cp(*cp_args: str) -> None:
        r = subprocess.run(["docker", "cp", *cp_args], capture_output=True, text=True)
        if r.returncode != 0:
            raise StubBuildError(f"docker cp {' '.join(cp_args)} failed: {r.stderr.strip()}")

    work = f"/work/stub-{temp_name}"
    raw = f"{work}/raw"
    built = f"/opt/UED22/{temp_name}.u"
    try:
        _exec(container, "sh", "-c", f"rm -rf {work} /opt/{temp_name}; mkdir -p {raw}/Classes {raw}/Textures")

        src_u = f"{source_u_dir}/{name}.u"
        _exec(container, "wine", _UCC, "batchexport", src_u, "class", "uc", to_z_path(f"{raw}/Classes"))
        _exec(container, "wine", _UCC, "batchexport", src_u, "texture", "pcx", to_z_path(f"{raw}/Textures"))
        # umodel resolves -path relative to its cwd under wine; pass the explicit Z: form.
        install_z = to_z_path(source_u_dir)
        _exec(container, "sh", "-c",
              f"cd /umodel && wine umodel.exe -path=\"{install_z}\" -export -uc -out=\"{to_z_path(raw + '/um')}\" {name}")

        with tempfile.TemporaryDirectory() as host_tmp:
            host_raw = Path(host_tmp) / "raw"
            _cp(f"{container}:{raw}", str(host_raw))
            staged = Path(host_tmp) / temp_name
            assemble_stub_source(
                classes_dir=host_raw / "Classes", umodel_dir=host_raw / "um",
                textures_dir=host_raw / "Textures", out_dir=staged, package=name,
            )
            _cp(str(staged), f"{container}:/opt/{temp_name}")

        # The target's direct code deps go on EditPackages BEFORE <temp_name> (which must be last);
        # `/stubs` on Paths so a cache-stub dep resolves alongside the substrate-v69 ones.
        ini = _exec(container, "cat", _EDITOR_INI)
        for dep in code_deps:
            ini = inject_edit_package(ini, dep)
        ini = inject_edit_package(ini, temp_name)
        ini = inject_stub_cache_path(ini)
        _exec(container, "sh", "-c", f"cat > {_EDITOR_INI}", input_text=ini)

        make_out = _exec(container, "sh", "-c", f"cd /opt/UED22 && wine {_UCC} make")
        if "Success" not in make_out:
            raise StubBuildError(f"`make` did not succeed for {name} (temp {temp_name}): {make_out[-500:]}")
        if _exec(container, "sh", "-c", f"test -f {built} && echo ok || echo no").strip() != "ok":
            raise StubBuildError(f"`make` reported Success but produced no {temp_name}.u for {name}")

        out_path = Path(out_u_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        _cp(f"{container}:{built}", str(out_path))
        return out_path
    finally:
        # Always clean container-side residue (only matters for a reused container; an ephemeral
        # one dies anyway). Best-effort — never mask the real failure.
        subprocess.run(["docker", "exec", container, "sh", "-c",
                        f"rm -rf {work} /opt/{temp_name} {built}"], capture_output=True)


# --- cache key + ensure (cache-or-build) ------------------------------------------------------

# Bump when the munger/pipeline output shape changes, to invalidate every cached stub.
_PIPELINE_FORMAT = "1"


def _combined_sha(paths: list[Path]) -> str:
    import hashlib
    h = hashlib.sha256()
    for p in sorted(paths):
        h.update(p.name.encode())
        h.update(p.read_bytes())
    return h.hexdigest()


@functools.lru_cache(maxsize=None)
def _substrate_id() -> str:
    """sha over the committed UED22 `.u` link set CONTENT — a re-strip that changes an exported
    symbol set (the thing that makes a body fail to link) must invalidate, which a version label
    wouldn't catch. Memoized per process — it hashes ~80 MB of fixed committed inputs, and
    `cached_stub` recomputes the key (even on a hit) to compare. UED22 is PACKAGE-RELATIVE
    (`tool_assets.uned_dir()` — decisions.md 2026-07-17 20:58 §6)."""
    from . import tool_assets
    return _combined_sha(list((tool_assets.uned_dir() / "UED22").glob("*.u")))


@functools.lru_cache(maxsize=None)
def _toolchain_id() -> str:
    import hashlib
    from . import tool_assets
    umodel = tool_assets.umodel_dir() / "umodel.exe"
    ucc = tool_assets.uned_dir() / "UED22" / "UCC.exe"
    h = hashlib.sha256(_PIPELINE_FORMAT.encode())
    for binary in (umodel, ucc):
        if binary.exists():
            h.update(binary.read_bytes())
    return h.hexdigest()


def _v69_code_dirs() -> list[str]:
    """The v69 CODE dirs a stub's DIRECT deps resolve against (for the closure classifier): the
    committed UED22 substrate (package-relative) + the per-user built-stub cache. NOT the game's
    own v68 `.u` (those are the stub SOURCE, classified must-stub) and NOT the config content dirs
    (no `.u` to match)."""
    from . import config, tool_assets
    return [str(tool_assets.uned_dir() / "UED22"), str(config.stub_cache_root())]


def _resolve_v68(name: str, search_dirs: list[str]) -> Path:
    """The host path of the v68 `<name>.u` on the composed search path (project overlay before game
    base), or a clean StubBuildError if absent — the stub SOURCE. First-dir-wins mirrors config
    shadowing. (`.u` is the code package; a same-named `.utx` etc. is a different, non-code file.)"""
    from .stub_closure import _find_code
    hit = _find_code(name, search_dirs)
    if hit is None:
        raise StubBuildError(f"no v68 code package {name!r} on the composed search path {search_dirs} "
                             f"— nothing to stub")
    return Path(hit)


def _dep_shas(name: str, *, search_dirs: list[str]) -> dict[str, str]:
    from .stub_closure import resolve, _find_code
    from .stub_cache import sha256_file
    from . import config

    v69_dirs = _v69_code_dirs()
    result = resolve(
        str(_resolve_v68(name, search_dirs)),
        substrate_dirs=v69_dirs,
        cache_dir=str(config.stub_cache_root()),
        search_dirs=search_dirs,
    )
    shas: dict[str, str] = {}
    for dep in result.ready_code:
        # Resolve through the SAME v69 dirs the classifier used (UED22 substrate, then cache) so any
        # ready dep's identity is keyed.
        located = _find_code(dep, v69_dirs)
        if located is not None:
            shas[dep] = sha256_file(located)
    for dep in result.must_stub_code:
        # A must-stub dep bottoms out on substrate (the M1 boundary REFUSES a must-stub-of-a-
        # must-stub), so its v68 source sha is a stable identity; the shared substrate/toolchain
        # axes are covered by THIS key's own substrate_id/toolchain_id. (Revisit if M1 is relaxed.)
        shas[dep] = sha256_file(_resolve_v68(dep, search_dirs))
    return shas


def _code_deps(name: str, *, search_dirs: list[str]) -> tuple[str, ...]:
    """The target's DIRECT code dep names (ready-v69 + must-stub) for the `make` `EditPackages`."""
    from .stub_closure import resolve
    from . import config

    result = resolve(
        str(_resolve_v68(name, search_dirs)),
        substrate_dirs=_v69_code_dirs(),
        cache_dir=str(config.stub_cache_root()),
        search_dirs=search_dirs,
    )
    return result.ready_code + result.must_stub_code


def compute_cache_key(name: str, *, search_dirs: list[str]):
    from .stub_cache import CacheKey, sha256_file
    return CacheKey(
        source_sha=sha256_file(_resolve_v68(name, search_dirs)),
        dep_shas=_dep_shas(name, search_dirs=search_dirs),
        substrate_id=_substrate_id(),
        toolchain_id=_toolchain_id(),
    )


def _is_stub_candidate(name: str, search_dirs: list[str]) -> bool:
    """A missing package is a stub candidate iff a v68 `<name>.u` (code) exists on the composed search
    path. A package present only as a non-code file (`.utx/.uax/.umx`) is a genuine absent asset when
    missing, not stubbable."""
    from .stub_closure import _find_code
    return _find_code(name, search_dirs) is not None


def stub_missing_packages(missing: list[str], *, search_dirs: list[str], state_dir) -> set[str]:
    """The lazy auto-trigger core: for each `missing` package that is a v68 `.u` (code) on the
    composed search path, build (or reuse) its v69 stub — in ONE shared ephemeral build container —
    and return the set newly resolved. A miss with no `.u` is left alone (a genuine absent asset). The
    caller recomputes its closure afterward (the stub cache is a permanent v69 search-dir member).

    `search_dirs` is the whole composed config dir set
    (`config.composed_search_dirs(project, user_config)`, decisions.md 2026-07-14 — one uniform dir
    set). Used by every `.dx`-resolution site (`qualify.export_and_qualify`, and the
    package-resolution pre-passes before an editor spin-up). `state_dir` is the project's
    `.uedctl/` state dir, threaded to the build container's crafted-ini temp."""
    from . import container_assets

    candidates = [m for m in missing if _is_stub_candidate(m, search_dirs)]
    if not candidates:
        return set()
    # ONE uniform mount set over the whole composed dir set: batchexport reads the v68 `.u` SOURCE
    # from its `/resources/<n>` path; `/stubs` (v69) stays first on Paths so it shadows any v68 `.u`.
    mounts = container_assets.resource_mounts(search_dirs)
    resolved: set[str] = set()
    with ephemeral_build_container(state_dir=state_dir, mounts=mounts) as container:
        for name in candidates:
            ensure_stub(name, container=container, search_dirs=search_dirs, mounts=mounts)
            resolved.add(name)
    return resolved


@contextmanager
def ephemeral_build_container(*, state_dir, mounts=None, ready_timeout: float = 60.0):
    """Spin a fresh NO-GUI build container (`LAUNCH_UED=0`, own WINEPREFIX, `/umodel` mounted), wait
    for wine, yield its name, tear it down. NOT the standing `dx-lum-uned`; readiness is an offline
    `wine --version` probe, not a GUI-window poll. Validated live 2026-06-22.

    This container wires its own asset mounts + `[Core.System] Paths` exactly like the GUI editor
    (`editor.ensure_editor`), via the ONE uniform `container_assets.resource_mounts` scheme
    (decisions.md 2026-07-14 — config-drive stub source, single mount way):
      - `mounts` (`container_assets.Mount` list) are the caller's `/resources/<n>` read-only bind
        mounts over the FULL composed dir set — CONTENT dirs (whose packages `make`/`texture sync`
        resolve via Paths) AND v68 CODE dirs (whose `.u` `build_stub`'s `batchexport`/umodel read by
        EXPLICIT `/resources/<n>` path). `None`/`[]` → no `/resources` mounts (a pure spin-up).
      - a crafted `unrealtournament.ini` (its `[Core.System] Paths` regenerated over
        `/stubs`+`/opt/UED22`+the mounts by `container_assets.paths_ini_lines`) is bind-mounted
        PRE-LAUNCH over the baked one, read-write (`UCC make` rewrites it via `cat >`). `/stubs` is
        FIRST, so a v68 code mount's `*.u` on Paths can never shadow the same-named v69 stub.
    The static compose `/deusex`+`/content` mounts and the entrypoint Paths `sed` block are gone; the
    caller (`stub_missing_packages`, `dispatch` substrate/texture verbs) computes `mounts` once from
    the composed config and threads the SAME list here and to `ensure_stub` (never recomputed).
    `state_dir` (required) is the resolved project's `.uedctl/` state dir (`config.state_dir`) —
    hosts the crafted-ini temp, cleaned up on teardown (decisions.md 2026-07-17 20:58)."""
    import os
    from . import config, container_assets, tool_assets
    from .editor import _compose_dir, engine_ini_mount, _engine_ini_path

    uid = uuid4().hex[:8]
    name, volume = f"uned-stub-{uid}", f"uned-wp-stub-{uid}"
    umodel = tool_assets.umodel_dir()
    mounts = mounts or []
    _ini_path, ini_mount = engine_ini_mount(name, mounts, state_dir)
    try:
        # Same compose file/volume as the editor: UEDCTL_STUB_CACHE feeds the `/stubs` mount
        # source (`${UEDCTL_STUB_CACHE:-…}`), so the BUILD container's stub cache also honors
        # `$UEDCTL_HOME` — /stubs is FIRST on its Paths precisely so previously-built stubs
        # shadow v68 deps during `UCC make`; a diverged mount would silently bind an empty
        # default-path dir (review fix, 2026-07-18 — the editor half landed first, this is the
        # build-container half).
        env = {**os.environ,
               "UEDCTL_STUB_CACHE": str(config.stub_cache_root(create=True))}
        run = subprocess.run(
            ["docker", "compose", "run", "-d", "--name", name, "-e", "LAUNCH_UED=0",
             "-v", f"{umodel}:/umodel:ro", "-v", f"{volume}:/wineprefix",
             *ini_mount, *container_assets.docker_mount_args(mounts), "uned"],
            cwd=_compose_dir(), env=env, capture_output=True, text=True)
        if run.returncode != 0:
            # Docker down / stale image / build needed — the documented container failure modes.
            raise StubBuildError(f"could not start build container: {run.stderr.strip() or run.stdout.strip()}")
        deadline = time.time() + ready_timeout
        while time.time() < deadline:
            if subprocess.run(["docker", "exec", name, "wine", "--version"],
                              capture_output=True).returncode == 0:
                break
            time.sleep(0.5)
        else:
            raise StubBuildError(f"build container {name} wine did not become ready")
        yield name
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)
        subprocess.run(["docker", "volume", "rm", volume], capture_output=True)
        _engine_ini_path(name, state_dir).unlink(missing_ok=True)


def ensure_stub(name: str, *, container: str,
                search_dirs: list[str], mounts, force: bool = False) -> Path:
    """Return the cached v69 `<name>.u` if its key matches, else build it (printing a one-line
    stdout notice) and cache it. `force` rebuilds even on a cache hit. The build container is the
    caller's responsibility.

    `search_dirs` is the whole composed config dir set; `mounts` is the SAME
    `resource_mounts(search_dirs)` list the caller bind-mounted on `container` — the v68 SOURCE dir is
    remapped to its container `/resources/<n>` path through it (never recomputed)."""
    from . import config, container_assets
    from .stub_cache import cached_stub, store_stub

    source_host = _resolve_v68(name, search_dirs)               # clean StubBuildError if absent
    source_u_dir = container_assets.remap(str(source_host.parent), mounts)
    if source_u_dir is None:
        raise StubBuildError(
            f"v68 source dir {source_host.parent} for {name!r} is under no build-container mount "
            f"(mounts must cover the composed search dirs — resource_mounts(search_dirs))")
    key = compute_cache_key(name, search_dirs=search_dirs)
    cache = config.stub_cache_root(create=True)

    if not force:
        hit = cached_stub(cache, name, key)
        if hit is not None:
            return hit

    print(f"stubbing {name}…")
    with tempfile.TemporaryDirectory() as tmp:
        built = build_stub(container=container, name=name, source_u_dir=source_u_dir,
                           out_u_path=Path(tmp) / f"{name}.u",
                           code_deps=_code_deps(name, search_dirs=search_dirs))
        return store_stub(cache, name, built, key)

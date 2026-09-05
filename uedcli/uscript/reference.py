"""Compile and decompile UnrealScript through UED22's `UCC.exe`, in an ephemeral build container.

This is the REFERENCE toolchain — it drives the real editor's compiler, so its output is the ground
truth we compare a native path against. It reuses the container machinery `stub.py` already owns:
`ephemeral_build_container` (a no-GUI wine container with the UED22 substrate on `Paths`), `_exec`
(a bounded-by-nature `docker exec` round-trip), and `inject_edit_package` (the "insert inside
`[Editor.EditorEngine]`" ini edit that `UCC make` needs).

The container puts the UED22 substrate flat at `/opt/UED22` (its `System` dir; game root `/opt`), so
a new package `Foo` compiles from sources at `/opt/Foo/Classes/*.uc` with `EditPackages=Foo` added to
the ini `UCC` reads (`/opt/UED22/unrealtournament.ini`, bind-mounted read-write by
`ephemeral_build_container`). Files go IN via `docker exec -i … cat >`/`tar` (not `docker cp`, which
fails under rootless docker) and come OUT via `cat`/`tar`.
"""
from __future__ import annotations

import io
import subprocess
import tarfile
from contextlib import contextmanager
from uuid import uuid4

from ..container_assets import UED22_CONTAINER_DIR
from ..driver import to_z_path
from ..stub import _exec, ephemeral_build_container, inject_edit_package

__all__ = ["UccError", "ucc_container", "ucc_compile", "ucc_decompile"]

_UCC = "UCC.exe"                                        # run with cwd = UED22_CONTAINER_DIR
_INI = f"{UED22_CONTAINER_DIR}/unrealtournament.ini"    # the ini UCC reads (bind-mounted rw)
_MIN_U_BYTES = 64                                       # a 64-byte `.u` is an empty/failed compile
_WINE_TIMEOUT = 180.0                                   # bound every wine call (background-work.md)
_EXFIL_TIMEOUT = 60.0


class UccError(RuntimeError):
    """A compile/decompile failed or the toolchain hung. `RuntimeError` so it rides the CLI's
    existing top-level `RuntimeError` guard to a clean exit instead of a bare traceback."""


@contextmanager
def ucc_container(*, state_dir, mounts=None):
    """Thin wrapper over `ephemeral_build_container`: spin a no-GUI wine build container (UED22 on
    `Paths`), yield its name, tear it down. `mounts` (default none) bind arbitrary `.u` dirs for
    `ucc_decompile`; a pure compile needs none."""
    with ephemeral_build_container(state_dir=state_dir, mounts=mounts or []) as name:
        yield name


def _wine(container: str, *args: str, timeout: float = _WINE_TIMEOUT) -> subprocess.CompletedProcess:
    """Run `wine <args>` with cwd `/opt/UED22`, bounded. A hang past `timeout` raises `UccError`
    (background-work.md: never wait open-endedly on the crash-prone toolchain) — the caller tears the
    container down. `-w` sets the workdir so `UCC` resolves the substrate `.u` via `Paths`."""
    try:
        return subprocess.run(
            ["docker", "exec", "-w", UED22_CONTAINER_DIR, container, "wine", *args],
            capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise UccError(f"`wine {' '.join(args)}` did not finish within {timeout:.0f}s in "
                       f"{container} (torn down)") from None


def _exfil(container: str, path: str) -> bytes:
    """Read a container file's raw bytes out over `docker exec … cat` (not `docker cp`: it remounts
    binds read-only under rootless docker and fails)."""
    r = subprocess.run(["docker", "exec", container, "cat", path],
                       capture_output=True, timeout=_EXFIL_TIMEOUT)
    if r.returncode != 0:
        raise UccError(f"could not read {path} from {container}: "
                       f"{r.stderr.decode(errors='replace').strip()}")
    return r.stdout


def ucc_compile(container: str, package: str, classes: dict[str, str]) -> bytes:
    """Compile a package `<package>` from `classes` (filename -> UnrealScript source, e.g.
    `{"Foo.uc": "class Foo expands Object;"}`) and return the built `<package>.u` bytes.

    CLEAN rebuild every call (stale `/opt/<package>` and `/opt/UED22/<package>.u` removed first) so
    results are reproducible. Success requires `UCC make` exit 0 AND `Success` in its output AND an
    output `.u` larger than a 64-byte empty stub; otherwise `UccError` names the package and carries
    the UCC output tail.
    """
    pkg_dir = f"/opt/{package}"
    built = f"{UED22_CONTAINER_DIR}/{package}.u"

    _exec(container, "sh", "-c", f"rm -rf {pkg_dir} {built}; mkdir -p {pkg_dir}/Classes")
    for filename, source in classes.items():
        _exec(container, "sh", "-c", f"cat > {pkg_dir}/Classes/{filename}", input_text=source)

    ini = inject_edit_package(_exec(container, "cat", _INI), package)
    _exec(container, "sh", "-c", f"cat > {_INI}", input_text=ini)

    make = _wine(container, _UCC, "make")
    size = int(_exec(container, "sh", "-c",
                     f"test -f {built} && wc -c < {built} || echo -1").strip())
    out = make.stdout + make.stderr
    if make.returncode != 0 or "Success" not in out or size <= _MIN_U_BYTES:
        raise UccError(
            f"UCC make failed for package {package!r} (exit {make.returncode}, {built} = {size} "
            f"bytes): {out[-800:].strip()}")
    return _exfil(container, built)


def _target_arg(u_path_or_name: str) -> str:
    """The `batchexport` package argument. A container path (has a `/`) becomes its `Z:\\` form; a
    bare package name is passed as-is (`UCC` resolves it via `Paths` from cwd `/opt/UED22`), with a
    `.u` appended if absent."""
    if "/" in u_path_or_name:
        return to_z_path(u_path_or_name)
    return u_path_or_name if u_path_or_name.endswith(".u") else f"{u_path_or_name}.u"


def ucc_decompile(container: str, u_path_or_name: str) -> dict[str, str]:
    """Decompile a package's classes to source: run `UCC batchexport <pkg> class uc <outdir>` and
    return `{ClassName.uc: source}`. Works on a stock package already on `Paths` (pass just the name,
    e.g. `"Engine"`) or an arbitrary mounted `.u` (pass its container path)."""
    out_dir = f"/work/ucc-export-{uuid4().hex[:8]}"
    _exec(container, "sh", "-c", f"rm -rf {out_dir}; mkdir -p {out_dir}")
    r = _wine(container, _UCC, "batchexport", _target_arg(u_path_or_name),
              "class", "uc", to_z_path(out_dir))
    sources = _read_uc_dir(container, out_dir)
    if r.returncode != 0 or not sources:
        raise UccError(
            f"UCC batchexport produced no classes for {u_path_or_name!r} (exit {r.returncode}): "
            f"{(r.stdout + r.stderr)[-800:].strip()}")
    return sources


def _read_uc_dir(container: str, out_dir: str) -> dict[str, str]:
    """Tar the export dir out in one round-trip and return its `.uc` files as `{basename: source}`."""
    r = subprocess.run(["docker", "exec", container, "sh", "-c", f"cd {out_dir} && tar cf - ."],
                       capture_output=True, timeout=_EXFIL_TIMEOUT)
    if r.returncode != 0:
        raise UccError(f"could not read export dir {out_dir} from {container}: "
                       f"{r.stderr.decode(errors='replace').strip()}")
    sources: dict[str, str] = {}
    with tarfile.open(fileobj=io.BytesIO(r.stdout)) as tf:
        for member in tf.getmembers():
            if member.isfile() and member.name.lower().endswith(".uc"):
                sources[member.name.rsplit("/", 1)[-1]] = \
                    tf.extractfile(member).read().decode("utf-8", errors="replace")
    return sources

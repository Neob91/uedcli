"""Compile and decompile UnrealScript through UT99's OWN `UCC.exe`, in an ephemeral build container.

The sibling `reference.py` drives the baked `/opt/UED22` substrate. That engine is a DIFFERENT build
(its `Core.u`/native indices ≠ UT99's), so it cannot compile UT99 packages. This module runs UT99's
own toolchain against UT99 packages — fully self-consistent — and is the golden the native compiler
matches for the UT99 corpus.

The UT99 substrate lives on the host at `uned/UT99/System/` (fetched by `fetch_ut99.sh`, gitignored).
`ut99_container` bind-mounts it read-only into the build container, then copies it to a WRITABLE
`/opt/UT99/System` (UCC `make` rewrites the ini and writes the output `.u` there). UCC's convention:
the System dir is the CWD and the game root is its parent, so with CWD `/opt/UT99/System` the game
root is `/opt/UT99`; a package `Foo` compiles from sources at `/opt/UT99/Foo/Classes/*.uc` and lands
at `/opt/UT99/System/Foo.u`. The CD's own `UnrealTournament.ini` (its `[Core.System] Paths` already
`../System/*.u` and a full `[Editor.EditorEngine] EditPackages` list) is used as-is; we only inject
the target's `EditPackages=` line. Files move over `docker exec … cat`/`tar` (not `docker cp`, which
fails under rootless docker).
"""
from __future__ import annotations

import io
import subprocess
import tarfile
from contextlib import contextmanager
from uuid import uuid4

from .. import tool_assets
from ..container_assets import Mount
from ..driver import to_z_path
from ..stub import _exec, ephemeral_build_container
from .reference import UccError

__all__ = ["UccError", "ut99_container", "ut99_substrate_dir",
           "ucc_compile_ut99", "ucc_decompile_ut99"]

_RO_MOUNT = "/opt/UT99-ro"                 # host UT99 System, bind-mounted read-only
_SYS = "/opt/UT99/System"                  # writable copy — CWD for UCC; game root is /opt/UT99
_GAME_ROOT = "/opt/UT99"
_UCC = f"{_SYS}/UCC.exe"
_INI = f"{_SYS}/UnrealTournament.ini"
_MIN_U_BYTES = 64
_WINE_TIMEOUT = 300.0                       # UT99 compiles load a big substrate; bound generously
_EXFIL_TIMEOUT = 60.0


def _edit_packages_upto(ini_text: str, package: str) -> str:
    """Return `ini_text` with the `[Editor.EditorEngine]` EditPackages list trimmed so `<package>` is
    the LAST entry. Deps stay (they precede the target in the CD's build order and load as prebuilt
    `.u`, no `Classes/` → not recompiled); every entry AFTER the target is dropped so `UCC make`'s
    dependent-invalidation cascade can't reach a stock package with no `Classes/` dir and abort. If
    the target isn't in the CD list, it is appended to the content-safe base (up to `Editor`) rather
    than the full list — the tail (Botpack, …) can't even LOAD here without content packages, so
    keeping it would abort the build before reaching the target."""
    def is_ep(ln: str) -> bool:
        return ln.strip().casefold().startswith("editpackages=")

    lines = ini_text.splitlines()
    order = [ln.strip().split("=", 1)[1].strip() for ln in lines if is_ep(ln)]
    if package in order:
        keep = order[:order.index(package) + 1]
    else:
        base = order[:order.index("Editor") + 1] if "Editor" in order else order
        keep = base + [package]
    at = next((i for i, ln in enumerate(lines) if is_ep(ln)), None)          # first EP line's slot
    out = [ln for ln in lines if not is_ep(ln)]
    if at is None:                                                           # no EP lines at all
        at = next(i for i, ln in enumerate(out)
                  if ln.strip().casefold() == "[editor.editorengine]") + 1
    else:
        at -= sum(1 for ln in lines[:at] if is_ep(ln))                      # (none removed before it)
    out[at:at] = [f"EditPackages={p}" for p in keep]
    return "\n".join(out) + ("\n" if ini_text.endswith("\n") else "")


def ut99_substrate_dir():
    """Host path of the UT99 System substrate (`uned/UT99/System`). Raises `UccError` if absent so a
    caller / test skips cleanly instead of spinning a container that would fail."""
    d = tool_assets.uned_dir() / "UT99" / "System"
    if not (d / "UCC.exe").is_file() or not (d / "Core.u").is_file():
        raise UccError(f"UT99 substrate missing at {d} — run uedcli/uscript/fetch_ut99.sh")
    return d


@contextmanager
def ut99_container(*, state_dir):
    """Spin a no-GUI build container with the UT99 substrate mounted read-only, copy it to a writable
    `/opt/UT99/System`, yield the container name, tear it down. The mount also lands in the (unused)
    UED22 crafted ini's Paths — harmless, since every UT99 call runs with CWD `/opt/UT99/System` and
    UT99's own ini."""
    host = str(ut99_substrate_dir())
    mounts = [Mount(host_dir=host, container_dir=_RO_MOUNT)]
    with ephemeral_build_container(state_dir=state_dir, mounts=mounts) as name:
        # UT99's appInit needs a User.ini to exist (else it aborts "MisingIni"); the CD ships one
        # via DefUser.ini we don't fetch, so synthesize it from UnrealTournament.ini.
        _exec(name, "sh", "-c",
              f"mkdir -p {_SYS} && cp -a {_RO_MOUNT}/. {_SYS}/ && "
              f"test -f {_SYS}/User.ini || cp {_INI} {_SYS}/User.ini")
        yield name


def _wine(container: str, *args: str, timeout: float = _WINE_TIMEOUT) -> subprocess.CompletedProcess:
    """Run `wine <args>` with CWD `/opt/UT99/System` (so UT99's UCC resolves its DLLs + Paths),
    bounded. A hang raises `UccError`; the caller tears the container down."""
    try:
        return subprocess.run(
            ["docker", "exec", "-w", _SYS, container, "wine", *args],
            capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise UccError(f"`wine {' '.join(args)}` did not finish within {timeout:.0f}s in "
                       f"{container} (torn down)") from None


def _exfil(container: str, path: str) -> bytes:
    r = subprocess.run(["docker", "exec", container, "cat", path],
                       capture_output=True, timeout=_EXFIL_TIMEOUT)
    if r.returncode != 0:
        raise UccError(f"could not read {path} from {container}: "
                       f"{r.stderr.decode(errors='replace').strip()}")
    return r.stdout


def ucc_compile_ut99(container: str, package: str, classes: dict[str, str]) -> bytes:
    """Compile `<package>` from `classes` ({filename -> source}) with UT99's UCC and return the built
    `<package>.u` bytes. CLEAN rebuild every call. Success requires `make` exit 0 AND `Success` in the
    output AND a `.u` larger than a 64-byte empty stub; otherwise `UccError` names the package and
    carries the UCC output tail."""
    pkg_dir = f"{_GAME_ROOT}/{package}"
    built = f"{_SYS}/{package}.u"

    _exec(container, "sh", "-c", f"rm -rf {pkg_dir} {built}; mkdir -p {pkg_dir}/Classes")
    for filename, source in classes.items():
        _exec(container, "sh", "-c", f"cat > {pkg_dir}/Classes/{filename}", input_text=source)

    ini = _edit_packages_upto(_exec(container, "cat", _INI), package)
    _exec(container, "sh", "-c", f"cat > {_INI}", input_text=ini)

    make = _wine(container, _UCC, "make")
    size = int(_exec(container, "sh", "-c",
                     f"test -f {built} && wc -c < {built} || echo -1").strip())
    out = make.stdout + make.stderr
    if make.returncode != 0 or "Success" not in out or size <= _MIN_U_BYTES:
        raise UccError(
            f"UT99 UCC make failed for package {package!r} (exit {make.returncode}, {built} = {size} "
            f"bytes): {out[-800:].strip()}")
    return _exfil(container, built)


def _target_arg(u_path_or_name: str) -> str:
    if "/" in u_path_or_name:
        return to_z_path(u_path_or_name)
    return u_path_or_name if u_path_or_name.endswith(".u") else f"{u_path_or_name}.u"


def ucc_decompile_ut99(container: str, u_path_or_name: str) -> dict[str, str]:
    """Decompile a package's classes to source with UT99's UCC: `batchexport <pkg> class uc <outdir>`,
    returning `{ClassName.uc: source}`. A stock package resolves by bare name via Paths; an arbitrary
    `.u` is passed by its container path."""
    out_dir = f"/work/ut99-export-{uuid4().hex[:8]}"
    _exec(container, "sh", "-c", f"rm -rf {out_dir}; mkdir -p {out_dir}")
    r = _wine(container, _UCC, "batchexport", _target_arg(u_path_or_name),
              "class", "uc", to_z_path(out_dir))
    sources = _read_uc_dir(container, out_dir)
    if r.returncode != 0 or not sources:
        raise UccError(
            f"UT99 UCC batchexport produced no classes for {u_path_or_name!r} (exit {r.returncode}): "
            f"{(r.stdout + r.stderr)[-800:].strip()}")
    return sources


def _read_uc_dir(container: str, out_dir: str) -> dict[str, str]:
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

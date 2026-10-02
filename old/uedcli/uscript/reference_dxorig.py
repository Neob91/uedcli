"""Compile UnrealScript through the ORIGINAL Ion Storm Deus Ex UCC (v1112fm), in an ephemeral
build container. The reason this module exists separately from `reference_ut99.py`/`reference.py`:
only the original Ion Storm editor toolchain handles `#exec CONVERSATION IMPORT` — OldUnreal's
rebuilt Editor.dll dropped that handler (our /opt/UED22 substrate is OldUnreal-based, so it no-ops),
and UT99's UCC can't even load DX's packages (package-version mismatch).

The DX substrate lives on the host at `uned/DXORIG/System/` (fetched by `fetch_dxorig.sh`,
gitignored): the GOTY game's own DLLs + .u, plus the SDK's DX-native `UCC.exe`. `dxorig_container`
bind-mounts it read-only, copies it to a WRITABLE `/opt/DXORIG/System`, then runs UCC there. UCC's
convention: the System dir is the CWD and the game root its parent, so a package `Foo` compiles from
`/opt/DXORIG/Foo/Classes/*.uc` and lands at `/opt/DXORIG/System/Foo.u`. The game's own `DeusEx.ini`
is used as-is (its `[Core.System] Paths` already resolves `../System/*.u`); we only trim its
`[Editor.EditorEngine] EditPackages` so the target is last. Files move over `docker exec … cat`/`tar`
(not `docker cp`, which fails under rootless docker).

Conversation import: `#exec CONVERSATION IMPORT FILE="X.con"` does NOT populate `<Foo>.u`; it emits
the Conversation/ConEvent/ConSpeech/… objects into sibling packages `<Foo>Text.u` (the objects) and
`<Foo>Audio<pkg>.u` (audio list). `ucc_compile_dxorig` stages the `.con` inputs and returns EVERY
`<Foo>*.u` produced. NOTE: the original build's shutdown GC hits a GPF while tearing down some
conversation object graphs — AFTER the packages are already saved — so the success gate keys on
"Success - 0 error(s)" plus a valid output package, not on the process exit code.
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

__all__ = ["UccError", "dxorig_container", "dxorig_substrate_dir",
           "ucc_compile_dxorig", "ucc_decompile_dxorig"]

_RO_MOUNT = "/opt/DXORIG-ro"                 # host DXORIG System, bind-mounted read-only
_SYS = "/opt/DXORIG/System"                  # writable copy — CWD for UCC; game root is /opt/DXORIG
_GAME_ROOT = "/opt/DXORIG"
_UCC = f"{_SYS}/UCC.exe"
_INI = f"{_SYS}/DeusEx.ini"
_MIN_U_BYTES = 64
_WINE_TIMEOUT = 300.0
_EXFIL_TIMEOUT = 60.0


def _edit_packages_upto(ini_text: str, package: str) -> str:
    """Return `ini_text` with the `[Editor.EditorEngine]` EditPackages list trimmed so `<package>`
    is the LAST entry. Everything AFTER the cut is dropped so `make`'s dependent-invalidation can't
    reach a game package with no `Classes/` dir and abort ("Can't find files matching
    ..\\<Pkg>\\Classes\\*.uc" — the content packages DeusExItems/Deco/Characters/… ship as `.u` only).
    If the target is already listed, cut there; otherwise cut just past `ConSys` (the last package a
    `#exec CONVERSATION IMPORT` needs — it carries the Conversation/ConEvent/… classes) and append
    the target, so the kept prefix is Core…ConSys + <package>."""
    def is_ep(ln: str) -> bool:
        return ln.strip().casefold().startswith("editpackages=")

    lines = ini_text.splitlines()
    order = [ln.strip().split("=", 1)[1].strip() for ln in lines if is_ep(ln)]
    if package in order:
        keep = order[:order.index(package) + 1]
    else:
        base = order[:order.index("ConSys") + 1] if "ConSys" in order else order
        keep = base + [package]
    at = next((i for i, ln in enumerate(lines) if is_ep(ln)), None)
    out = [ln for ln in lines if not is_ep(ln)]
    if at is None:
        at = next(i for i, ln in enumerate(out)
                  if ln.strip().casefold() == "[editor.editorengine]") + 1
    else:
        at -= sum(1 for ln in lines[:at] if is_ep(ln))
    out[at:at] = [f"EditPackages={p}" for p in keep]
    return "\n".join(out) + ("\n" if ini_text.endswith("\n") else "")


def dxorig_substrate_dir():
    """Host path of the DX substrate (`uned/DXORIG/System`). Raises `UccError` if absent so a
    caller/test skips cleanly instead of spinning a container that would fail."""
    d = tool_assets.uned_dir() / "DXORIG" / "System"
    if not (d / "UCC.exe").is_file() or not (d / "Core.u").is_file():
        raise UccError(f"DX substrate missing at {d} — run uedcli/uscript/fetch_dxorig.sh")
    return d


@contextmanager
def dxorig_container(*, state_dir):
    """Spin a no-GUI build container with the DX substrate mounted read-only, copy it to a writable
    `/opt/DXORIG/System`, yield the container name, tear it down."""
    host = str(dxorig_substrate_dir())
    with ephemeral_build_container(state_dir=state_dir,
                                   mounts=[Mount(host_dir=host, container_dir=_RO_MOUNT)]) as name:
        _exec(name, "sh", "-c",
              f"mkdir -p {_SYS} && cp -a {_RO_MOUNT}/. {_SYS}/ && "
              f"test -f {_SYS}/User.ini || cp {_INI} {_SYS}/User.ini")
        yield name


def _wine(container: str, *args: str, timeout: float = _WINE_TIMEOUT) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["docker", "exec", "-w", _SYS, container, "wine", *args],
                              capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise UccError(f"`wine {' '.join(args)}` did not finish within {timeout:.0f}s in "
                       f"{container} (torn down)") from None


def _exfil(container: str, path: str) -> bytes:
    r = subprocess.run(["docker", "exec", container, "cat", path], capture_output=True,
                       timeout=_EXFIL_TIMEOUT)
    if r.returncode != 0:
        raise UccError(f"could not read {path} from {container}: "
                       f"{r.stderr.decode(errors='replace').strip()}")
    return r.stdout


def ucc_compile_dxorig(container: str, package: str, classes: dict[str, str],
                       con_files: dict[str, bytes] | None = None) -> dict[str, bytes]:
    """Compile `<package>` from `classes` ({filename -> source}) with the original DX UCC and return
    EVERY produced `<package>*.u` as {filename -> bytes} (the class package plus any `<package>Text.u`
    / `<package>Audio*.u` a `#exec CONVERSATION IMPORT` emitted). `con_files` ({filename -> bytes})
    are staged into both the package dir and the System CWD so `#exec CONVERSATION IMPORT FILE="X"`
    resolves. CLEAN rebuild every call.

    Success requires "Success - 0 error(s)" in the output AND a produced `<package>.u` larger than a
    64-byte empty stub. The process exit code is NOT part of the gate: the original build's shutdown
    GC faults (GPF) while destroying some conversation object graphs, AFTER the packages are saved."""
    pkg_dir = f"{_GAME_ROOT}/{package}"
    _exec(container, "sh", "-c",
          f"rm -rf {pkg_dir} {_SYS}/{package}*.u; mkdir -p {pkg_dir}/Classes")
    for filename, source in classes.items():
        _exec(container, "sh", "-c", f"cat > {pkg_dir}/Classes/{filename}", input_text=source)
    for filename, data in (con_files or {}).items():
        for dest in (f"{pkg_dir}/{filename}", f"{_SYS}/{filename}"):
            subprocess.run(["docker", "exec", "-i", container, "sh", "-c", f"cat > {dest}"],
                           input=data, capture_output=True, check=True, timeout=_EXFIL_TIMEOUT)

    ini = _edit_packages_upto(_exec(container, "cat", _INI), package)
    _exec(container, "sh", "-c", f"cat > {_INI}", input_text=ini)

    make = _wine(container, _UCC, "make")
    out = make.stdout + make.stderr
    names = _exec(container, "sh", "-c",
                  f"cd {_SYS} && ls {package}*.u 2>/dev/null || true").split()
    target = f"{package}.u"
    size = int(_exec(container, "sh", "-c",
                     f"test -f {_SYS}/{target} && wc -c < {_SYS}/{target} || echo -1").strip())
    if "Success" not in out or size <= _MIN_U_BYTES:
        raise UccError(f"DX UCC make failed for package {package!r} ({target} = {size} bytes): "
                       f"{out[-800:].strip()}")
    return {n: _exfil(container, f"{_SYS}/{n}") for n in names}


def _target_arg(u_path_or_name: str) -> str:
    if "/" in u_path_or_name:
        return to_z_path(u_path_or_name)
    return u_path_or_name if u_path_or_name.endswith(".u") else f"{u_path_or_name}.u"


def ucc_decompile_dxorig(container: str, u_path_or_name: str) -> dict[str, str]:
    """Decompile a package's classes to source with the DX UCC: `batchexport <pkg> class uc <out>`,
    returning `{ClassName.uc: source}`. A stock package resolves by bare name via Paths; an arbitrary
    `.u` is passed by its container path."""
    out_dir = f"/work/dxorig-export-{uuid4().hex[:8]}"
    _exec(container, "sh", "-c", f"rm -rf {out_dir}; mkdir -p {out_dir}")
    r = _wine(container, _UCC, "batchexport", _target_arg(u_path_or_name),
              "class", "uc", to_z_path(out_dir))
    sources = _read_uc_dir(container, out_dir)
    if r.returncode != 0 or not sources:
        raise UccError(
            f"DX UCC batchexport produced no classes for {u_path_or_name!r} (exit {r.returncode}): "
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

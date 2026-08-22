"""Host<->container file exchange. With the broad /repo bind mount gone (container-fs-isolation
design), no container sees the repo tree: the target .dx is `docker cp`'d IN, results
(verified .dx) are streamed OUT via `docker exec cat` (`docker cp`-out remounts the container's
mounts read-only, which rootless docker cannot do for a `:ro` bind mount), and all editor scratch
lives in the container-local /work dir that dies with the container. This module is the SOLE owner of
/work path generation -- every path is uuid-suffixed because /work is shared by reused/standing
containers (a fixed path would race). cp_in returns a RAW POSIX /work path; callers wrap with
`driver.to_z_path` themselves where wine/UCC needs Z:\\ (don't bake Z:\\ in here)."""
from __future__ import annotations

import subprocess
import uuid
from pathlib import Path

from .driver import DriverError

WORK = "/work"

# Hard bound on ONE `docker cp`, in seconds. Generous rather than tight: the payload is a whole map
# package or a directory of exported textures, and a cold host page-cache copy of a ~50 MB `.dx`
# through the docker daemon is legitimately slow. Anything past this is dockerd or the container not
# answering, and per `dev/docs/rules/background-work.md` ("never leave a wait open-ended") that must
# surface as a named error rather than parking the caller forever — a wedged copy used to hang the
# whole verb with no output at all.
CP_TIMEOUT = 300.0
# Hard bound on the best-effort `rm -rf` cleanup exec. Short: it is a local unlink inside a container
# that is about to die anyway, and cleanup must never delay the caller.
REMOVE_TIMEOUT = 60.0


def work_path(ext: str) -> str:
    """A fresh unique /work/<uuid>.<ext> file path (container-side, POSIX)."""
    return f"{WORK}/{uuid.uuid4().hex}.{ext}"


def work_dir(stem: str) -> str:
    """A fresh unique /work/<stem>-<uuid> directory path (container-side, POSIX)."""
    return f"{WORK}/{stem}-{uuid.uuid4().hex}"


def _cp(args: list[str], what: str) -> None:
    """One BOUNDED `docker cp`. A copy that does not finish within `CP_TIMEOUT` raises
    `DriverError` naming what was being copied — a `RuntimeError` subclass, so the materialize /
    preview guards already turn it into a clean `exit 2` message instead of a traceback or, as
    before, an unbounded hang with no output."""
    try:
        subprocess.run(args, check=True, capture_output=True, text=True, timeout=CP_TIMEOUT)
    except subprocess.TimeoutExpired:
        raise DriverError(f"docker cp did not finish within {CP_TIMEOUT:.0f}s ({what}) — "
                          f"dockerd or the container is not answering") from None
    except subprocess.CalledProcessError as e:
        # Surface docker's own stderr (else the caller sees only "exit status N" and can't tell a
        # vanished container from a bad path — CLAUDE.md "error messages include the offending value").
        raise DriverError(f"docker cp failed ({what}): {(e.stderr or '').strip() or 'no stderr'}") \
            from None


def cp_in(container: str, host_path: str, *, ext: str) -> str:
    """Copy a host file into the container at a freshly-minted /work path; return that path."""
    cpath = work_path(ext)
    _cp(["docker", "cp", host_path, f"{container}:{cpath}"], f"{host_path} → {container}:{cpath}")
    return cpath


def cp_out(container: str, container_path: str, host_path: str) -> None:
    """Stream a container FILE out to a host path via `docker exec … cat` — NOT `docker cp`.
    `docker cp` from a running container remounts every one of the container's mounts read-only for
    the copy, and rootless docker cannot remount a `:ro` bind mount (`/stubs`): it fails
    `remount-ro … operation not permitted`. `docker exec cat` reads the file's bytes with no remount,
    so it works under rootless and rootful alike — the SOLE cp-out path on every host, uniform, not a
    host-conditional fallback. File-only (all callers copy a single `.dx`/T3D); a directory would need
    a `tar` stream instead."""
    what = f"{container}:{container_path} → {host_path}"
    try:
        with open(host_path, "wb") as out:
            subprocess.run(["docker", "exec", container, "cat", container_path],
                           check=True, stdout=out, stderr=subprocess.PIPE, timeout=CP_TIMEOUT)
    except subprocess.TimeoutExpired:
        Path(host_path).unlink(missing_ok=True)   # a truncated stream must not be left at the dest
        raise DriverError(f"docker exec cat did not finish within {CP_TIMEOUT:.0f}s ({what}) — "
                          f"dockerd or the container is not answering") from None
    except subprocess.CalledProcessError as e:
        Path(host_path).unlink(missing_ok=True)   # cat wrote nothing/partial before failing
        raise DriverError(f"docker exec cat failed ({what}): "
                          f"{(e.stderr or b'').decode(errors='replace').strip() or 'no stderr'}") \
            from None
    except OSError as e:
        raise DriverError(f"cannot write {host_path} ({what}): {e}") from None


def remove(container: str, *paths: str) -> None:
    """Best-effort cleanup of /work paths (the editor is crash-prone; never raise on cleanup).
    Bounded and swallowed: a container that has already died — or a wedged dockerd — must not turn
    cleanup into a hang on a path the caller is only passing through."""
    try:
        subprocess.run(["docker", "exec", container, "rm", "-rf", *paths],
                       capture_output=True, text=True, check=False, timeout=REMOVE_TIMEOUT)
    except subprocess.TimeoutExpired:
        pass

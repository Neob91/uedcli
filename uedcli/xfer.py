"""Host<->container file exchange. With the broad /repo bind mount gone (container-fs-isolation
design), no container sees the repo tree: the target .dx is `docker cp`'d IN, results
(verified .dx, screenshots, texture PNGs) are `docker cp`'d OUT, and all editor scratch lives in
the container-local /work dir that dies with the container. This module is the SOLE owner of
/work path generation -- every path is uuid-suffixed because /work is shared by reused/standing
containers (a fixed path would race). cp_in returns a RAW POSIX /work path; callers wrap with
`driver.to_z_path` themselves where wine/UCC needs Z:\\ (don't bake Z:\\ in here)."""
from __future__ import annotations

import subprocess
import uuid

WORK = "/work"


def work_path(ext: str) -> str:
    """A fresh unique /work/<uuid>.<ext> file path (container-side, POSIX)."""
    return f"{WORK}/{uuid.uuid4().hex}.{ext}"


def work_dir(stem: str) -> str:
    """A fresh unique /work/<stem>-<uuid> directory path (container-side, POSIX)."""
    return f"{WORK}/{stem}-{uuid.uuid4().hex}"


def cp_in(container: str, host_path: str, *, ext: str) -> str:
    """Copy a host file into the container at a freshly-minted /work path; return that path."""
    cpath = work_path(ext)
    subprocess.run(["docker", "cp", host_path, f"{container}:{cpath}"],
                   check=True, capture_output=True, text=True)
    return cpath


def cp_out(container: str, container_path: str, host_path: str) -> None:
    """Copy a container file out to a host path."""
    subprocess.run(["docker", "cp", f"{container}:{container_path}", host_path],
                   check=True, capture_output=True, text=True)


def remove(container: str, *paths: str) -> None:
    """Best-effort cleanup of /work paths (the editor is crash-prone; never raise on cleanup)."""
    subprocess.run(["docker", "exec", container, "rm", "-rf", *paths],
                   capture_output=True, text=True, check=False)

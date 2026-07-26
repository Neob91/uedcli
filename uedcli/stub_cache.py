"""Stub cache: built v69 `.u` packages + a per-package JSON sidecar, keyed so a changed input /
dep / substrate / toolchain invalidates dependents.

ONE sidecar per package (`<pkg>.json` beside `<pkg>.u`) — NOT a single shared manifest two
different-package builders could clobber (lost-update race). The sidecar is written LAST, only
after the `.u` is in place, so its mere presence certifies "built clean"; reuse additionally
re-confirms the `.u`'s sha (`output_sha`) so a torn `.u`/sidecar pair from concurrent same-package
builds is rejected, not served. Both files are placed by atomic rename. See
`dev/docs/specs/2026-06-21-uedcli-package-stubbing-design.md`.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True, kw_only=True)
class CacheKey:
    source_sha: str             # sha256 of the v68 `<P>.u` input
    dep_shas: dict[str, str]    # direct code dep -> its identity sha
    substrate_id: str           # sha over the committed v69 link set
    toolchain_id: str           # umodel + UCC + pipeline-format id


@dataclass(frozen=True, kw_only=True)
class StubManifest:
    file: str
    output_sha: str             # sha256 of the built `<P>.u` this sidecar certifies
    source_sha: str
    dep_shas: dict[str, str]
    substrate_id: str
    toolchain_id: str
    built_at: str


def sha256_file(path: Path | str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fd:
        for chunk in iter(lambda: fd.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _sidecar_path(cache_dir: Path | str, name: str) -> Path:
    return Path(cache_dir) / f"{name}.json"


def _atomic_write(path: Path, data: bytes) -> None:
    """Write `data` to `path` via a temp file in the same dir + `os.replace` (atomic, same fs)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def store_stub(cache_dir: Path | str, name: str, built_u: Path | str, key: CacheKey) -> Path:
    """Place the built `<name>.u` into the cache and write its sidecar LAST. Returns the cached
    `.u` path."""
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / f"{name}.u"
    # Read the bytes ONCE and hash exactly what we write — the whole reuse re-confirm rests on
    # `output_sha` matching the stored `.u`.
    payload = Path(built_u).read_bytes()
    output_sha = hashlib.sha256(payload).hexdigest()
    _atomic_write(target, payload)

    manifest = StubManifest(
        file=f"{name}.u",
        output_sha=output_sha,
        source_sha=key.source_sha,
        dep_shas=dict(key.dep_shas),
        substrate_id=key.substrate_id,
        toolchain_id=key.toolchain_id,
        built_at=datetime.now(timezone.utc).isoformat(),
    )
    _atomic_write(_sidecar_path(cache, name), json.dumps(asdict(manifest), indent=2).encode())
    return target


def _load_sidecar(sidecar: Path) -> StubManifest | None:
    """Parse a sidecar to a manifest, or None if it can't be read/parsed. A corrupt or
    schema-drifted sidecar must be a cache MISS (rebuild) at the pre-lock resolution stage, never
    an exception that aborts resolution."""
    try:
        return StubManifest(**json.loads(sidecar.read_text()))
    except (json.JSONDecodeError, TypeError, ValueError, OSError):
        return None


def read_manifest(cache_dir: Path | str, name: str) -> StubManifest | None:
    sidecar = _sidecar_path(cache_dir, name)
    if not sidecar.exists():
        return None
    return _load_sidecar(sidecar)


def cached_stub(cache_dir: Path | str, name: str, key: CacheKey) -> Path | None:
    """Return the cached `<name>.u` iff its sidecar is present, every key component matches, AND the
    sidecar's `output_sha` re-confirms the on-disk `.u` (rejects a torn pair / corrupt file).
    Otherwise None (rebuild)."""
    manifest = read_manifest(cache_dir, name)
    if manifest is None:
        return None
    stub = Path(cache_dir) / manifest.file
    if not stub.exists():
        return None
    if sha256_file(stub) != manifest.output_sha:
        return None
    if (manifest.source_sha, manifest.dep_shas, manifest.substrate_id, manifest.toolchain_id) != (
        key.source_sha, key.dep_shas, key.substrate_id, key.toolchain_id
    ):
        return None
    return stub


def list_manifests(cache_dir: Path | str) -> list[StubManifest]:
    """Every cached package's sidecar, name-sorted — backs `substrate stub --list`."""
    cache = Path(cache_dir)
    if not cache.is_dir():
        return []
    out = []
    for sidecar in sorted(cache.glob("*.json")):
        manifest = _load_sidecar(sidecar)
        if manifest is not None:
            out.append(manifest)
    return out

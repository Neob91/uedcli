"""GET /api/package/{package_name}/raw -- gui-inspector-props-payload-redesign spec §0: serves the
resolved backing .u file's bytes verbatim, no parsing/resolution/JSON. The only NEW backend surface
this feature adds; the frontend (spec §4) parses these bytes itself via the WASM resolve core."""
from __future__ import annotations

import hashlib
import os

from .. import config


class PackageRawError(Exception):
    """A name resolving to a non-.u file, or one absent from the search path entirely -- both a
    clean 404 naming the value (spec §0), classified by `serve/errors.py::error_to_status`."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def find_u_file(search_files: list[tuple[str, str]], package_name: str) -> str:
    """Case-insensitive LOOKUP against `search_files` (config.composed_search_files's own list) --
    never a path join (a join would be a traversal hole; `t3dtree.check_safe_segment`'s existing
    convention is why this project treats that as a real concern elsewhere). Returns the host path
    of the .u file backing `package_name`, or raises `PackageRawError` for a name absent from the
    search path OR one resolving to a non-.u package kind (.dx/.utx/.uax/.umx) -- this route serves
    .u bytes only, never a generic package-file endpoint."""
    want = package_name.casefold()
    for path, _prov in search_files:
        stem = config.pkg_stem(path)
        if stem is not None and stem.casefold() == want:
            if os.path.splitext(path)[1].lower() != ".u":
                raise PackageRawError(f"package is not a .u file: {package_name!r}")
            return path
    raise PackageRawError(f"package not found: {package_name!r}")


# (realpath, size, mtime_ns) -> sha1 hexdigest, keyed by stat tuple directly (closer to
# `schema_cache.cache_key`'s key composition than to `upackage.py`'s `_LOAD_CACHE`, which keys on
# `(realpath, resolved_name)` and checks a fresh stat for staleness -- this cache instead treats a
# changed stat tuple as a new key, no explicit staleness check or eviction needed). A different
# TRADEOFF from `schema_cache.cache_key` itself (which still hashes, but only a stat tuple, never
# the file's own bytes, since ITS cache saves a resolution this route never pays) -- the owner's
# explicit "etag with checksum of .u"
# ruling wants a real checksum here, not a proxy. Unbounded growth over the process's life is
# accepted (one entry per distinct (file, stat) ever served; a `serve` process restart clears it).
_ETAG_CACHE: dict[tuple[str, int, int], str] = {}


def cached_etag_and_bytes_if_needed(key: tuple[str, int, int], realpath: str) -> tuple[str, bytes | None]:
    """`(etag, bytes_or_none)` -- `bytes` is `None` on a cache HIT (the file need not be re-read at
    all to answer a conditional GET whose If-None-Match already matches; the route only reads the
    body when it actually needs to SEND one). A cache MISS reads the file once, computes and caches
    a real sha1 of its own bytes, and returns those same bytes so the route never reads the file
    twice on a cold request."""
    cached = _ETAG_CACHE.get(key)
    if cached is not None:
        return cached, None
    with open(realpath, "rb") as f:
        buf = f.read()
    etag = hashlib.sha1(buf).hexdigest()
    _ETAG_CACHE[key] = etag
    return etag, buf

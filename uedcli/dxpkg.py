"""Offline Unreal Engine 1 header parser (package versions 61, 68, 69) → the set of
packages a .dx depends on. The Import table's FObjectImport records name the package every
imported object (actor classes, meshes, textures, sounds) comes from — authoritative, and the
only place actor-class packages live (T3D headers carry only the UNQUALIFIED class name). Pure
offline Python: no editor, no Wine — runs in the host process. Resolved by the
package-extraction spike (dev/docs/spikes/pkg_extraction/); see
dev/docs/specs/2026-06-18-uedcli-package-extraction-design.md."""
from __future__ import annotations

import os
import struct
from dataclasses import dataclass

_MAGIC = 0x9E2A83C1
# Three versions in the Deus Ex install:
#   61 — five older-format content packages (CoreTexDetail/CoreTexWater/Palettes/Render/TITAN).
#          Name table: null-terminated string + 4-byte ObjectFlags — NO compact-index length
#          prefix (confirmed live 2026-06-23; see dev/docs/spikes/2026-06-23-capability-gaps-round2.md).
#          Import table: identical compact-index format as 68/69.
#   68 — overwhelmingly the Deus Ex install's content packages (.utx/.uax/.umx) — 89/94 sampled.
#   69 — level files (.dx) and the committed UED22 substrate (.u).
#   Both 68 and 69 use ver>=64 name-table layout: compact-index length + string + 4-byte ObjectFlags.
_SUPPORTED_VERSIONS = (61, 68, 69)

_PKG_EXTS = (".u", ".dx", ".utx", ".uax", ".umx")


@dataclass(frozen=True, kw_only=True)
class PackageHeader:
    version: int
    names: list[str]
    imports: list[tuple[int, int, int, int]]   # (ClassPackage, ClassName, PackageIndex, ObjectName)


def _read_compact_index(buf: bytes, pos: int) -> tuple[int, int]:
    """FCompactIndex: signed, variable length (UE1)."""
    b = buf[pos]; pos += 1
    neg = b & 0x80
    val = b & 0x3F
    if b & 0x40:
        shift = 6
        while True:
            b = buf[pos]; pos += 1
            val |= (b & 0x7F) << shift
            shift += 7
            if not (b & 0x80):
                break
    return (-val if neg else val), pos


def _read_name_v61(buf: bytes, pos: int) -> tuple[str, int]:
    """ver<64 name entry: null-terminated ANSI string + u32 ObjectFlags (no compact-index prefix)."""
    end = buf.index(b'\x00', pos)
    s = buf[pos:end].decode('latin-1')
    return s, end + 1 + 4   # skip null + 4-byte flags


def _read_name(buf: bytes, pos: int) -> tuple[str, int]:
    """ver>=64 name entry: compact-index length, string incl. null, u32 flags. NEGATIVE
    length = UTF-16LE of -length code units (DeusEx Unicode Group names, e.g. 20_AireGardens.dx);
    positive = ANSI."""
    length, pos = _read_compact_index(buf, pos)
    if length < 0:
        nbytes = (-length) * 2
        s = buf[pos:pos + nbytes].decode("utf-16-le", "replace").split("\x00", 1)[0]
    else:
        nbytes = length
        s = buf[pos:pos + nbytes].split(b"\x00", 1)[0].decode("latin-1")
    return s, pos + nbytes + 4


def parse_header(path: str) -> PackageHeader:
    buf = open(path, "rb").read()
    tag, ver_l, _flags, namecnt, nameoff, _expcnt, _expoff, impcnt, impoff = \
        struct.unpack_from("<9I", buf, 0)
    if tag != _MAGIC:
        raise ValueError(f"{path}: bad magic {tag:#010x} (not an Unreal package)")
    version = ver_l & 0xFFFF
    if version not in _SUPPORTED_VERSIONS:
        raise ValueError(f"{path}: package version {version} not in {_SUPPORTED_VERSIONS} "
                         "(refusing to guess offsets for an unverified version)")
    _read = _read_name_v61 if version < 64 else _read_name
    names, pos = [], nameoff
    for _ in range(namecnt):
        s, pos = _read(buf, pos)
        names.append(s)
    imports, pos = [], impoff
    for _ in range(impcnt):
        cp, pos = _read_compact_index(buf, pos)
        cn, pos = _read_compact_index(buf, pos)
        pi = struct.unpack_from("<i", buf, pos)[0]; pos += 4
        on, pos = _read_compact_index(buf, pos)
        imports.append((cp, cn, pi, on))
    return PackageHeader(version=version, names=names, imports=imports)


def _name_of(names: list[str], i: int) -> str:
    return names[i] if 0 <= i < len(names) else f"<{i}>"


def direct_packages(path: str) -> set[str]:
    """The top-level package of every import, by walking PackageIndex to the root. This is the
    level's DIRECT dependency set (the .dx's own import table) — what `<role>/packages` stores.

    PackageIndex: 0 = root (this import IS a package; its ObjectName is the name); negative n =
    import entry -n-1 (walk up the outer chain); positive = export in THIS package (not external)."""
    h = parse_header(path)
    pkgs: set[str] = set()
    for entry in h.imports:
        cur, guard = entry, 0
        while True:
            guard += 1
            if guard > 64:
                break
            _cp, _cn, pi, on = cur
            if pi == 0:
                pkgs.add(_name_of(h.names, on))
                break
            if pi < 0:
                parent = -pi - 1
                if 0 <= parent < len(h.imports):
                    cur = h.imports[parent]
                else:
                    break
            else:
                break        # positive = export in THIS package, not an external dep
    return pkgs


def _find_package_file(pkg: str, search_dirs: list[str]) -> str | None:
    """Case-insensitive locate (Wine/NTFS: core.u satisfies a Core import)."""
    want = {(pkg + ext).lower() for ext in _PKG_EXTS}
    for d in search_dirs:
        try:
            entries = os.listdir(d)
        except OSError:
            continue
        for name in entries:
            if name.lower() in want:
                return os.path.join(d, name)
    return None


def transitive_closure(dx_path: str, *, search_dirs: list[str]) -> tuple[set[str], set[str]]:
    """(found, missing): the transitive package closure over EVERY dep — code (.u) AND content
    (.utx/.uax/.umx) — and the packages whose files are NOT on `search_dirs`. The engine
    resolves deps transitively regardless of package kind: `CoreTexMetal.utx` itself depends on
    `CoreTexDetail` (confirmed live 2026-06-20, `unrealed/quirks.md` "Containers / package
    resolution") — a content-to-content dependency a code-only closure would miss entirely.
    `parse_header`/`direct_packages` are generic UPackage-format readers (Name+Import tables),
    not `.dx`-specific, so they work identically on content packages — measured clean against
    the real Deus Ex install (`Tools/uedcli/uned/DeusExAssets/`): closures over 6 real maps land at 6-65
    packages (not "the whole install" of ~190), zero false-missing positives. The five version-61
    content packages (`CoreTexDetail`/`CoreTexWater`/`Palettes`/`Render`/`TITAN`) are supported —
    they use a null-terminated name table rather than the compact-index-prefixed form of 68/69, but
    the same compact-index import table, confirmed 2026-06-23; their own deps are just Core/Engine
    (substrate). `missing` is the fail-fast completeness signal (an under-count is the
    silent-materialize-failure this exists to prevent), so report it, never drop it.

    The ROOT (`dx_path` itself) is NOT covered by that same swallow (review-found 2026-06-20):
    every OTHER frontier node already passed `_find_package_file` (it's a real, located file we
    chose to recurse into, so "can't parse further" only means "stop growing the closure from
    here," never "this dependency doesn't exist"), but the root is the caller's own input and was
    never resolved through that check — a root parse failure (corrupt file, or a real package
    version this parser doesn't yet support) must not silently produce an empty `(found,
    missing)` with NO signal at all that anything went wrong. Letting it propagate keeps that
    distinction: callers that have already independently confirmed `dx_path` exists/parses
    (every current call site does, via the offline UCC export that runs first) never see this;
    a caller that hasn't must decide for itself, the same way an offline-export
    catch handles the analogous UCC-side failure (D-Q5)."""
    seen: set[str] = set()
    missing: set[str] = set()

    def _expand(deps: set[str]) -> list[str]:
        next_paths = []
        for pkg in deps:
            if pkg in seen:
                continue
            seen.add(pkg)
            f = _find_package_file(pkg, search_dirs)
            if f is None:
                missing.add(pkg)
            else:
                next_paths.append(f)
        return next_paths

    frontier = _expand(direct_packages(dx_path))     # root: let a parse failure propagate
    while frontier:
        path = frontier.pop()
        try:
            deps = direct_packages(path)
        except Exception:
            continue          # an unparseable DEPENDENCY is a closure-growth dead end, not a
                              # missing-ness signal — it was already resolved as a real file
        frontier.extend(_expand(deps))
    return seen - missing, missing

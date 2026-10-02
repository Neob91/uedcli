"""Build synthetic UE1 audio packages (`.uax`/`.umx`/`.u`) in memory, for the audio-arm tests.

Test-only — nothing here ships. The audio index is header-only (it reads the name/import/export
TABLES, never object bodies — see `audioindex`), so a fixture needs only correct table entries:
`Sound`/`Music` class imports, group exports (for `Package.Group.Name` paths), and object exports.
Bodies can be empty — except a `.umx`, whose embedded tracker-module bytes we place as an object
body so `umxtitle.sniff_title` (which scans the whole file for a magic) finds them.

Built on `native.pkg_write.build_package` (the from-scratch container writer), like `pkgfixture`.
"""
from __future__ import annotations

from uedcli.native.codec import write_ci
from uedcli.native.pkg_write import NameTable, ImportRec, ExportRec, build_package

RF_OBJ = 0x00000007                          # RF_Public|LoadForClient|LoadForServer — reads ignore it
FIXTURE_GUID = bytes(range(16))              # deterministic so a committed fixture is reproducible

_CLASS_OF_KIND = {"sound": "Sound", "music": "Music"}


def audio_package(*, name: str, kind: str, objects: list[tuple[str | None, str]],
                  embed: bytes = b"", version: int = 69, licensee: int = 0) -> bytes:
    """A synthetic package `name` holding `objects` — a list of `(group | None, object_name)` for
    class `Sound` (kind `sound`) or `Music` (kind `music`). A non-None group becomes an intermediate
    `Package` export so the object's `object_path` is `name.Group.object_name`. `embed` (if given)
    is placed as the FIRST object's body — the raw tracker-module bytes for a `.umx` title sniff."""
    class_name = _CLASS_OF_KIND[kind]
    names = NameTable()
    groups = list(dict.fromkeys(g for g, _ in objects if g is not None))
    for n in ("Core", "Package", "Class", "Engine", class_name, name, *groups,
              *(o for _, o in objects)):
        names.index(n)

    imports = [
        ImportRec(names.index("Core"), names.index("Class"), 0, names.index(class_name)),   # -1
        ImportRec(names.index("Core"), names.index("Class"), 0, names.index("Package")),     # -2
    ]
    class_ref, pkg_class_ref = -1, -2

    exports: list[ExportRec] = []
    group_ref: dict[str, int] = {}
    for g in groups:                              # group exports first → 1-based refs 1..len(groups)
        exports.append(ExportRec(pkg_class_ref, 0, 0, names.index(g), RF_OBJ, b""))
        group_ref[g] = len(exports)
    for i, (g, obj) in enumerate(objects):
        outer = group_ref[g] if g is not None else 0
        body = embed if (i == 0 and embed) else b""
        exports.append(ExportRec(class_ref, 0, outer, names.index(obj), RF_OBJ, body))

    return build_package(version=version, licensee=licensee, package_flags=0,
                         names=names, imports=imports, exports=exports, guid=FIXTURE_GUID)


# --- embedded tracker-module blobs (for .umx title tests) --------------------

def it_module(title: str) -> bytes:
    """A minimal Impulse Tracker header: `IMPM` + a 26-byte song name."""
    return b"IMPM" + title.encode("latin-1").ljust(26, b"\x00")


def s3m_module(title: str) -> bytes:
    """A minimal ScreamTracker 3 header: a 28-byte name, then `SCRM` at offset 0x2C."""
    return title.encode("latin-1").ljust(28, b"\x00") + b"\x00" * (0x2C - 28) + b"SCRM"


def xm_module(title: str) -> bytes:
    """A minimal FastTracker 2 header: `Extended Module: ` then a 20-byte name at +17."""
    return b"Extended Module: " + title.encode("latin-1").ljust(20, b"\x00")

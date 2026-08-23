"""The primitives every other uprops layer builds on: the decoded-property record `Prop`, the
closed sets of UProperty kinds, and the `SchemaError` guard that keeps a corrupt package body from
escaping as a bare traceback."""
from __future__ import annotations

import functools
import struct
from dataclasses import dataclass

from ..upackage import Package, SchemaError, read_compact_index as _read_compact_index


# The closed set of UProperty subclasses (proven finite = 11 by the name-only spike).
PROPERTY_TYPES = frozenset({
    "ArrayProperty", "BoolProperty", "ByteProperty", "ClassProperty", "FloatProperty",
    "IntProperty", "NameProperty", "ObjectProperty", "PointerProperty", "StrProperty",
    "StructProperty",
})


_KINDS_WITH_TYPE_REF = frozenset({
    "ByteProperty", "ObjectProperty", "StructProperty", "ClassProperty", "ArrayProperty",
})


CPF_NET = 0x20                      # PropertyFlags bit: a 2-byte RepOffset follows Category on disk


def _schema_guard(fn):
    """Convert ANY parse-layer escape (IndexError/struct.error/ValueError/RecursionError/
    OverflowError from a corrupt-but-loadable package body — review finding: `load_package`'s
    wrapper covers only the header/tables, and byte-flip fuzzing reached bare tracebacks in the
    body decoders) into a named `SchemaError`, honoring the module's "every parse error raises
    SchemaError" contract. A real SchemaError passes through unchanged."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except SchemaError:
            raise
        except RecursionError:
            raise SchemaError(f"{fn.__name__}: runaway recursion decoding a corrupt "
                              "package body") from None
        except (IndexError, ValueError, OverflowError, KeyError) as e:
            raise SchemaError(f"{fn.__name__}: corrupt package body "
                              f"({type(e).__name__}: {e})") from e
        except struct.error as e:
            raise SchemaError(f"{fn.__name__}: truncated package body ({e})") from e
    return wrapper


@dataclass(frozen=True, kw_only=True)
class Prop:
    name: str
    kind: str                       # e.g. "ByteProperty"
    array_dim: int                  # static-array size; 1 for a scalar
    property_flags: int             # full 32-bit CPF_* flags
    type_ref: int                   # signed object ref of the type tail (0 == None)
    type_name: str | None           # resolved name of type_ref (enum/struct/object class)
    owner: str                      # the class that declares it (FQCN), for diagnostics
    enum_value_names: tuple[str, ...] = ()   # a ByteProperty's LOCAL enum values; () if none/imported
    category: str | None = None     # editor group (`var(Category)`); the declaring class name for a
                                     # bare `var()`; None for a non-editable `var` (name index 0)
    # An `ArrayProperty`'s ELEMENT property (`UArrayProperty::Inner`), decoded as a Prop of its own —
    # so a caller can see the element KIND (`IntProperty`/`ObjectProperty`/`StructProperty`/…) and,
    # through the element's own `type_ref`/`type_name`, the element's enum/struct/object type. This
    # is the only place that information exists: an ArrayProperty's own `type_ref`/`type_name` point
    # at the Inner UProperty OBJECT (so `type_name` is the inner's *name*, e.g. "Ammo", never its
    # kind). None for every non-array Prop, and for an array whose Inner ref is 0 or a cross-package
    # import (the UnrealScript compiler always emits Inner as a child export of the ArrayProperty in
    # the SAME package, so an import there means a corrupt/foreign package). Consumed by
    # `mapimport`'s dynamic-array value decode (board item `level-import-native-editor-less-dx-unr-t3d` §5.2d).
    array_inner: "Prop | None" = None


def _last_compact(buf: bytes, start: int, end: int) -> int:
    pos, last = start, 0
    while pos < end:
        last, pos = _read_compact_index(buf, pos)
    return last


def _safe_name(pkg: Package, nm: int) -> str | None:
    """The name-table entry `nm`, or None if out of range (a malformed-but-loadable package —
    `load_package` checks consume-to-EOF, not that every `nm` indexes a real name)."""
    return pkg.names[nm] if 0 <= nm < len(pkg.names) else None


_STRUCT_BIN_SIZES = {"ByteProperty": 1, "IntProperty": 4, "FloatProperty": 4}

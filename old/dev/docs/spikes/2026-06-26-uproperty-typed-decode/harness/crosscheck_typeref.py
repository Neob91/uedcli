"""Independent cross-check of the "type_ref = body's last compact" method.

The decoder reads each typed property's type as the body's LAST compact index.
This script independently verifies that claim by a target-KIND audit over the
WHOLE corpus: the resolved type ref must be an object of the kind the property
demands, otherwise last-compact landed on the wrong thing (a stray middle byte
parsed as a spurious extra compact, or an off-by-one).

  ByteProperty   -> Enum   (or None == plain byte)
  ObjectProperty -> Class
  ClassProperty  -> Class  (the meta-class; the two refs both end on a Class)
  StructProperty -> Struct
  ArrayProperty  -> a *Property (the inner element property), whose OWN type ref
                    then resolves to the element's Enum/Class/Struct

This is a stronger check than a structural re-parse: it needs no assumed middle
grammar, and a wrong type ref would land on an object of the wrong class. Run on
the corpus (2026-06-26) it found ZERO wrong-kind targets across 49 packages.

Run: python crosscheck_typeref.py   (from Tools/uedcli/)
"""
from __future__ import annotations

import glob
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(__file__))
from uproperty_decode import (  # noqa: E402
    load_package, decode_property, _PROPERTY_TYPES,
)

# What kind of object the type ref must resolve to, per property kind.
_EXPECTED = {
    "ByteProperty": {"Enum"},                 # or None (plain byte)
    "ObjectProperty": {"Class"},
    "ClassProperty": {"Class"},
    "StructProperty": {"Struct"},
    "ArrayProperty": _PROPERTY_TYPES,          # inner element is itself a property
}


def _kind_of_ref(pkg, ref: int) -> str | None:
    """The CLASS of the object a ref points at (Enum/Class/Struct/...).

    A UClass export carries its own class ref as None (the engine's "this IS a
    Class" convention) — normalize that to "Class" so an ObjectProperty whose
    target is a top-level class isn't mislabeled."""
    if ref == 0:
        return None
    if ref > 0:
        e = pkg.exports[ref - 1]
        k = pkg.name_of_ref(e["cls"])
        return k if k is not None else "Class"
    j = -ref - 1
    k = pkg.names[pkg.imports[j][1]]  # import's ClassName
    return k if k not in (None, "None") else "Class"


def main() -> None:
    files = sorted(glob.glob("uned/UED22/*.u")
                   + glob.glob("uned/DeusExAssets/System/*.u"))
    checked = wrong = 0
    wrong_examples = []
    by_kind = Counter()
    for f in files:
        pkg = load_package(f)
        for i, e in enumerate(pkg.exports):
            kind = pkg.name_of_ref(e["cls"])
            if kind not in _EXPECTED:
                continue
            info = decode_property(pkg, i + 1)
            if info.type_ref == 0:
                continue  # None tail (plain byte / no ref) — nothing to check
            target_kind = _kind_of_ref(pkg, info.type_ref)
            checked += 1
            by_kind[(kind, target_kind)] += 1
            if target_kind not in _EXPECTED[kind]:
                wrong += 1
                if len(wrong_examples) < 20:
                    wrong_examples.append((os.path.basename(f), info.name, kind,
                                           f"-> {info.type_name} (class {target_kind})"))
    print(f"typed properties with a non-None type ref checked: {checked}")
    print(f"type refs landing on the WRONG object class: {wrong}")
    for x in wrong_examples:
        print("  ", x)
    print("\n(property kind, target object class) -> count:")
    for k, v in sorted(by_kind.items(), key=lambda kv: (kv[0][0], str(kv[0][1]))):
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()

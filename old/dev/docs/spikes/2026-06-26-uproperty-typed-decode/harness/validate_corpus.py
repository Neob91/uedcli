"""Corpus-wide validation of the UProperty typed decoder against every `.u` in
the committed substrate (v69) AND the v68 install (gitignored).

Counts only REAL CLASS-MEMBER properties — a `*Property` export whose Outer is a
UClass. (A `*Property` whose Outer is a Function/State is a parameter or local,
never a static array; including those inflates the array-dim stats with decode
artifacts. The validator is about the class schema, so it filters to class
members, matching `uproperty_decode.class_properties`.)

Asserts, per package:
  - every class-member *Property decodes without error (array_dim/flags/type_ref);
  - every ByteProperty whose type_ref is a LOCAL Enum decodes that Enum body
    byte-exact (cursor at EOF) into a non-empty tag list; ByteProperties whose
    enum is a cross-package IMPORT are counted separately (not decodable here —
    the enum lives in another package the schema builder must load);
  - every ObjectProperty/StructProperty/ClassProperty type_ref resolves to a
    real object name (never a dangling ref);
  - reports the array-dim distribution (genuine static arrays only).

Run: python validate_corpus.py  (from Tools/uedcli/)
"""
from __future__ import annotations

import glob
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(__file__))
from uproperty_decode import (  # noqa: E402
    load_package, decode_property, enum_values,
    enum_index_by_name, _PROPERTY_TYPES,
)


def _outer_is_class(pkg, outer_idx: int) -> bool:
    """True if the property's Outer is a UClass (a real class member), not a
    Function/State (a param/local)."""
    if outer_idx <= 0 or outer_idx > len(pkg.exports):
        return False
    return pkg.name_of_ref(pkg.exports[outer_idx - 1]["cls"]) in (None, "Class")


def validate_one(path: str) -> dict:
    pkg = load_package(path)
    n_props = n_enum_props = n_enum_imported = n_obj_struct = 0
    enum_fail, type_fail = [], []
    dims = Counter()
    enum_samples = {}
    for i, e in enumerate(pkg.exports):
        kind = pkg.name_of_ref(e["cls"])
        if kind not in _PROPERTY_TYPES:
            continue
        if not _outer_is_class(pkg, e["outer"]):
            continue  # skip function params / locals — not class schema
        try:
            info = decode_property(pkg, i + 1)
        except Exception as ex:  # any decode failure is a hard signal
            type_fail.append((pkg.names[e["nm"]], kind, str(ex)))
            continue
        n_props += 1
        dims[info.array_dim] += 1
        if info.kind == "ByteProperty" and info.type_ref != 0:
            if info.type_ref < 0:  # cross-package import enum — not decodable here
                n_enum_imported += 1
            else:
                ei = info.type_ref  # local Enum export index
                n_enum_props += 1
                try:
                    vals = enum_values(pkg, ei)
                    if not vals:
                        enum_fail.append((info.name, info.type_name, "empty"))
                    elif info.type_name not in enum_samples:
                        enum_samples[info.type_name] = vals
                except Exception as ex:
                    enum_fail.append((info.name, info.type_name, str(ex)))
        if info.kind in ("ObjectProperty", "StructProperty", "ClassProperty"):
            n_obj_struct += 1
            if info.type_ref != 0 and info.type_name is None:
                type_fail.append((info.name, info.kind, f"dangling ref {info.type_ref}"))
    return dict(version=pkg.version, n_props=n_props, n_enum_props=n_enum_props,
                n_enum_imported=n_enum_imported, n_obj_struct=n_obj_struct,
                dims=dims, enum_fail=enum_fail, type_fail=type_fail,
                enum_samples=enum_samples)


def main() -> None:
    files = sorted(glob.glob("uned/UED22/*.u")
                   + glob.glob("uned/DeusExAssets/System/*.u"))
    total_props = total_enums = total_imported = 0
    all_dims = Counter()
    failures = []
    enum_examples = {}
    print(f"{'file':30} {'ver':>3} {'props':>6} {'enums':>6} {'imp-enum':>8} {'obj/struct':>10}  status")
    for f in files:
        try:
            r = validate_one(f)
        except Exception as ex:
            print(f"{os.path.basename(f):30} PARSE ERROR: {ex}")
            failures.append((f, str(ex)))
            continue
        total_props += r["n_props"]
        total_enums += r["n_enum_props"]
        total_imported += r["n_enum_imported"]
        all_dims.update(r["dims"])
        enum_examples.update(r["enum_samples"])
        bad = r["enum_fail"] + r["type_fail"]
        status = "OK" if not bad else f"{len(bad)} FAIL"
        if bad:
            failures.append((f, bad))
        print(f"{os.path.basename(f):30} {r['version']:>3} {r['n_props']:>6} "
              f"{r['n_enum_props']:>6} {r['n_enum_imported']:>8} {r['n_obj_struct']:>10}  {status}")

    print(f"\nTOTAL: {total_props} CLASS-MEMBER properties decoded across {len(files)} packages")
    print(f"  enum-typed with a LOCAL enum (decoded byte-exact): {total_enums}")
    print(f"  enum-typed with a cross-package IMPORT enum (must load that pkg): {total_imported}")
    print(f"array_dim distribution (class members only): {dict(sorted(all_dims.items()))}")
    print(f"\ndecode/enum/type failures: {len(failures)}")
    for f in failures[:20]:
        print("  ", f)

    print("\nSample recovered enums (proof):")
    for name in sorted(enum_examples)[:12]:
        print(f"  {name} = {enum_examples[name]}")


if __name__ == "__main__":
    main()

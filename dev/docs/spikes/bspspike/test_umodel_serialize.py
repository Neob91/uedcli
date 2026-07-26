"""Corpus validation for the UModel serializer (spike deliverable).

Run directly for the per-map EXACT/MISMATCH table:
    python3 test_umodel_serialize.py

Or under pytest (each map is a test):
    python3 -m pytest test_umodel_serialize.py -q

The decisive assertion: re-serializing a parsed UModel body reproduces the
original `buf[offset:offset+size]` byte-for-byte, on every Model export of every
real Deus Ex map (package v68–v69 — original-shipped v68 + UnrealEd-2.2-rebuilt v69;
the Model body format is identical across the bump. v61 Entry.dx fails at the HEADER
only, which is a package-version concern, not a Model-serialize one).
"""
from __future__ import annotations

import sys
from pathlib import Path

import umodel_parser as P
import umodel_serialize as S

_MAPS_DIR = Path(
    "/home/human/src/dx_lum/Tools/uedcli/uned/DeusExAssets/Maps"
)


def _maps() -> list[Path]:
    return sorted(_MAPS_DIR.glob("*.dx"))


def test_primitive_encoders_roundtrip() -> None:
    S._test_primitives()


def _validate_all_models_in(path: Path) -> tuple[int, int, list]:
    """Return (n_models, n_exact, mismatches) for one map (skips v61 header-fail)."""
    try:
        exports = P.find_model_exports(str(path))
    except Exception:
        return 0, 0, [("<header>", 0, "v61/header parse — not a serialize issue")]
    buf = open(path, "rb").read()
    total = exact = 0
    bad = []
    for _exp_idx, name, size, off in exports:
        total += 1
        ok, diff = S.validate_model(buf, off, size)
        if ok:
            exact += 1
        else:
            bad.append((name, size, f"MISMATCH@{diff}"))
    return total, exact, bad


def test_every_map_serializes_byte_exact() -> None:
    """Every Model export in every Deus Ex map (package v68–v69) re-serializes byte-identically."""
    grand_total = grand_exact = 0
    all_bad = []
    for path in _maps():
        try:
            P.find_model_exports(str(path))  # skip the v61 Entry.dx header-fail
        except Exception:
            continue
        total, exact, bad = _validate_all_models_in(path)
        grand_total += total
        grand_exact += exact
        for name, size, tag in bad:
            all_bad.append((path.name, name, size, tag))
    assert grand_exact == grand_total, (
        f"{grand_total - grand_exact} of {grand_total} models not byte-exact: "
        f"{all_bad[:10]}"
    )
    assert grand_total > 70000, f"corpus too small: {grand_total}"


def test_prefix_detection_is_unambiguous() -> None:
    """Each model resolves to exactly one prefix length (42 or 57), never both."""
    ambiguous = []
    for path in _maps():
        try:
            exports = P.find_model_exports(str(path))
        except Exception:
            continue
        buf = open(path, "rb").read()
        for _exp_idx, name, size, off in exports:
            data = buf[off:off + size]
            ok42 = S._walk_arrays(data, size, S._PREFIX_STD) == size
            ok57 = S._walk_arrays(data, size, S._PREFIX_VARIANT) == size
            if ok42 and ok57:
                ambiguous.append((path.name, name, size))
    assert not ambiguous, f"ambiguous prefix on {len(ambiguous)}: {ambiguous[:5]}"


def _main() -> int:
    S._test_primitives()
    print("primitive encoders: PASS\n")

    print(f"{'map':38s} {'models':>7s} {'exact':>7s}  level-model")
    print("-" * 70)
    g_total = g_exact = 0
    header_fail = []
    any_mismatch = []
    for path in _maps():
        try:
            exports = P.find_model_exports(str(path))
        except Exception as e:
            header_fail.append((path.name, repr(e)))
            print(f"{path.name:38s} {'--':>7s} {'--':>7s}  HEADER-FAIL (v61)")
            continue
        total, exact, bad = _validate_all_models_in(path)
        g_total += total
        g_exact += exact
        # level model = largest = exports[0]
        buf = open(path, "rb").read()
        lname, lsize, loff = exports[0][1], exports[0][2], exports[0][3]
        lok, ldiff = S.validate_model(buf, loff, lsize)
        ltag = "EXACT" if lok else f"MISMATCH@{ldiff}"
        for name, size, tag in bad:
            any_mismatch.append((path.name, name, size, tag))
        print(f"{path.name:38s} {total:>7d} {exact:>7d}  "
              f"{lname} {lsize:,}b {ltag}")

    print("-" * 70)
    if any_mismatch:
        print("MISMATCHES:")
        for m in any_mismatch:
            print("  ", m)
    if header_fail:
        print("\nHeader-parse failures (package-version issue, NOT Model-serialize):")
        for fn, e in header_fail:
            print(f"  {fn}: {e}")
    print(f"\n{g_exact}/{g_total} models byte-exact "
          f"(across {len([p for p in _maps()]) - len(header_fail)} maps, package v68–v69)")
    return 0 if g_exact == g_total else 1


if __name__ == "__main__":
    sys.exit(_main())

#!/usr/bin/env python3
"""Canonicalized content diff of two UE1 packages: index-remap noise removed.

Decodes every matched actor export (StateFrame + property tags) with name indices resolved to
strings and object refs resolved to dotted paths, so a name-table or import-table order shift
stops looking like a body difference. Reports:
  1. object-set differences,
  2. per-export prop-list differences grouped by pattern (which props differ, extra, missing),
  3. StateFrame differences (class, probemask, latent -- latent reported but known-garbage),
  4. non-actor bodies (Model/Polys/Level/...) compared by size only (ref-bearing binary).

Usage: canon_diff.py <a.dx> <b.dx> [--show N]
"""
from __future__ import annotations

import argparse
import struct
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))

from uedcli.upackage import load_package, read_compact_index, read_property_tags  # noqa: E402

PT_OBJECT, PT_NAME, PT_STRUCT = 5, 6, 10


def exp_identity(p, i):
    e = p.exports[i]
    chain, outer = [], e["outer"]
    while outer > 0:
        oe = p.exports[outer - 1]
        chain.append(p.names[oe["nm"]])
        outer = oe["outer"]
    prefix = ".".join(reversed(chain))
    nm = p.names[e["nm"]]
    full = f"{prefix}.{nm}" if prefix else nm
    cls = p.object_class_name(i + 1) or "<Class>"
    return f"{cls} {full}"


def canon_value(p, t):
    """A property tag's value with every embedded index resolved."""
    if t.ptype == 3:
        return str(t.bool_value)
    if t.ptype == PT_NAME:
        idx, _ = read_compact_index(t.raw, 0)
        return f"name:{p.names[idx] if 0 <= idx < len(p.names) else idx}"
    if t.ptype == PT_OBJECT:
        ref, _ = read_compact_index(t.raw, 0)
        return f"obj:{p.object_path(ref) or 'None'}"
    if t.ptype == PT_STRUCT and t.struct_name == "PointRegion":
        ref, pos = read_compact_index(t.raw, 0)
        ileaf = struct.unpack_from("<i", t.raw, pos)[0]
        zone = t.raw[pos + 4]
        return f"region:(zone={p.object_path(ref) or 'None'},ileaf={ileaf},zn={zone})"
    return t.raw.hex()


def actor_view(p, i):
    e = p.exports[i]
    pos, end = e["soff"], e["soff"] + e["ssize"]
    sf = None
    if e["flags"] & 0x02000000:
        node, pos = read_compact_index(p.buf, pos)
        _sn, pos = read_compact_index(p.buf, pos)
        probemask = struct.unpack_from("<Q", p.buf, pos)[0]; pos += 8
        pos += 4                                    # LatentAction: known nondeterministic garbage
        if node != 0:
            _off, pos = read_compact_index(p.buf, pos)
        sf = (p.object_path(node), hex(probemask))
    tags, _ = read_property_tags(p, pos, end)
    props = [(t.name, t.array_index, t.struct_name, canon_value(p, t)) for t in tags]
    return sf, props


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("a"); ap.add_argument("b")
    ap.add_argument("--show", type=int, default=15)
    args = ap.parse_args()
    A, B = load_package(args.a), load_package(args.b)
    ids_a = {exp_identity(A, i): i for i in range(len(A.exports))}
    ids_b = {exp_identity(B, i): i for i in range(len(B.exports))}

    only_a = [x for x in ids_a if x not in ids_b]
    only_b = [x for x in ids_b if x not in ids_a]
    print(f"A: {args.a} ({len(A.exports)} exports)\nB: {args.b} ({len(B.exports)} exports)")
    print(f"only in A ({len(only_a)}): {only_a[:20]}")
    print(f"only in B ({len(only_b)}): {only_b[:20]}")

    patterns = Counter()
    examples: dict[str, str] = {}
    n_actor = n_same = 0
    size_only = Counter()
    for ident, i in ids_a.items():
        j = ids_b.get(ident)
        if j is None:
            continue
        ea, eb = A.exports[i], B.exports[j]
        is_actor = bool(ea["flags"] & 0x02000000)
        if not is_actor:
            if ea["ssize"] != eb["ssize"]:
                size_only[ident.split()[0]] += 1
            continue
        n_actor += 1
        try:
            sfa, pa = actor_view(A, i)
            sfb, pb = actor_view(B, j)
        except Exception as ex:
            patterns[f"DECODE FAIL: {ex}"] += 1
            continue
        if sfa != sfb:
            patterns["stateframe differs"] += 1
            examples.setdefault("stateframe differs", f"{ident}: {sfa} vs {sfb}")
        if pa == pb:
            n_same += 1
            continue
        da, db = dict(((n, ai), (s, v)) for n, ai, s, v in pa), \
                 dict(((n, ai), (s, v)) for n, ai, s, v in pb)
        extra_a = sorted(set(da) - set(db))
        extra_b = sorted(set(db) - set(da))
        changed = sorted(k for k in set(da) & set(db) if da[k] != db[k])
        order_only = not extra_a and not extra_b and not changed
        key = (f"order-only" if order_only else
               f"extraA={[k[0] for k in extra_a]} extraB={[k[0] for k in extra_b]} "
               f"changed={[k[0] for k in changed]}")
        patterns[key] += 1
        if key not in examples:
            det = "; ".join(f"{k[0]}: A={da[k]} B={db[k]}" for k in changed[:3])
            examples[key] = f"{ident} {det}"
    print(f"\nactors compared: {n_actor}; identical (canon, latent masked): {n_same}")
    print("\nDIFF PATTERNS (count — pattern | example):")
    for key, cnt in patterns.most_common(args.show):
        print(f"  {cnt:5} — {key}")
        print(f"         e.g. {examples.get(key, '')[:300]}")
    if size_only:
        print(f"\nnon-actor exports with ssize differences by class: {dict(size_only)}")


if __name__ == "__main__":
    main()

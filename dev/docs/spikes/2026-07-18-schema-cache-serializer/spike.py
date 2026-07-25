#!/usr/bin/env python3
"""§9 serializer-format spike: time json.loads on the ACTUAL v1 PackageSchema bundle shape for a
big package, deciding JSON-vs-binary BEFORE the serializer is locked (spec
dev/docs/specs/2026-07-18-package-schema-cache.md §4.4/§9). Run host-native in the dev venv:

    .venv/bin/python dev/docs/spikes/2026-07-18-schema-cache-serializer/spike.py [PKG.u]

Defaults to the install DeusEx.u (§9's reference package); falls back to the largest reachable .u.
Prints blob size + median decode time for JSON and marshal (a stdlib binary baseline). The parse it
replaces is load_package's table parse: DeusEx.u 211 ms (§9)."""
from __future__ import annotations
import json, marshal, os, statistics, sys, time
from dataclasses import asdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
from uedctl import uprops  # noqa: E402


def build_bundle(path, name):
    pk = uprops.load_package(path, name=name)
    classes = uprops.iter_classes(pk)
    cmap = uprops.class_index_map(pk)
    super_refs, abstract, own = {}, {}, {}
    for c in classes:
        cf = c.casefold()
        ci = cmap.get(cf)
        try:
            super_refs[cf] = uprops.super_fqcn_by_index(pk, ci) if ci else None
        except uprops.SchemaError:
            super_refs[cf] = None
        abstract[cf] = uprops.class_is_abstract(pk, c)
        own[cf] = [asdict(p) for p in uprops.own_class_properties(pk, c, owner_fqcn=f"{name}.{c}")]
    return {"v": 1, "package_name": name, "class_list": classes, "cmap": cmap,
            "super_refs": super_refs, "abstract": abstract, "own_props": own}


def median_ms(fn, blob, n=30):
    ts = []
    for _ in range(n):
        t = time.perf_counter(); fn(blob); ts.append((time.perf_counter() - t) * 1000)
    return statistics.median(ts)


def main():
    cand = sys.argv[1] if len(sys.argv) > 1 else "/home/neob91/Games/LutrisDX/drive_c/DX/System/DeusEx.u"
    if not os.path.isfile(cand):
        sys.exit(f"no package at {cand}")
    name = os.path.splitext(os.path.basename(cand))[0]
    print(f"package: {cand} ({os.path.getsize(cand)/1e6:.2f} MB, name={name})")
    b = build_bundle(cand, name)
    print(f"bundle: {len(b['class_list'])} classes, "
          f"{sum(len(v) for v in b['own_props'].values())} own props")

    jtxt = json.dumps(b).encode()
    mtxt = marshal.dumps(b)
    print(f"\nJSON    blob {len(jtxt)/1024:8.1f} KB   json.loads    median {median_ms(json.loads, jtxt):6.2f} ms")
    print(f"marshal blob {len(mtxt)/1024:8.1f} KB   marshal.loads median {median_ms(marshal.loads, mtxt):6.2f} ms")

    # For reference: what load_package (the parse the cache replaces) costs on this package.
    t = time.perf_counter(); uprops.load_package(cand, name=name); parse_ms = (time.perf_counter()-t)*1000
    print(f"\nload_package (the table parse we replace): {parse_ms:6.2f} ms")


if __name__ == "__main__":
    main()

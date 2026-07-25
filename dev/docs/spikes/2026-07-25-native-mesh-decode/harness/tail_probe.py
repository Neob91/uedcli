"""Characterize the 5 trailing bytes Deus Ex writes past UT's `ULodMesh` tail.

Parses each mesh with the UT-shaped layout, then reads whatever remains as `BYTE + INT` and
correlates the INT against the mesh's other counts, so the field can be NAMED rather than
guessed. Also reports each mesh's export class, to see whether the extra bytes track
`LodMesh`-vs-`Mesh`.

Usage: python tail_probe.py <pkg.u> [...]
"""
from __future__ import annotations

import os
import struct
import sys
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", ".."))
from uedctl.upackage import load_package  # noqa: E402
import umesh  # noqa: E402


def main(argv):
    for path in argv[1:]:
        pkg = load_package(path)
        shapes = Counter()
        corr = Counter()
        examples = {}
        for j in umesh.mesh_exports(pkg):
            e = pkg.exports[j]
            end = e["soff"] + e["ssize"]
            cls = pkg.object_class_name(j + 1)
            try:
                m, p = umesh.parse_mesh(pkg, j, strict_end=False)
            except Exception as ex:                      # noqa: BLE001
                shapes[f"{cls}:PARSE-FAIL"] += 1
                examples.setdefault(f"{cls}:PARSE-FAIL", f"{m if 0 else pkg.names[e['nm']]}: {ex}")
                continue
            rest = end - p
            shapes[f"{cls}:+{rest}"] += 1
            examples.setdefault(f"{cls}:+{rest}", pkg.names[e["nm"]])
            if rest == 5:
                b0 = pkg.buf[p]
                val = struct.unpack_from("<i", pkg.buf, p + 1)[0]
                corr[("byte", b0)] += 1
                for label, other in (("verts", len(m.verts)), ("modelverts", m.model_verts),
                                     ("frameverts", m.frame_verts), ("wedges", len(m.wedges)),
                                     ("specialverts", m.special_verts)):
                    if val == other:
                        corr[("int==" + label)] += 1
                corr[("n", "total")] += 1
        print(f"{os.path.basename(path)}: v{pkg.version}")
        for k, n in shapes.most_common():
            print(f"   {k:28s} {n:4d}   e.g. {examples[k]}")
        for k, n in corr.most_common():
            print(f"   corr {str(k):28s} {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

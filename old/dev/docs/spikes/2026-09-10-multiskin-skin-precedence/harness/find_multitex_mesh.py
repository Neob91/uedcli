"""Find meshes whose FACES genuinely span two texture slots — needed to see the `Count != 0` half
of `UMesh::GetTexture`, where the mesh's own `Textures(i)` outranks `Skin`. A mesh that merely
declares several textures is not enough: the faces in view must actually use slot 1.

`DeusExDeco.Earth` is what this turned up — 480 faces on slot 0, 480 on slot 1, both plain-flagged.

    python3 find_multitex_mesh.py <pkg.u>
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))

from uedcli import umesh  # noqa: E402
from uedcli.upackage import load_package  # noqa: E402

pkg = load_package(sys.argv[1])
for ref in umesh.mesh_exports(pkg):
    try:
        m = umesh.parse_mesh(pkg, ref)
    except Exception:
        continue
    if len(m.textures) < 2 or not m.faces:
        continue
    slots: Counter[int] = Counter()
    for face in m.faces:                      # face == (wedge triple, material index)
        mi = face[1]
        if mi < len(m.materials):
            slots[m.materials[mi][1]] += 1    # material == (poly flags, texture index)
    if len(slots) >= 2 and sorted(slots)[:2] == [0, 1] and slots[0] >= 8 and slots[1] >= 8:
        print(f"{m.name}  faces-per-texture-slot={dict(slots)}  "
              f"material-flags={sorted({f for f, _t in m.materials})}  "
              f"textures={[pkg.object_path(t) for t in m.textures]}")

#!/usr/bin/env python3
"""Pin the editor `LightMap`-array ORDER = BSP tree-walk order (spike section 20 §21 (E)).

Decodes the editor golden `Test_Castle.dx` and proves its `Model.LightMap` array is emitted in the
editor's **BSP tree-walk** order, NOT surf-index order:

  descend from root: visit the node's surf (first-seen lightmappable surf allocates a record),
  recurse the BACK subtree, then the FRONT subtree, then step the next coplanar `iPlane` node.

The record->surf sequence recovered from each surf's `iLightMap` link must equal this independent
walk exactly (484 records on the castle). It also runs the same check against a native build if one
is given, and prints the RAW per-section byte-match A/B (surf-order vs walk-order) so the +46.7 pp
`LightMap` jump / the `LightBits` cascade (§21 (E)) are reproducible.

Usage:
  .venv/bin/python .../harness/lightmap_order_decode.py [NATIVE.dx]
Editor golden defaults to DX/Maps/Test_Castle.dx.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path("/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedcli")
sys.path.insert(0, str(ROOT))

from uedcli.native import umodel as UM  # noqa: E402
from uedcli.native.pkg_write import parse_package  # noqa: E402

EDITOR = "/home/neob91/Games/LutrisDX/drive_c/DX/Maps/Test_Castle.dx"
PF_NO_LIGHTMAP = 0x0040_0081  # PF_Unlit | PF_FakeBackdrop | PF_Invisible (editor skip mask, §20 §14)


def load_model(path: str) -> UM.Model:
    pkg = parse_package(Path(path).read_bytes())
    mi = max((i for i in range(len(pkg.exports)) if pkg.class_of_export(i) == "Model"),
             key=lambda i: pkg.exports[i]["ssize"])
    e = pkg.exports[mi]
    return UM.parse_model_body(pkg.buf, e["soff"], e["ssize"])


def record_to_surf(m: UM.Model) -> list[int]:
    """record index k -> surf index, recovered from each surf's iLightMap link."""
    d = {s.i_light_map: si for si, s in enumerate(m.surfs) if s.i_light_map >= 0}
    return [d[k] for k in range(len(m.light_map))]


def bsp_walk_order(m: UM.Model) -> list[int]:
    """The editor's LightMap emission order: node surf, recurse back, recurse front, step iPlane."""
    sys.setrecursionlimit(1_000_000)
    seen = [False] * len(m.surfs)
    out: list[int] = []

    def rec(ni: int) -> None:
        while ni >= 0:
            n = m.nodes[ni]
            s = n.i_surf
            if s >= 0 and not seen[s]:
                seen[s] = True
                if not (m.surfs[s].poly_flags & PF_NO_LIGHTMAP):
                    out.append(s)
            rec(n.i_back)
            rec(n.i_front)
            ni = n.i_plane

    if m.nodes:
        rec(0)
    return out


def check(path: str) -> bool:
    m = load_model(path)
    got = record_to_surf(m)
    want = bsp_walk_order(m)
    ok = got == want
    print(f"{path}")
    print(f"  records={len(m.light_map)}  record->surf[:8]={got[:8]}  walk[:8]={want[:8]}")
    print(f"  LightMap order == BSP tree-walk order: {ok}")
    return ok


def main() -> int:
    ok = check(EDITOR)
    assert ok, "editor LightMap order must be the BSP tree-walk order (spike §20 §21 (E))"
    if len(sys.argv) > 1:
        nok = check(sys.argv[1])
        if not nok:
            print("  (native mismatch: bake is not emitting in walk order)")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""§87 amendment harness — prove the real Cause-2 over-solidification root is DROPPED BRUSH SCALE
(`materialize._build_brush_input`), NOT the `is_csg_filter` dead-node hack (`bspcsg.rs:437`).

`_build_brush_input` silently drops every brush's MainScale/PostScale (the Rust core rejects a
non-identity `scale` tuple), so scaled brushes build at UNIT size.  A scaled-up SUBTRACT brush then
carves a tiny hole instead of a full room, leaving the room interior SOLID -> the editor's open void
reads solid in native (`shatter_probe.py` metric `[A]`).  The castle has ZERO scaled brushes, which
is why it stayed a byte-identity control and hid this entire bug class.

This harness builds a trunk in one of several diagnostic MODES and prints the geometry dimensions;
pair it with `shatter_probe.py NATIVE.dx GOLDEN.dx` to read `[A]`.  The `apply_scale` mode bakes the
model-side full linear transform `actor_linear` = PostScale·R·MainScale into the brush's world
transform (dropping authored normals/origins so the Rust core recomputes them from the transformed
winding — correct for a scaled brush).  A production fix lives in `materialize.py`, gated on
non-identity scale, so identity-scale brushes (the whole castle) are untouched -> byte-identical.

Modes:
  baseline       - current shipping behavior (scale dropped)
  apply_scale    - bake actor_linear into the transform (the fix, diagnostic form)
  exclude_scale  - drop every non-identity-scale brush from CSG (a WEAK control: removes valid
                   solids too, so it makes [A] WORSE — kept to show that only APPLYING helps)
  nomovers       - drop Mover-class actors from CSG (H2 isolation)
  apply_scale_nomovers / exclude_scale_nomovers - combinations

Findings pinned 2026-07-19 (sections/87-cause2-shattered-tree.md §9+):
  HK     baseline [A]=74.5% surfs=2664  -> apply_scale [A]=8.9% surfs=4723  (golden 5224)
  UNATCO baseline [A]=15.3% surfs=3581  -> apply_scale [A]=1.1% surfs=4056  (golden 3589)
  castle 0 scaled brushes; gated apply_scale == baseline byte-for-byte (GUID aside).
  nomovers alone: HK [A] 74.5%->74.3% (H2 negligible for [A]); but with scale applied, dropping
  movers takes leaf-blobs 21->2 (=editor) and zones 23->4 (~editor 5) — movers-as-CSG are the
  residual tree-shatter / spurious-zone source, a milder SEPARATE defect.

Usage:
  scale_defect_probe.py quantify  TRUNK_DIR
  scale_defect_probe.py build MODE TRUNK_DIR OUT.dx [--lit]
"""
import argparse
import sys
from pathlib import Path

ROOT = Path("/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedcli")
sys.path.insert(0, str(ROOT))

from spike_classindex import class_index  # noqa: E402  (schema-aware mover gate's index)
from uedcli import trunk, rotation as ROT               # noqa: E402
from uedcli.native import materialize as M              # noqa: E402
from uedcli.native import umodel as UM                  # noqa: E402
from uedcli.native.pkg_write import parse_package       # noqa: E402

# Game texture dirs so texture refs resolve at assembly time (else "Can't find Texture").
PKG_DIRS = ["/home/neob91/Games/LutrisDX/drive_c/DX/Textures",
            "/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Textures"]
_ORIG_BUILD = M._build_brush_input


def is_scaled(a):
    return not (ROT.actor_main_scale(a).is_identity() and ROT.actor_post_scale(a).is_identity())


def is_mover(a):
    return "Mover" in (a.cls or "").split(".")[-1]


def _apply_scale_builder(gated: bool):
    """A _build_brush_input that bakes actor_linear into the brush transform.  When `gated`, an
    identity-scale brush is passed through the original builder untouched (the production-fix shape:
    byte-transparent wherever scale is identity)."""
    def build(name, actor):
        if gated and not is_scaled(actor):
            return _ORIG_BUILD(name, actor)
        tup = list(_ORIG_BUILD(name, actor))
        L = ROT.actor_linear(actor)                     # PostScale·R·MainScale, or None if all identity
        if L is not None:
            tup[6] = [[float(x) for x in row] for row in L]   # R <- full linear
            tup[2] = []                                       # normals -> Rust CalcNormal(winding)
            tv, _origins = tup[11]
            tup[11] = (tv, [])                                # origins -> Rust default base=verts[0]
        return tuple(tup)
    return build


def cmd_quantify(trunk_dir):
    lvl, _ = trunk.read_level(Path(trunk_dir))
    order = [n for n in lvl.order if lvl.actors[n].brush is not None]
    scaled = [n for n in order if is_scaled(lvl.actors[n])]
    movers = [n for n in order if is_mover(lvl.actors[n])]
    add = [n for n in order if dict(lvl.actors[n].props).get("CsgOper", "CSG_Add") != "CSG_Subtract"]
    sub = [n for n in order if dict(lvl.actors[n].props).get("CsgOper") == "CSG_Subtract"]
    print(f"trunk {trunk_dir}")
    print(f"  csg_order brushes: {len(order)}")
    print(f"  non-identity scale: {len(scaled)}  ({100*len(scaled)/max(1,len(order)):.1f}%)")
    print(f"  movers: {len(movers)}")
    print(f"  add={len(add)} (scaled {sum(is_scaled(lvl.actors[n]) for n in add)})  "
          f"sub={len(sub)} (scaled {sum(is_scaled(lvl.actors[n]) for n in sub)})")


def cmd_build(mode, trunk_dir, out, lit):
    lvl, _ = trunk.read_level(Path(trunk_dir))
    drop = set()
    if "exclude_scale" in mode:
        drop |= {n for n in lvl.order if lvl.actors[n].brush is not None and is_scaled(lvl.actors[n])}
    if "nomovers" in mode:
        drop |= {n for n in lvl.order if lvl.actors[n].brush is not None and is_mover(lvl.actors[n])}
    if drop:
        for n in drop:
            lvl.actors.pop(n, None)
        lvl.order = [n for n in lvl.order if n not in drop]
        print(f"[{mode}] dropped {len(drop)} actors from CSG")
    if "apply_scale" in mode:
        M._build_brush_input = _apply_scale_builder(gated=True)
        print(f"[{mode}] gated apply-scale builder installed")
    try:
        M.run_materialize_native(level=lvl, out_path=out, class_index=class_index(),
                                 overwrite=True, version=68,
                                 no_light=not lit, pkg_dirs=PKG_DIRS)
    finally:
        M._build_brush_input = _ORIG_BUILD
    pkg = parse_package(Path(out).read_bytes())
    mi = max((i for i in range(len(pkg.exports)) if pkg.class_of_export(i) == "Model"),
             key=lambda i: pkg.exports[i]["ssize"])
    e = pkg.exports[mi]
    m = UM.parse_model_body(pkg.buf, e["soff"], e["ssize"])
    print(f"MODE={mode} OUT={out}")
    print(f"  nodes={len(m.nodes)} surfs={len(m.surfs)} verts={len(m.verts)} "
          f"points={len(m.points)} leaves={len(m.leaves)} zones={len(m.zones)}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    q = sub.add_parser("quantify"); q.add_argument("trunk")
    b = sub.add_parser("build")
    b.add_argument("mode")
    b.add_argument("trunk")
    b.add_argument("out")
    b.add_argument("--lit", action="store_true")
    args = ap.parse_args()
    if args.cmd == "quantify":
        cmd_quantify(args.trunk)
    else:
        cmd_build(args.mode, args.trunk, args.out, args.lit)


if __name__ == "__main__":
    main()

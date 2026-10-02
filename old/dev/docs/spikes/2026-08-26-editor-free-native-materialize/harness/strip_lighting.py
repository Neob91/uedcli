#!/usr/bin/env python3
"""Rewrite a built `.dx` with its baked lighting removed, keeping everything else byte-for-byte.

Isolates "no lighting" from "wrong BSP leaves" as the reason a natively built map draws no mesh
actors.  It takes an EDITOR-built map — correct leaves AND baked lighting — and strips exactly the
three things the editor-free native build lacks:

  * `Model.LightMap`   (one `FLightMapIndex` per lit surf)
  * `Model.LightBits`  (the packed shadow bitmaps those indices point into)
  * `Model.Lights`     (the per-leaf light actor reference lists)
  * every `FBspSurf.iLightMap` set to -1

Everything else — nodes, surfs, leaves, zones, bounds, leaf hulls, and every other export in the
package — is carried across unchanged.  If the result still renders meshes, absent lighting is not
what breaks them; if it stops, it is.

    dev/docs/spikes/2026-08-26-editor-free-native-materialize/harness/strip_lighting.py \
        [--keep-lighting] <in.dx> <out.dx>

`--keep-lighting` is the CONTROL: the identical parse/re-serialize/repack round trip with the
lighting left alone.  Run it first — if the control does not render, the round trip itself is broken
and the stripped result proves nothing.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[5]))

from uedcli.native import pkg_write, umodel  # noqa: E402
from uedcli.native.csg_golden import _find_model_export  # noqa: E402


def strip(raw: bytes, *, keep_lighting: bool) -> bytes:
    off, size = _find_model_export(raw)
    model = umodel.parse_model_body(raw, off, size)
    if not keep_lighting:
        model.light_map = []
        model.light_bits = b""
        model.lights = []
        for s in model.surfs:
            s.i_light_map = -1
    # `write_model_body` reproduces the original body byte-for-byte except its leading byte (the
    # UObject property-list terminator, which the writer emits as 0), so carry that one over.
    body = bytes(raw[off : off + 1]) + umodel.write_model_body(model)[1:]

    pp = pkg_write.parse_package(raw)
    names = pkg_write.NameTable()
    for n in pp.names:
        names.index(n)
    if names.names != pp.names:
        raise SystemExit(f"name table is not injective: {len(pp.names)} -> {len(names)}")
    imports = [pkg_write.ImportRec(*rec) for rec in pp.imports]
    exports = []
    for e in pp.exports:
        is_model = e["soff"] == off and e["ssize"] == size
        exports.append(
            pkg_write.ExportRec(
                cls=e["cls"], super_ref=e["sup"], outer=e["outer"], name=e["nm"],
                flags=e["flags"],
                body=body if is_model else raw[e["soff"] : e["soff"] + e["ssize"]],
            )
        )
    return pkg_write.build_package(
        version=pp.version, licensee=pp.licensee, package_flags=pp.flags,
        names=names, imports=imports, exports=exports, guid=pp.guid,
    )


def main() -> None:
    args = sys.argv[1:]
    keep = "--keep-lighting" in args
    args = [a for a in args if a != "--keep-lighting"]
    src, dst = pathlib.Path(args[0]), pathlib.Path(args[1])
    out = strip(src.read_bytes(), keep_lighting=keep)
    dst.write_bytes(out)
    model = umodel.parse_model_body(out, *_find_model_export(out))
    print(
        f"wrote {dst} ({len(out)} bytes): light_map={len(model.light_map)} "
        f"light_bits={len(model.light_bits)} lights={len(model.lights)} "
        f"surfs_with_lightmap={sum(1 for s in model.surfs if s.i_light_map >= 0)} "
        f"nodes={len(model.nodes)} leaves={len(model.leaves)}"
    )


main()

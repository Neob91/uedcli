"""Mesh facts read off a class's default `Mesh` — the file-fact half of the asset-catalog class arm.

`class show` reports a mesh class's **signed mesh-local extents** (plus collision/pivot/drawtype/
parent, which come straight from the resolved class defaults). This module owns the one piece those
facts need beyond `uprops`: turning a class's `Mesh` default object-ref into a decoded bounding box
and rendering it as signed lo..hi extents.

**The one mesh-local frame** (`direction/asset-catalog.md`, class-arm spec §3). The reported extents
are the mesh's own `FBox` with the mesh's `Scale` applied per-axis, then each axis re-sorted to
`lo <= hi` (a negative `Scale` flips an axis and must not yield `lo > hi`), rounded to integer Unreal
units. `Origin`, `RotOrigin` and `DrawScale` are NOT applied: `Origin`/`RotOrigin` move/rotate the
pivot rather than change the box shape, and `DrawScale` varies per placement. These are FILE FACTS —
the box is read from the mesh, never derived. What they settle is seating/footprint (height, whether
the mesh sits at z=0); world-facing stays UNVERIFIED pending the RotOrigin-prevalence probe, so this
module makes no facing claim.

The tool reports the picture, or a NAMED error (`direction/asset-catalog.md`): a class whose `Mesh`
is unresolvable or fails to decode raises `MeshFactError` naming the class and mesh, never a
traceback. A non-mesh class (`DT_Sprite`/`DT_Brush`/`DT_None`) has no mesh to read and is not an
error — the caller reports its mesh/extents as null.
"""
from __future__ import annotations

import re

from . import umesh
from .upackage import load_package

# A class `Mesh` default renders as a T3D object ref, e.g. `LodMesh'DeusExDeco.BarStool'` or, with a
# group, `Mesh'Pkg.Group.Name'`. The package is the first dotted segment, the mesh name the last.
_OBJREF = re.compile(r"^\s*\w+'([^']+)'\s*$")


class MeshFactError(Exception):
    """A mesh fact could not be produced for a class whose `DrawType` is `DT_Mesh` — its `Mesh`
    default is unresolvable, or the mesh body failed to decode. Carries a message naming the class
    and mesh; the CLI turns it into a clean exit 2, never a traceback."""


def parse_mesh_ref(text: str | None) -> tuple[str, str] | None:
    """`LodMesh'Pkg.Group.Name'` -> `("Pkg", "Name")`; None for a missing/`None`/unparseable ref."""
    if not text or text.strip() in ("", "None"):
        return None
    m = _OBJREF.match(text)
    if m is None:
        return None
    parts = m.group(1).split(".")
    if len(parts) < 2:
        return None
    return parts[0], parts[-1]


def signed_extents(box, scale) -> dict[str, list[int]]:
    """The mesh's `FBox` rendered as signed per-axis extents in the one mesh-local frame: `Scale`
    applied per-axis, each axis re-sorted to `lo <= hi`, rounded to integer Unreal units. `box` is
    the decoder's `(Min, Max, valid)` (two `(x, y, z)` float triples); `scale` its `(sx, sy, sz)`.
    Returns `{"x": [lo, hi], "y": [...], "z": [...]}`."""
    mn, mx = box[0], box[1]
    out: dict[str, list[int]] = {}
    for i, axis in enumerate("xyz"):
        a, b = mn[i] * scale[i], mx[i] * scale[i]
        lo, hi = (a, b) if a <= b else (b, a)           # a negative Scale flips the axis; re-sort
        out[axis] = [round(lo), round(hi)]
    return out


def decode_mesh_box(mesh_ref: tuple[str, str], *, class_fqcn: str, resolver):
    """Decode the mesh named by `mesh_ref` (`(package, name)`) and return `(display_ref, box, scale)`
    — `display_ref` is `"Package.Name"`, `box`/`scale` the decoder outputs `signed_extents` reads.
    `resolver(package_name) -> .u path | None` locates the mesh's package on the composed path.
    Raises `MeshFactError` (naming `class_fqcn` and the mesh) on any failure — a missing package, a
    mesh not in it, or a decode desync."""
    pkg_stem, mesh_name = mesh_ref
    display = f"{pkg_stem}.{mesh_name}"
    path = resolver(pkg_stem)
    if path is None:
        raise MeshFactError(f"cannot read mesh facts for {class_fqcn}: mesh package {pkg_stem!r} "
                            f"(for Mesh {display}) is not on the package search path")
    try:
        pkg = load_package(path, name=pkg_stem)
        j = next((j for j in umesh.mesh_exports(pkg)
                  if pkg.names[pkg.exports[j]["nm"]].casefold() == mesh_name.casefold()), None)
        if j is None:
            raise MeshFactError(f"cannot read mesh facts for {class_fqcn}: mesh {display} is not a "
                                f"mesh export in package {pkg_stem}")
        mesh = umesh.parse_mesh(pkg, j)
    except MeshFactError:
        raise
    except Exception as e:                              # any decode desync/bad package → named error
        raise MeshFactError(f"cannot read mesh facts for {class_fqcn}: mesh {display} failed to "
                            f"decode ({type(e).__name__}: {e})") from e
    return display, mesh.box, mesh.scale

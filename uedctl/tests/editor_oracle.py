"""The live-UnrealEd ORACLE for `brush intersect` / `brush deintersect` — TEST SUPPORT ONLY.

This is the editor-driven implementation the native verbs replaced.  It is **not a shipping verb**
and has no CLI surface (the old `stash intersect`/`stash deintersect` were deleted when the native
path landed).  It survives for exactly one job: REGENERATING the committed goldens in
`fixtures/intersect/` that the offline suite diffs the native merge against.

Why it stays out of the standing gate: driving UnrealEd needs the live `dx-lum-uned` container and
the editor is crash-prone and wedges silently (`unrealed/quirks.md` "Stability"), so it runs only
under `-m integration`.  The committed goldens are the standing bar.

**The `EDIT PASTE` +32uu drift matters here.** The set is placed via `EDIT PASTE`, which drifts the
pasted actors +32uu on all three axes, so uedctl pre-subtracts 32 (`unrealed/quirks.md`).  The
wrap-subtract cube below is written at `(cx-32, cy-32, cz-32)` for exactly that reason and lands at
`(cx, cy, cz)` in WORLD space — coincident with the `BRUSH IMPORT`ed builder, which takes no paste
and so needs no compensation.  The native path has no paste and therefore no offset
(`brushcsg.BUILDER_PAD == WRAP_PAD`); do not "port" the -32.
"""
from __future__ import annotations

import os
import tempfile

from uedctl import builders, writes, xfer
from uedctl.driver import Driver, to_z_path
from uedctl.editor import ensure_editor, stop_editor
from uedctl.emit import emit_brush_block, emit_map
from uedctl.uuid7 import uuid7


def _scaffold_dims(actors):
    """The editor impl's builder/wrap geometry: `bbox + 64` on every axis, centred on the set."""
    brush_actors = [a for a in actors if a.brush is not None]
    lo, hi = writes.union_bounds(brush_actors)
    center = tuple((float(lo[i]) + float(hi[i])) / 2 for i in range(3))
    size = tuple(float(hi[i] - lo[i]) + 64 for i in range(3))
    return center, size


def _export_builder(driver) -> str:
    """`BRUSH EXPORT` the (now carved) builder brush back to the host as a T3D brush block."""
    export_path = xfer.work_path("t3d")
    driver.exec(f"BRUSH EXPORT FILE={to_z_path(export_path)}")
    fd, host_tmp = tempfile.mkstemp(suffix=".t3d")
    try:
        os.close(fd)
        xfer.cp_out(driver.container, export_path, host_tmp)
        with open(host_tmp) as fh:
            return fh.read()
    finally:
        try:
            os.unlink(host_tmp)
        except OSError:
            pass


def _wrap_in_actor(raw_block: str, csg_oper: str) -> str:
    return (
        "Begin Actor Class=Engine.Brush Name=Brush\n"
        f"    CsgOper={csg_oper}\n"
        "    Begin Brush Name=Model_Brush\n"
        + raw_block
        + "    End Brush\n"
        "    Brush=Model'MyLevel.Model_Brush'\n"
        "    Location=(X=0,Y=0,Z=0)\n"
        '    Name="Brush"\n'
        "End Actor\n"
    )


def intersect(driver, actors) -> str:
    """Drive `BRUSH FROM INTERSECTION` over `actors` and return the result as one brush actor T3D.

    The empty background is forced by a wrap-SUBTRACT cube pasted first (see the module note on the
    -32 paste compensation); the builder is the same box, `BRUSH IMPORT`ed.
    """
    center, size = _scaffold_dims(actors)
    cx, cy, cz = center
    driver.map_new()
    wrap = builders.make_brush_actor(
        "WrapSubtract0", builders.cube(*size),
        location=(cx - 32, cy - 32, cz - 32),          # +32 paste drift compensation
        csg="subtract")
    driver.set_clipboard(emit_map([wrap]))
    driver.edit_paste()
    writes._re_add(driver, actors)
    driver.rebuild()

    translated = builders.translate_brush(builders.cube(*size), cx, cy, cz)
    container_path = writes._write_container_file(driver, emit_brush_block(translated))
    driver.exec(f"BRUSH IMPORT FILE={to_z_path(container_path)}")
    driver.exec("BRUSH FROM INTERSECTION")
    return _wrap_in_actor(_export_builder(driver), "CSG_Add")


def deintersect(driver, actors) -> str:
    """Drive `BRUSH FROM DEINTERSECTION` — the default SOLID world, no wrap cube."""
    center, size = _scaffold_dims(actors)
    cx, cy, cz = center
    driver.map_new()
    writes._re_add(driver, actors)
    driver.rebuild()

    translated = builders.translate_brush(builders.cube(*size), cx, cy, cz)
    container_path = writes._write_container_file(driver, emit_brush_block(translated))
    driver.exec(f"BRUSH IMPORT FILE={to_z_path(container_path)}")
    driver.exec("BRUSH FROM DEINTERSECTION")
    return _wrap_in_actor(_export_builder(driver), "CSG_Subtract")


def run(verb: str, actors, *, state_dir, container: str = "dx-lum-uned") -> str:
    """Spin a per-command EPHEMERAL editor, run `verb`, tear it down; return the result T3D.

    A fresh uuid7 container created and destroyed inside this one call — the same shape
    `level materialize` uses.  Pure geometry CSG, so there is no package/paths load set to wire.
    """
    impl = intersect if verb == "intersect" else deintersect
    ed_id = uuid7()
    try:
        return impl(Driver(container=ensure_editor(ed_id, mounts=None, state_dir=state_dir)),
                    actors)
    finally:
        stop_editor(ed_id, state_dir)                  # always tear the ephemeral container down

"""Geometry + lighting extraction and comparison -- the `uedcli`/`uedcli_native` half of the parity
report. Needs the built `uedcli_native` extension (no live editor). Reuses the same read paths
`regression_gate.py`/`breadth_gate.py` (geometry) and `light_spotcheck_unatco.py`/
`light_spotcheck_wanchai.py` + `lightparity.py` (lighting) already use, so this reports the identical
numbers those scripts would for the same trunk+golden pair.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import parity_lib as pl

ROOT = Path(__file__).resolve().parents[5]
NATIVE_MAT_HARNESS = ROOT / "dev/docs/spikes/2026-07-15-native-materialize/harness"
LIGHT_HARNESS = ROOT / "dev/docs/spikes/2026-08-27-native-light-apply-parity/harness"
DECONTAINERIZE_HARNESS = ROOT / "dev/docs/spikes/2026-06-27-decontainerize-uedcli/harness"


def _ensure_imports() -> None:
    for p in (ROOT, NATIVE_MAT_HARNESS, NATIVE_MAT_HARNESS / "editor-tree-oracle", LIGHT_HARNESS,
             DECONTAINERIZE_HARNESS):
        sp = str(p)
        if sp not in sys.path:
            sys.path.insert(0, sp)


def parse_dx_model(dx_path: Path):
    """The level BSP `Model` of a built map -- the largest `Engine.Model` export (every brush actor
    also owns a small shape Model; the world BSP dwarfs them), same rule `regression_gate.py`/
    `lightparity.py` both use. Works on ANY built `.dx` (golden or native's own assembled output) --
    both are read through this one path so their `Model`s are extracted identically."""
    _ensure_imports()
    import utexture_decode as UT
    from uedcli.native import umodel as UM
    pkg = UT.load_package(str(dx_path))
    models = [i for i in range(len(pkg.exports)) if pkg.class_of_export(i) == "Model"]
    mi = max(models, key=lambda i: pkg.exports[i]["ssize"])
    return UM.parse_model_body(pkg.buf, pkg.exports[mi]["soff"], pkg.exports[mi]["ssize"])


def object_paths(dx_bytes: bytes) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """`(export_paths, import_paths)` for a built `.dx` -- the full dotted path of every table entry,
    which is what `pl.resolve_surf_refs` needs to compare a surf's `texture_ref`/`i_actor` by identity
    instead of by raw table position (see `pl.SURF_OBJECT_REF_FIELDS`). A cheap header/tables-only
    parse; kept separate from `parse_dx_model` (which decodes only the world Model's body and has no
    access to the tables) rather than widening that function's return shape for its other callers."""
    _ensure_imports()
    from uedcli.native.pkg_write import parse_package
    pkg = parse_package(dx_bytes)
    return pl.object_paths([(e["outer"], pkg.names[e["nm"]]) for e in pkg.exports],
                           [(i[2], pkg.names[i[3]]) for i in pkg.imports])


def _temp_dx(data: bytes) -> Path:
    """Write `.dx` bytes to a throwaway temp file -- `parse_dx_model`/`lightparity.level_model`
    read a path, not bytes, and native's own build only exists in memory until assembled."""
    with tempfile.NamedTemporaryFile(suffix=".dx", delete=False) as f:
        f.write(data)
        return Path(f.name)


def build_native_model(trunk_dir: Path):
    """Build the native world Model directly (`uedcli_native.build_geometry_bspcsg`) -- the same
    call `regression_gate.py`/`breadth_gate.py` make, bypassing `level materialize`'s CLI. Returns
    `(model, level)`. `spike_classindex.class_index()` resolves `$UEDCLI_PROJECT`, so this points it
    at the trunk's own project root (`trunk_dir.parent.parent`, `_scratch_project`-shaped)."""
    _ensure_imports()
    import os
    os.environ["UEDCLI_PROJECT"] = str(trunk_dir.parent.parent)
    from uedcli import trunk as trunk_mod
    from uedcli.native import brush_marshal as BM
    from uedcli.native import umodel as UM
    import uedcli_native
    from spike_classindex import class_index

    level, _ranks = trunk_mod.read_level(trunk_dir)
    ci = class_index()
    names = [n for n in level.order
             if level.actors[n].brush is not None and BM._in_world_csg(level.actors[n], ci)]
    ins = [BM._build_brush_input(n, level.actors[n]) for n in names]
    built = uedcli_native.build_geometry_bspcsg(ins)
    nbody = uedcli_native.serialize_model(built)
    return UM.parse_model_body(nbody, 0, len(nbody)), level


def geometry_counts(model) -> pl.GeometryCounts:
    return pl.GeometryCounts(nodes=len(model.nodes), surfs=len(model.surfs),
                             leaves=len(model.leaves), verts=len(model.verts),
                             points=len(model.points), vectors=len(model.vectors))


def compare_geometry(trunk_dir: Path, golden_path: Path) -> pl.GeometryDelta:
    native_model, _level = build_native_model(trunk_dir)
    golden_model = parse_dx_model(golden_path)
    return pl.GeometryDelta(native=geometry_counts(native_model),
                            golden=geometry_counts(golden_model))


def compare_content(native_dx_bytes: bytes, golden_path: Path) -> pl.ContentComparison:
    """Index-for-index nodes/surfs field comparison -- the check `compare_geometry`'s aggregate
    counts cannot do (see `pl.ContentComparison`'s docstring).

    Deliberately compares native's own FULLY ASSEMBLED `.dx` bytes (the same bytes
    `compare_lighting` reads, built by `build_native_lit_dx`) -- NOT the bare
    `build_geometry_bspcsg` model `compare_geometry`/`build_native_model` use. The bare CSG-only
    build never populates `texture_ref`/`i_actor`/`i_light_map` (`i_actor` there is a transient
    index into the CSG brush LIST, not an object ref; texture/light refs are filled in later by
    `unbuilt.assemble_unbuilt`'s rewrite pass and the lighting bake) -- comparing it field-by-field
    against golden's fully-assembled surfs would flag those three fields as "different" on every
    single surf regardless of whether the tree itself is right, a false positive from comparing the
    wrong build stage rather than a real divergence (confirmed live on `DX.dx`, first run of this
    comparison). Covers nodes/surfs/leaves -- the "tree structure" triple this investigation's own
    reporting format is built on; verts/points/vectors are NOT included, see
    `native-materialize-findings.md` for that scope note.

    A surf's two OBJECT-REF fields (`texture_ref`, `i_actor`) are compared by resolved identity, not
    by raw table index: each side's refs go through `pl.resolve_surf_refs` with its OWN
    `object_paths`, so the comparison asks "same texture? same owning brush actor?" rather than "same
    integer position in two tables that are ordered differently by construction". See
    `pl.SURF_OBJECT_REF_FIELDS` for why the raw indices can never agree. Every other surf field, and
    all of nodes/leaves, stays a bit-exact raw comparison."""
    native_path = _temp_dx(native_dx_bytes)
    try:
        native_model = parse_dx_model(native_path)
    finally:
        native_path.unlink(missing_ok=True)
    golden_model = parse_dx_model(golden_path)
    native_exports, native_imports = object_paths(native_dx_bytes)
    golden_exports, golden_imports = object_paths(golden_path.read_bytes())
    native_surfs = pl.resolve_surf_refs(native_model.surfs, export_paths=native_exports,
                                        import_paths=native_imports)
    golden_surfs = pl.resolve_surf_refs(golden_model.surfs, export_paths=golden_exports,
                                        import_paths=golden_imports)
    return pl.ContentComparison(
        nodes=pl.compare_array_content(native_model.nodes, golden_model.nodes, array_name="nodes"),
        surfs=pl.compare_array_content(native_surfs, golden_surfs, array_name="surfs"),
        leaves=pl.compare_array_content(native_model.leaves, golden_model.leaves,
                                        array_name="leaves"))


def build_native_lit_dx(trunk_dir: Path, project_root: Path) -> tuple[bytes, list[str]]:
    """Native's own lit `.dx` bytes -- `build_world_model` + `gather_lights` + `assemble_unbuilt`,
    the same call `light_spotcheck_unatco.py`/`light_spotcheck_wanchai.py` make. `project_root`
    resolves packages/schema for the extracted trunk (its own `_scratch_project`-shaped
    `uedcli.toml`, written by `build_ued_lit_golden.py` during the golden build)."""
    _ensure_imports()
    import os
    os.environ["UEDCLI_PROJECT"] = str(project_root)
    from uedcli import config, packages
    from uedcli import trunk as trunk_mod
    from uedcli.classdefaults import ClassDefaults
    from uedcli.native.materialize import build_world_model, gather_lights, resolve_zone_actors
    from uedcli.native.unbuilt import assemble_unbuilt, substrate_schema
    from spike_classindex import class_index

    project = config.load_project(str(project_root))
    user_config = config.load_user_config()
    pkg_dirs = [str(d) for d in config.composed_search_dirs(project, user_config)]

    level, _ranks = trunk_mod.read_level(trunk_dir)
    ci = class_index()
    resolver = packages.schema_resolver(project, user_config)
    defaults = ClassDefaults(resolver)
    lights = gather_lights(level, defaults=defaults)

    world_model, csg_brushes = build_world_model(level, index=ci, lights=lights)
    dx_bytes, warnings = assemble_unbuilt(
        level, schema=substrate_schema(*pkg_dirs), pkg_dirs=pkg_dirs, world_model=world_model,
        csg_brushes=csg_brushes, zone_actors=resolve_zone_actors(level, world_model),
        light_names=[n for n, *_rest in lights])
    return dx_bytes, list(warnings)


def compare_lighting(native_dx_bytes: bytes, golden_path: Path) -> pl.LightingSummary:
    """`lightparity.py`'s own per-record + shadow-bit comparison, reused as a library: its `main` is
    print-only, so this re-derives the same two headline numbers from its own pure helpers
    (`level_model`/`light_names`/`runs`/`planes`) rather than re-parsing `LightMap` records itself."""
    _ensure_imports()
    import lightparity as LP
    from uedcli import upackage
    from uedcli.native import umodel

    native_path = _temp_dx(native_dx_bytes)
    try:
        npkg, nm = LP.level_model(upackage, umodel, str(native_path))
    finally:
        native_path.unlink(missing_ok=True)
    epkg, em = LP.level_model(upackage, umodel, str(golden_path))

    nnames, enames = LP.light_names(npkg, nm), LP.light_names(epkg, em)
    nruns, eruns = LP.runs(nm, nnames), LP.runs(em, enames)

    # The GOLDEN's own record count is the denominator -- never `min(native, golden)`. A native
    # build that produces FEWER records than the golden (up to and including zero) must show up as
    # a real shortfall, not silently shrink the denominator into a spurious 100%/"FULL" verdict.
    total = len(em.light_map)
    identical = 0
    same_bits = tot_bits = 0
    for k in range(total):
        if k >= len(nm.light_map):
            continue  # native has no record here at all -- correctly NOT counted identical
        a, b = nm.light_map[k], em.light_map[k]
        run_match = nruns[k] == eruns[k]
        grid_match = (a.u_size == b.u_size and a.v_size == b.v_size
                     and pl._bit_exact_eq(a.pan, b.pan)
                     and pl._bit_exact_eq(a.u_scale, b.u_scale)
                     and pl._bit_exact_eq(a.v_scale, b.v_scale))
        pa = LP.planes(nm, a, len(nruns[k]))
        pb = LP.planes(em, b, len(eruns[k]))
        if grid_match and run_match and pa == pb:
            identical += 1
        if (a.u_size, a.v_size, len(nruns[k])) == (b.u_size, b.v_size, len(eruns[k])):
            for x, y in zip(pa, pb):
                same_bits += 8 - bin(x ^ y).count("1")
                tot_bits += 8

    return pl.LightingSummary(total_records=total, identical_records=identical,
                              shadow_bits_same=same_bits, shadow_bits_total=tot_bits)

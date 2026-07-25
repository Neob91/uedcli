//! `uedctl_native` — the PyO3 shim.  THIN by design (§8.2): PyO3 in -> pure-core structs,
//! core out -> `bytes`.  All compute lives in the pure-Rust modules (`cargo test`-able with
//! no Python).  The FFI boundary is the built `UModel` body (§8.1): bulk data, crossed a
//! handful of times, never per-op.
//!
//! Error contract (§8.1): the core returns `Result<_, BuildError>`; this shim maps `Err`
//! (and any caught panic) to a dedicated Python `uedctl_native.BuildError` carrying the
//! offending value — never a bare traceback (repo rule).  Heavy compute runs under
//! `Python::allow_threads` so the multi-second call stays interruptible.

mod bspcsg;
mod bspoptgeom;
mod build;
mod csg;
mod f32;
mod fpoly;
mod light;
mod linecheck;
mod model;
mod model_write;
mod passes;
mod paths;
mod render;
mod zones;

use pyo3::create_exception;
use pyo3::prelude::*;
use pyo3::types::PyBytes;

create_exception!(uedctl_native, BuildError, pyo3::exceptions::PyException);

fn map_err(e: model::BuildError) -> PyErr {
    BuildError::new_err(e.to_string())
}

/// An opaque handle to a built model (the `Built`/handle of §8.1).  Python never sees the
/// node/vert arrays — only counts + the serialized `bytes`.
#[pyclass]
struct Built {
    model: model::Model,
}

#[pymethods]
impl Built {
    #[getter]
    fn num_nodes(&self) -> usize {
        self.model.nodes.len()
    }
    #[getter]
    fn num_surfs(&self) -> usize {
        self.model.surfs.len()
    }
    #[getter]
    fn num_verts(&self) -> usize {
        self.model.verts.len()
    }
    #[getter]
    fn num_points(&self) -> usize {
        self.model.points.len()
    }
}

/// One brush, marshalled as FLAT buffers (§8.1 — never nested PyO3 objects per op):
/// `(verts_flat, poly_sizes, normals_flat, oper, poly_flags, location, rot3x3, prepivot,
/// scale, poly_flags_flat, tex_u_flat, tex_v_flat)`.  `verts_flat` = all poly vertices
/// concatenated as x,y,z; `poly_sizes[i]` = vertex count of poly i; `normals_flat` = per-poly
/// normal x,y,z (may be empty -> computed).  `poly_flags` is the brush-level PolyFlags (ORed onto
/// every poly); `poly_flags_flat` is the PER-POLY PolyFlags (one per poly —
/// Portal/FakeBackdrop/Translucent/… vary per surface; empty -> all 0).  `tex_u_flat`/`tex_v_flat`
/// = the PER-POLY authored texture axes (T3D `TextureU=`/`TextureV=`), one x,y,z triple per poly in
/// the brush's LOCAL space (`FPoly::transform` rotates them into world); an absent axis is (0,0,0),
/// which `alloc_surf`'s `have_u`/`have_v` check treats as "unauthored" -> default in-plane basis.
/// Empty lists -> every poly's axes default.  `origins_flat` = the PER-POLY authored `FPoly::Base`
/// (T3D `Origin=`, the surface's texture ORIGIN — a stored FVector, usually NOT a polygon vertex),
/// one x,y,z triple per poly in the brush's LOCAL space (`FPoly::transform` rotates it into world,
/// then LOOP-1 base-snaps it onto the face plane).  This is the point `bspAddNode` stores as the
/// surf `pBase`, so passing it is load-bearing for `Points`/`pBase` byte-parity: without it the
/// core defaults `base` to `verts[0]` (a CORNER), welding pBase onto a ring vertex instead of
/// emitting the editor's distinct orphan origin point.  Empty list -> keep the `verts[0]` default.
/// It rides bundled with `tex_v_flat` in a nested `(tex_v_flat, origins_flat)` pair because PyO3's
/// `FromPyObject` for tuples tops out at 12 fields; the pair keeps the marshalled arity at 12.
/// `oper`: 1=Add, 2=Subtract, 3=Intersect, 4=Deintersect.
type BrushTuple = (
    Vec<f32>,
    Vec<usize>,
    Vec<f32>,
    i32,
    u32,
    [f32; 3],
    [[f32; 3]; 3],
    [f32; 3],
    [f32; 3],
    Vec<u32>,
    Vec<f32>,
    (Vec<f32>, Vec<f32>, Vec<f32>),
);

fn oper_from_i32(o: i32) -> Result<csg::CsgOper, model::BuildError> {
    match o {
        1 => Ok(csg::CsgOper::Add),
        2 => Ok(csg::CsgOper::Subtract),
        3 => Ok(csg::CsgOper::Intersect),
        4 => Ok(csg::CsgOper::Deintersect),
        _ => Err(model::BuildError(format!(
            "unknown CsgOper {o} (expect 1..=4)"
        ))),
    }
}

fn brush_from_tuple(t: &BrushTuple) -> Result<build::BrushInput, model::BuildError> {
    let (
        verts_flat,
        poly_sizes,
        normals_flat,
        oper,
        poly_flags,
        loc,
        rot,
        prepivot,
        scale,
        poly_flags_flat,
        tex_u_flat,
        (tex_v_flat, origins_flat, vec_xform_flat),
    ) = t;
    // `vec_xform_flat` = 9 floats (row-major `(L⁻¹)ᵀ`, ABrush::BuildCoords VectorXform) for a SCALED
    // brush, else empty.  When present, `bsp_brush_csg` recomputes each face normal covariantly
    // (§92 §43) instead of `calc_normal` over the L-warped world winding.
    let vec_xform: Option<[[f32; 3]; 3]> = if vec_xform_flat.len() == 9 {
        Some([
            [vec_xform_flat[0], vec_xform_flat[1], vec_xform_flat[2]],
            [vec_xform_flat[3], vec_xform_flat[4], vec_xform_flat[5]],
            [vec_xform_flat[6], vec_xform_flat[7], vec_xform_flat[8]],
        ])
    } else {
        None
    };
    let oper = oper_from_i32(*oper)?;
    let mut polys: Vec<fpoly::FPoly> = Vec::new();
    let mut off = 0usize;
    for (pi, &sz) in poly_sizes.iter().enumerate() {
        let mut verts = Vec::with_capacity(sz);
        for _ in 0..sz {
            if (off + 3) > verts_flat.len() {
                return Err(model::BuildError(
                    "verts_flat shorter than poly_sizes".into(),
                ));
            }
            verts.push(model::Vec3::new(
                verts_flat[off],
                verts_flat[off + 1],
                verts_flat[off + 2],
            ));
            off += 3;
        }
        let mut p = fpoly::FPoly::new(verts);
        if normals_flat.len() >= (pi + 1) * 3 {
            p.normal = model::Vec3::new(
                normals_flat[pi * 3],
                normals_flat[pi * 3 + 1],
                normals_flat[pi * 3 + 2],
            );
        }
        // per-poly PolyFlags (Portal/FakeBackdrop/Translucent/…); the brush-level `poly_flags` is
        // ORed on in `csg::bsp_brush_csg`.  Empty list -> 0 (plain surface).
        p.poly_flags = poly_flags_flat.get(pi).copied().unwrap_or(0);
        // per-poly authored texture axes (T3D TextureU/V), local space; `FPoly::transform` rotates
        // them into world.  Absent (empty list, or a (0,0,0) triple) -> alloc_surf synthesizes a
        // default in-plane basis.  These are the world/45°-aligned axes the editor dedups into its
        // (smaller) Vectors pool via bspAddVector — synthesizing instead inflates that pool.
        if tex_u_flat.len() >= (pi + 1) * 3 {
            p.texture_u =
                model::Vec3::new(tex_u_flat[pi * 3], tex_u_flat[pi * 3 + 1], tex_u_flat[pi * 3 + 2]);
        }
        if tex_v_flat.len() >= (pi + 1) * 3 {
            p.texture_v =
                model::Vec3::new(tex_v_flat[pi * 3], tex_v_flat[pi * 3 + 1], tex_v_flat[pi * 3 + 2]);
        }
        // per-poly authored FPoly::Base (T3D Origin), local space; `FPoly::transform` rotates it
        // into world, then LOOP-1 base-snaps it onto the face plane.  Absent (empty list) -> keep
        // the `FPoly::new` default (verts[0]).  This is what `bspAddNode` stores as the surf pBase.
        if origins_flat.len() >= (pi + 1) * 3 {
            p.base = model::Vec3::new(
                origins_flat[pi * 3],
                origins_flat[pi * 3 + 1],
                origins_flat[pi * 3 + 2],
            );
        }
        polys.push(p);
    }
    Ok(build::BrushInput {
        polys,
        oper,
        poly_flags: *poly_flags,
        rot: *rot,
        prepivot: model::Vec3::new(prepivot[0], prepivot[1], prepivot[2]),
        location: model::Vec3::new(loc[0], loc[1], loc[2]),
        scale: model::Vec3::new(scale[0], scale[1], scale[2]),
        vec_xform,
    })
}

/// `build_geometry` (§8.1) — CSG -> BSP -> single-zone.  Runs the REAL leaf-filter + BSP build
/// over the brush list (actor order).  Errors surface as `BuildError` (never a traceback).
#[pyfunction]
fn build_geometry(py: Python<'_>, brushes: Vec<BrushTuple>) -> PyResult<Built> {
    let model = py
        .allow_threads(|| {
            let inputs: Result<Vec<_>, _> = brushes.iter().map(brush_from_tuple).collect();
            let inputs = inputs?;
            build::build_geometry_from_brushes(&inputs)
        })
        .map_err(map_err)?;
    Ok(Built { model })
}

/// `build_geometry_bspcsg` (NEW, OPT-IN) — the incremental `bspBrushCSG` CSG core, driving toward a
/// byte-identical `UModel`.  PARALLEL to `build_geometry`; the default path is unchanged.  Same
/// brush-tuple input.  Errors surface as `BuildError` (never a traceback).
#[pyfunction]
fn build_geometry_bspcsg(py: Python<'_>, brushes: Vec<BrushTuple>) -> PyResult<Built> {
    let model = py
        .allow_threads(|| {
            let inputs: Result<Vec<_>, _> = brushes.iter().map(brush_from_tuple).collect();
            let inputs = inputs?;
            bspcsg::build_geometry_bspcsg(&inputs)
        })
        .map_err(map_err)?;
    Ok(Built { model })
}

/// One result face of `intersect_brushset`, marshalled as FLAT buffers:
/// `(verts_flat, normal, base, tex_u, tex_v, poly_flags, i_link, actor, i_brush_poly)`.
///
/// `verts_flat` = the world-space ring as x,y,z triples.  `base` is the poly's texture ORIGIN
/// (T3D `Origin=`), `tex_u`/`tex_v` its texture axes — all three already in WORLD space.
/// `i_link` is the finalized surf-share representative (an index into the returned list, T3D
/// `Link=`).  `actor` identifies the SOURCE brush: an index into the `brushes` list the caller
/// passed (so the caller can recover the source face's `Texture`/`PanU`/`PanV`, which the CSG core
/// never sees), or `-1` for a Phase-1 face carved off the synthesized BUILDER cube.
/// `i_brush_poly` is the index of the source poly within that brush.
type FaceTuple = (
    Vec<f32>,
    [f32; 3],
    [f32; 3],
    [f32; 3],
    [f32; 3],
    u32,
    i32,
    i32,
    i32,
);

/// `intersect_brushset` — the native `BRUSH FROM INTERSECTION` / `DEINTERSECTION` over an in-tree
/// brush SET (spec `specs/2026-07-24-intersect-deintersect-native-brushset.md`).
///
/// `brushes` is the world CSG set in stdin order (for `intersect`, with the caller's synthesized
/// wrap-subtract cube prepended); `builder` is the synthesized padded-bbox cube whose `oper`
/// (3 = Intersect, 4 = Deintersect) selects the operation.  Returns the result face set.
/// Errors surface as `BuildError` (never a traceback).
#[pyfunction]
fn intersect_brushset(
    py: Python<'_>,
    brushes: Vec<BrushTuple>,
    builder: BrushTuple,
) -> PyResult<Vec<FaceTuple>> {
    let faces = py
        .allow_threads(|| {
            let inputs: Result<Vec<_>, _> = brushes.iter().map(brush_from_tuple).collect();
            let inputs = inputs?;
            let b = brush_from_tuple(&builder)?;
            bspcsg::intersect_brushset(&inputs, &b)
        })
        .map_err(map_err)?;
    Ok(faces
        .iter()
        .map(|p| {
            let mut verts = Vec::with_capacity(p.verts.len() * 3);
            for v in &p.verts {
                verts.push(v.x);
                verts.push(v.y);
                verts.push(v.z);
            }
            (
                verts,
                [p.normal.x, p.normal.y, p.normal.z],
                [p.base.x, p.base.y, p.base.z],
                [p.texture_u.x, p.texture_u.y, p.texture_u.z],
                [p.texture_v.x, p.texture_v.y, p.texture_v.z],
                p.poly_flags,
                p.i_link,
                p.actor,
                p.i_brush_poly,
            )
        })
        .collect())
}

/// `build_carved_box` — the M0 single-subtract stand-in (kept for the dual-serializer §6 gate
/// 5 cross-check against the Python `carved_box_model`).
#[pyfunction]
#[pyo3(signature = (size=512.0, height=256.0))]
fn build_carved_box(py: Python<'_>, size: f32, height: f32) -> PyResult<Built> {
    let model = py.allow_threads(|| build::carved_box(size, height));
    Ok(Built { model })
}

/// `serialize_model` (§8.1) — the built UModel body as `bytes`.  Pinned byte-identical to
/// the Python oracle by §6 gate 5.
#[pyfunction]
fn serialize_model(py: Python<'_>, built: &Built) -> PyResult<Py<PyBytes>> {
    let model = &built.model;
    let bytes = py
        .allow_threads(|| model_write::serialize(model))
        .map_err(map_err)?;
    Ok(PyBytes::new_bound(py, &bytes).unbind())
}

/// `bake_lighting` (§8.1) — the native `LIGHT APPLY` surface-lightmap bake (spike section 20).
/// Fills the built Model's lightmap arrays (`light_map`/`light_bits`/`lights`) and links each
/// lit surf's `iLightMap`, in parallel (rayon).  `lights` is the participating light set as
/// `[(location=[x,y,z], radius_byte), ...]` — the caller filters `LightType != LT_None`.  The
/// `lights` array holds 0-based light INDICES + `-1` NULL terminators (Python assembly rewrites
/// them to export object-refs).  Heavy compute runs under `allow_threads` (interruptible).
#[pyfunction]
fn bake_lighting(py: Python<'_>, built: &mut Built, lights: Vec<([f32; 3], u8)>) -> PyResult<()> {
    let inputs: Vec<light::LightInput> = lights
        .iter()
        .map(|(loc, r)| light::LightInput {
            location: model::Vec3::new(loc[0], loc[1], loc[2]),
            radius: *r,
        })
        .collect();
    let model = &mut built.model;
    py.allow_threads(|| light::bake(model, &inputs))
        .map_err(map_err)?;
    Ok(())
}

/// `build_paths` (§8.1) — reachspec build.  N-5; not yet ported.
#[pyfunction]
fn build_paths(_built: &Built) -> PyResult<()> {
    Err(BuildError::new_err(
        "build_paths is not implemented (N-5: reachspec build)",
    ))
}

/// One flat world-space textured polygon for `render_frame` (native preview, spec §5):
/// `(verts_flat, uv_base, uv_axis_u, uv_axis_v, pan, tex_index)`.  `verts_flat` = the ring
/// as x,y,z triples; the UV frame is in texel units (Python computes it from the SOURCE
/// poly's authored axes); `tex_index` indexes the texture table, `-1` = flat default grey.
type RenderPolyTuple = (Vec<f32>, [f32; 3], [f32; 3], [f32; 3], [f32; 2], i32);

/// `render_frame` — the `--native` preview rasterizer (spec §5).  Flat world-space
/// polygons + a texture table (`(w, h, rgb_bytes)` mip0) + a camera BASIS
/// (`(location, forward, right, up, fov_deg)` — Python single-sources the FRotator
/// convention; Rust never converts angles) -> `width*height*3` RGB bytes.
#[pyfunction]
fn render_frame(
    py: Python<'_>,
    polys: Vec<RenderPolyTuple>,
    textures: Vec<(u32, u32, Vec<u8>)>,
    camera: ([f32; 3], [f32; 3], [f32; 3], [f32; 3], f32),
    size: (u32, u32),
) -> PyResult<Py<PyBytes>> {
    let (width, height) = size;
    if width == 0 || height == 0 || width > 16384 || height > 16384 {
        return Err(BuildError::new_err(format!(
            "render size {width}x{height} out of range (1..=16384)"
        )));
    }
    for (i, (w, h, data)) in textures.iter().enumerate() {
        if (w * h * 3) as usize != data.len() {
            return Err(BuildError::new_err(format!(
                "texture {i}: {w}x{h} needs {} RGB bytes, got {}",
                w * h * 3,
                data.len()
            )));
        }
        if *w == 0 || *h == 0 {
            return Err(BuildError::new_err(format!(
                "texture {i}: zero-sized ({w}x{h})"
            )));
        }
    }
    let rpolys: Vec<render::RenderPoly> = polys
        .into_iter()
        .map(|(verts_flat, base, au, av, pan, tex_index)| {
            let verts = verts_flat
                .chunks_exact(3)
                .map(|c| model::Vec3::new(c[0], c[1], c[2]))
                .collect();
            render::RenderPoly {
                verts,
                uv_base: model::Vec3::new(base[0], base[1], base[2]),
                uv_axis_u: model::Vec3::new(au[0], au[1], au[2]),
                uv_axis_v: model::Vec3::new(av[0], av[1], av[2]),
                pan,
                tex_index,
            }
        })
        .collect();
    let rtex: Vec<render::RenderTexture> = textures
        .into_iter()
        .map(|(w, h, data)| render::RenderTexture { w, h, data })
        .collect();
    let (loc, fwd, right, up, fov) = camera;
    let cam = render::Camera {
        location: model::Vec3::new(loc[0], loc[1], loc[2]),
        forward: model::Vec3::new(fwd[0], fwd[1], fwd[2]),
        right: model::Vec3::new(right[0], right[1], right[2]),
        up: model::Vec3::new(up[0], up[1], up[2]),
        fov_deg: fov,
    };
    let img = py.allow_threads(|| render::render(&rpolys, &rtex, &cam, width, height));
    Ok(PyBytes::new_bound(py, &img).unbind())
}

/// `opt_geom_from_arrays` — TEST/VALIDATION entry for the standalone `bspOptGeom` port
/// (`bspoptgeom.rs`).  Reconstructs the minimal `Model` fields the pass touches from flat arrays,
/// runs the full `bsp_opt_geom`, and returns the mutated results, so the offline harness
/// (`optgeom_validate.py`) can assert byte-exact reproduction of a parsed golden `Model`'s
/// `FVert.iSide` + `NumSharedSides` (and that pass-1 inserts nothing on an already-optimized model).
/// Inputs: `points` = 3·P f32; per-node `plane` = 4·N f32, `ivertpool/numverts/ifront/iback/iplane`
/// = N i32; per-vert `ivertex` = V i32.  Returns `(vert_ivertex, vert_iside, node_ivertpool,
/// node_numverts, num_shared_sides)`.
#[pyfunction]
#[allow(clippy::type_complexity, clippy::too_many_arguments)]
fn opt_geom_from_arrays(
    py: Python<'_>,
    points: Vec<f32>,
    node_plane: Vec<f32>,
    node_ivertpool: Vec<i32>,
    node_numverts: Vec<i32>,
    node_ifront: Vec<i32>,
    node_iback: Vec<i32>,
    node_iplane: Vec<i32>,
    vert_ivertex: Vec<i32>,
) -> PyResult<(Vec<i32>, Vec<i32>, Vec<i32>, Vec<i32>, i32)> {
    let n_nodes = node_ivertpool.len();
    if node_numverts.len() != n_nodes
        || node_ifront.len() != n_nodes
        || node_iback.len() != n_nodes
        || node_iplane.len() != n_nodes
        || node_plane.len() != n_nodes * 4
    {
        return Err(BuildError::new_err(
            "opt_geom_from_arrays: node array length mismatch",
        ));
    }
    if points.len() % 3 != 0 {
        return Err(BuildError::new_err(
            "opt_geom_from_arrays: points not a multiple of 3",
        ));
    }
    let (verts_out, iside_out, pool_out, nv_out, nss) = py.allow_threads(move || {
        let mut model = model::Model::default();
        model.points = points
            .chunks_exact(3)
            .map(|c| model::Vec3::new(c[0], c[1], c[2]))
            .collect();
        model.verts = vert_ivertex
            .iter()
            .map(|&iv| model::BspVert {
                i_vertex: iv,
                i_side: -1,
            })
            .collect();
        model.nodes = (0..n_nodes)
            .map(|i| {
                let pl = model::Plane {
                    x: node_plane[i * 4],
                    y: node_plane[i * 4 + 1],
                    z: node_plane[i * 4 + 2],
                    w: node_plane[i * 4 + 3],
                };
                let mut nd = model::BspNode::leaf(pl, 0, node_ivertpool[i], node_numverts[i]);
                nd.i_front = node_ifront[i];
                nd.i_back = node_iback[i];
                nd.i_plane = node_iplane[i];
                nd
            })
            .collect();
        bspoptgeom::bsp_opt_geom(&mut model);
        let verts_out: Vec<i32> = model.verts.iter().map(|v| v.i_vertex).collect();
        let iside_out: Vec<i32> = model.verts.iter().map(|v| v.i_side).collect();
        let pool_out: Vec<i32> = model.nodes.iter().map(|n| n.i_vert_pool).collect();
        let nv_out: Vec<i32> = model.nodes.iter().map(|n| n.num_vertices).collect();
        (
            verts_out,
            iside_out,
            pool_out,
            nv_out,
            model.num_shared_sides,
        )
    });
    Ok((verts_out, iside_out, pool_out, nv_out, nss))
}

#[pymodule]
fn uedctl_native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("BuildError", m.py().get_type_bound::<BuildError>())?;
    m.add_class::<Built>()?;
    m.add_function(wrap_pyfunction!(build_geometry, m)?)?;
    m.add_function(wrap_pyfunction!(build_geometry_bspcsg, m)?)?;
    m.add_function(wrap_pyfunction!(intersect_brushset, m)?)?;
    m.add_function(wrap_pyfunction!(build_carved_box, m)?)?;
    m.add_function(wrap_pyfunction!(serialize_model, m)?)?;
    m.add_function(wrap_pyfunction!(bake_lighting, m)?)?;
    m.add_function(wrap_pyfunction!(build_paths, m)?)?;
    m.add_function(wrap_pyfunction!(render_frame, m)?)?;
    m.add_function(wrap_pyfunction!(opt_geom_from_arrays, m)?)?;
    Ok(())
}

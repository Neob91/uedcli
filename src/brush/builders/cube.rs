//! `brush build cube` geometry: builds a cube brush actor as T3D text. No CLI knowledge -- see
//! `cli::cube` for argument parsing and scope (which flags are handled natively vs. proxied).

use rust_decimal::Decimal;

use super::base::{self, CsgOperation, Solidity};
use crate::core::emit::{clean, emit_actor_t3d, format_float_like_python};
use crate::core::model::{FinalizedPolygon, Polygon, Vector3D};

fn build_cube_faces(width: f64, breadth: f64, height: f64) -> Vec<Polygon> {
    let (half_width, half_breadth, half_height) = (width / 2.0, breadth / 2.0, height / 2.0);
    let corner =
        |sx: f64, sy: f64, sz: f64| Vector3D::new(sx * half_width, sy * half_breadth, sz * half_height);
    let faces: [([Vector3D; 4], Vector3D); 6] = [
        (
            [corner(1., -1., -1.), corner(1., 1., -1.), corner(1., 1., 1.), corner(1., -1., 1.)],
            Vector3D::new(1., 0., 0.),
        ),
        (
            [corner(-1., 1., -1.), corner(-1., -1., -1.), corner(-1., -1., 1.), corner(-1., 1., 1.)],
            Vector3D::new(-1., 0., 0.),
        ),
        (
            [corner(1., 1., -1.), corner(-1., 1., -1.), corner(-1., 1., 1.), corner(1., 1., 1.)],
            Vector3D::new(0., 1., 0.),
        ),
        (
            [corner(-1., -1., -1.), corner(1., -1., -1.), corner(1., -1., 1.), corner(-1., -1., 1.)],
            Vector3D::new(0., -1., 0.),
        ),
        (
            [corner(-1., -1., 1.), corner(1., -1., 1.), corner(1., 1., 1.), corner(-1., 1., 1.)],
            Vector3D::new(0., 0., 1.),
        ),
        (
            [corner(-1., 1., -1.), corner(1., 1., -1.), corner(1., -1., -1.), corner(-1., -1., -1.)],
            Vector3D::new(0., 0., -1.),
        ),
    ];
    faces.into_iter().map(|(ring, outward)| base::build_polygon(ring.to_vec(), outward)).collect()
}

fn check_positive(flag: &str, value: f64) -> Result<(), String> {
    if !(value.is_finite() && value > 0.0) {
        return Err(format!(
            "brush build cube: {flag} must be greater than 0, got {}",
            format_float_like_python(value)
        ));
    }
    Ok(())
}

pub fn build_cube(
    width: f64,
    breadth: f64,
    height: f64,
    at: (Decimal, Decimal, Decimal),
    base_name: String,
    csg: CsgOperation,
    solidity: Solidity,
) -> Result<String, String> {
    // _check_positive_build_dims checks in the table's declared order: width, breadth, height.
    check_positive("--width", width)?;
    check_positive("--breadth", breadth)?;
    check_positive("--height", height)?;

    // Pre-clean once, mirroring make_brush_actor's own finalize pass (see
    // core::emit::format_vertex's doc) -- emit_actor_t3d/format_location/format_vertex apply
    // their own clean() on top, giving the correct TWO total applications for vertices and
    // Location.
    let polygons: Vec<FinalizedPolygon> = build_cube_faces(width, breadth, height)
        .iter()
        .map(base::finalize_polygon)
        .collect::<Result<_, _>>()?;
    let location = (clean(at.0)?, clean(at.1)?, clean(at.2)?);

    let model_name = format!("Model_{base_name}");
    emit_actor_t3d(&base_name, &model_name, csg.as_t3d(), solidity.poly_flags(), location, &polygons)
}

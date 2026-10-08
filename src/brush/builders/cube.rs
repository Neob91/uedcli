//! `brush build cube` geometry: builds a cube brush actor as T3D text. No CLI knowledge -- see
//! `cli::cube` for argument parsing and scope (which flags are handled natively vs. proxied).

use rust_decimal::Decimal;

use super::base::{self, CsgOperation, Solidity};
use crate::core::emit::{clean, decimal_from_f64, emit_brush_t3d, format_float_for_error};
use crate::core::model::{Polygon, Vector3D};

fn build_cube_faces(width: Decimal, breadth: Decimal, height: Decimal) -> Vec<Polygon> {
    let two = Decimal::from(2);
    let (half_width, half_breadth, half_height) = (width / two, breadth / two, height / two);
    let one = Decimal::ONE;
    let zero = Decimal::ZERO;
    let neg_one = -one;
    let corner = |sx: Decimal, sy: Decimal, sz: Decimal| {
        Vector3D::new(sx * half_width, sy * half_breadth, sz * half_height)
    };
    let faces: [([Vector3D; 4], Vector3D); 6] = [
        (
            [
                corner(one, neg_one, neg_one),
                corner(one, one, neg_one),
                corner(one, one, one),
                corner(one, neg_one, one),
            ],
            Vector3D::new(one, zero, zero),
        ),
        (
            [
                corner(neg_one, one, neg_one),
                corner(neg_one, neg_one, neg_one),
                corner(neg_one, neg_one, one),
                corner(neg_one, one, one),
            ],
            Vector3D::new(neg_one, zero, zero),
        ),
        (
            [
                corner(one, one, neg_one),
                corner(neg_one, one, neg_one),
                corner(neg_one, one, one),
                corner(one, one, one),
            ],
            Vector3D::new(zero, one, zero),
        ),
        (
            [
                corner(neg_one, neg_one, neg_one),
                corner(one, neg_one, neg_one),
                corner(one, neg_one, one),
                corner(neg_one, neg_one, one),
            ],
            Vector3D::new(zero, neg_one, zero),
        ),
        (
            [
                corner(neg_one, neg_one, one),
                corner(one, neg_one, one),
                corner(one, one, one),
                corner(neg_one, one, one),
            ],
            Vector3D::new(zero, zero, one),
        ),
        (
            [
                corner(neg_one, one, neg_one),
                corner(one, one, neg_one),
                corner(one, neg_one, neg_one),
                corner(neg_one, neg_one, neg_one),
            ],
            Vector3D::new(zero, zero, neg_one),
        ),
    ];
    faces.into_iter().map(|(ring, outward)| base::build_polygon(ring.to_vec(), outward)).collect()
}

fn check_positive(flag: &str, value: f64) -> Result<(), String> {
    if !(value.is_finite() && value > 0.0) {
        return Err(format!(
            "brush build cube: {flag} must be greater than 0, got {}",
            format_float_for_error(value)
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

    // Decimal from here on -- every Vector3D this builds is exact from construction, no float
    // noise to clean up later.
    let width = decimal_from_f64(width)?;
    let breadth = decimal_from_f64(breadth)?;
    let height = decimal_from_f64(height)?;

    // Pre-clean vertices once (see core::emit::format_vertex's doc); emit_brush_t3d applies its
    // own clean() on top, giving the correct TWO total applications for vertices and Location.
    let polygons: Vec<Polygon> = build_cube_faces(width, breadth, height)
        .iter()
        .map(base::clean_polygon)
        .collect::<Result<_, _>>()?;
    let location = Vector3D::new(clean(at.0)?, clean(at.1)?, clean(at.2)?);

    let model_name = format!("Model_{base_name}");
    emit_brush_t3d(&base_name, &model_name, csg.as_t3d(), solidity.poly_flags(), location, &polygons)
}

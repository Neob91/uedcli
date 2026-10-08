//! `brush build cube` geometry: builds a cube brush actor as T3D text. No CLI knowledge -- see
//! `cli::cube` for argument parsing and scope (which flags are handled natively vs. proxied).

use rust_decimal::Decimal;

use super::base::{self, CsgOperation, Solidity};
use crate::core::emit::{clean_decimal, emit_brush_t3d};
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

// Decimal has no NaN/Infinity -- a value that failed to parse as one never reaches here (the
// CLI layer's parse failure proxies instead), so only the sign needs checking.
fn check_positive(param: &str, value: Decimal) -> Result<(), String> {
    if value <= Decimal::ZERO {
        let text = value.to_string();
        let text = if text.contains('.') { text } else { format!("{text}.0") };
        return Err(format!("brush build cube: {param} must be greater than 0, got {text}"));
    }
    Ok(())
}

pub fn build_cube(
    width: Decimal,
    breadth: Decimal,
    height: Decimal,
    at: Vector3D,
    base_name: String,
    csg: CsgOperation,
    solidity: Solidity,
) -> Result<String, String> {
    // _check_positive_build_dims checks in the table's declared order: width, breadth, height.
    check_positive("--width", width)?;
    check_positive("--breadth", breadth)?;
    check_positive("--height", height)?;

    // Pre-clean vertices once (see core::emit::format_vertex's doc); emit_brush_t3d applies its
    // own clean_decimal() on top, giving the correct TWO total applications for vertices and
    // Location.
    let polygons: Vec<Polygon> = build_cube_faces(width, breadth, height)
        .iter()
        .map(base::clean_polygon)
        .collect::<Result<_, _>>()?;
    let location = Vector3D::new(clean_decimal(at.x)?, clean_decimal(at.y)?, clean_decimal(at.z)?);

    let model_name = format!("Model_{base_name}");
    emit_brush_t3d(&base_name, &model_name, csg.as_t3d(), solidity.poly_flags(), location, &polygons)
}

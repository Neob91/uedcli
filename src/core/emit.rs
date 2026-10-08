//! Decimal-exact T3D number formatting, plus assembling a Polygon/Brush/Actor block. Shared
//! across uedcli's Rust verbs, not brush-specific.

use rust_decimal::prelude::ToPrimitive;
use rust_decimal::{Decimal, RoundingStrategy};
use std::str::FromStr;

use super::model::{Polygon, Vector3D};

const CLEAN_EPS: &str = "0.001";

pub fn quantize6(d: Decimal) -> Result<Decimal, String> {
    Ok(d.round_dp_with_strategy(6, RoundingStrategy::MidpointAwayFromZero))
}

// A coordinate within CLEAN_EPS of an integer is float noise and snaps to it; anything further
// is a genuine fraction, kept at 6dp (T3D's precision).
pub fn clean_decimal(d: Decimal) -> Result<Decimal, String> {
    let nearest = d.round_dp_with_strategy(0, RoundingStrategy::MidpointAwayFromZero);
    let eps = Decimal::from_str(CLEAN_EPS).unwrap();
    if (d - nearest).abs() <= eps {
        return Ok(nearest);
    }
    quantize6(d)
}

// clean_decimal() is NOT idempotent right at the CLEAN_EPS boundary: quantize6's rounding can
// move a value's distance from the nearest integer from just above the threshold to at-or-below
// it, so calling this once vs. twice on the same raw input can give different results. Vertices
// are cleaned once by their caller before reaching here (see
// brush::builders::base::clean_polygon), so this call is their SECOND application;
// Origin/Normal/TextureU/TextureV skip that pre-clean, so this is their only application. Getting
// the count wrong is a real output difference, not a style choice.
pub fn format_vertex(d: Decimal) -> Result<String, String> {
    let d = clean_decimal(d)?;
    let sign = if d < Decimal::ZERO { "-" } else { "+" };
    let quantized = quantize6(d.abs())?;
    let integer_part = quantized.trunc();
    let fraction = quantized - integer_part;
    let integer_part_as_i64: i64 = integer_part
        .to_i64()
        .ok_or_else(|| format!("coordinate {d} is out of emittable range"))?;
    let fraction_text = fraction.to_string();
    let fraction_digits = fraction_text.split('.').nth(1).unwrap_or("");
    let fraction_digits = format!("{fraction_digits:0<6}");
    Ok(format!("{sign}{integer_part_as_i64:05}.{fraction_digits}"))
}

/// The caller must pass an already-once-cleaned Decimal, so this function's own
/// `clean_decimal()` call is the correct second application -- see `format_vertex`'s doc.
pub fn format_location(value: Decimal) -> Result<String, String> {
    let d = clean_decimal(value)?;
    Ok(format!("{d:.6}"))
}

fn format_vector_line(kind: &str, vector: Vector3D) -> Result<String, String> {
    Ok(format!(
        "         {kind:<8} {},{},{}",
        format_vertex(vector.x)?,
        format_vertex(vector.y)?,
        format_vertex(vector.z)?
    ))
}

pub fn emit_polygon(polygon: &Polygon) -> Result<String, String> {
    let mut out = vec!["         Begin Polygon Item=OUTSIDE".to_string()];
    out.push(format_vector_line("Origin", polygon.origin)?);
    out.push(format_vector_line("Normal", polygon.normal)?);
    out.push(format_vector_line("TextureU", polygon.texture_u)?);
    out.push(format_vector_line("TextureV", polygon.texture_v)?);
    for vertex in &polygon.vertices {
        out.push(format_vector_line("Vertex", *vertex)?);
    }
    out.push("         End Polygon".to_string());
    Ok(out.join("\n"))
}

pub fn emit_brush(model_name: &str, polygons: &[Polygon]) -> Result<String, String> {
    let mut out =
        vec![format!("    Begin Brush Name={model_name}"), "       Begin PolyList".to_string()];
    for polygon in polygons {
        out.push(emit_polygon(polygon)?);
    }
    out.push("       End PolyList".to_string());
    out.push("    End Brush".to_string());
    Ok(out.join("\n"))
}

// TODO: CsgOper/PolyFlags/Location/MainScale/PostScale are hardcoded here instead of going
// through a generic per-Actor property mechanism -- revisit once uedcli has one (see
// dev/epics/refactor.md for where the architecture is headed).
//
// location must already be cleaned once by the caller -- see format_vertex's doc.
pub fn emit_brush_t3d(
    name: &str,
    model_name: &str,
    csg_op: &str,
    poly_flags: u32,
    location: Vector3D,
    polygons: &[Polygon],
) -> Result<String, String> {
    let mut out = vec![format!("Begin Actor Class=Engine.Brush Name={name}")];
    out.push(format!("    CsgOper={csg_op}"));
    if poly_flags != 0 {
        out.push(format!("    PolyFlags={poly_flags}"));
    }
    out.push(format!(
        "    Location=(X={},Y={},Z={})",
        format_location(location.x)?,
        format_location(location.y)?,
        format_location(location.z)?
    ));
    // Identity scale + the editor's own default shear axis.
    out.push("    MainScale=(SheerAxis=SHEER_ZX)".to_string());
    out.push("    PostScale=(SheerAxis=SHEER_ZX)".to_string());
    out.push(emit_brush(model_name, polygons)?);
    out.push(format!("    Brush=Model'MyLevel.{model_name}'"));
    out.push(format!("    Name=\"{name}\""));
    out.push("End Actor".to_string());
    Ok(out.join("\n") + "\n")
}

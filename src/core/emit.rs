//! Decimal-exact T3D number formatting, plus assembling a Polygon/Brush/Actor block. Shared
//! across uedcli's Rust verbs, not brush-specific.

use rust_decimal::prelude::ToPrimitive;
use rust_decimal::{Decimal, RoundingStrategy};
use std::str::FromStr;

use super::model::{FinalizedPolygon, Vector3D};

const CLEAN_EPS: &str = "0.001";

/// Formats a float for an error message: lowercase `nan`/`inf`, always a decimal point.
pub fn format_float_like_python(v: f64) -> String {
    if v.is_nan() {
        return "nan".to_string();
    }
    if v.is_infinite() {
        return if v > 0.0 { "inf".to_string() } else { "-inf".to_string() };
    }
    let s = format!("{v}");
    if s.contains('.') || s.contains('e') {
        s
    } else {
        format!("{s}.0")
    }
}

// str(value) first, so a float's binary tail never enters Decimal directly -- 0.1 as an f64
// isn't exactly 0.1, and Decimal::from(0.1_f64) would carry that noise forever.
//
// TODO: at a pathologically tiny/huge finite magnitude, the decimal string can exceed
// rust_decimal's ~28-29 digit capacity, failing for a value that IS actually finite -- reported
// below as "not a finite number", which mislabels it as a precision/magnitude problem. Only
// reachable far beyond the real engine's +-32768 world.
pub fn decimal_from_f64(value: f64) -> Result<Decimal, String> {
    if !value.is_finite() {
        return Err(format!("coordinate is not a finite number: {}", format_float_like_python(value)));
    }
    Decimal::from_str(&format_float_like_python(value))
        .map_err(|_| format!("coordinate is not a finite number: {value}"))
}

// TODO: format_vertex's to_i64() below narrows the accepted range further still (i64 tops out
// around 9.2e18, well short of the ~1e22 digit limit this allows). Not expected to matter for any
// realistic cube dimension.
pub fn quantize6(d: Decimal) -> Result<Decimal, String> {
    Ok(d.round_dp_with_strategy(6, RoundingStrategy::MidpointAwayFromZero))
}

// A coordinate within CLEAN_EPS of an integer is float noise and snaps to it; anything further
// is a genuine fraction, kept at 6dp (T3D's precision).
pub fn clean(d: Decimal) -> Result<Decimal, String> {
    let nearest = d.round_dp_with_strategy(0, RoundingStrategy::MidpointAwayFromZero);
    let eps = Decimal::from_str(CLEAN_EPS).unwrap();
    if (d - nearest).abs() <= eps {
        return Ok(nearest);
    }
    quantize6(d)
}

// clean() is NOT idempotent right at the CLEAN_EPS boundary: quantize6's rounding can move a
// value's distance from the nearest integer from just above the threshold to at-or-below it, so
// calling this once vs. twice on the same raw input can give different results. Vertices and
// Location are cleaned once by their caller before reaching here, so this call is their SECOND
// application; Origin/Normal/TextureU/TextureV skip that pre-clean, so `format_vertex_from_f64`
// is their only application. Getting the count wrong is a real output difference, not a style
// choice.
pub fn format_vertex(d: Decimal) -> Result<String, String> {
    let d = clean(d)?;
    let sign = if d < Decimal::ZERO { "-" } else { "+" };
    let quantized = quantize6(d.abs())?;
    let integer_part = quantized.trunc();
    let fraction = quantized - integer_part;
    let integer_part_as_i64: i64 = integer_part
        .to_i64()
        .ok_or_else(|| format!("coordinate {d} is out of emittable range"))?;
    let fraction_text = fraction.to_string(); // "0.XXXXXX" -- quantize6 fixed the scale to 6
    let fraction_digits = fraction_text.split('.').nth(1).unwrap_or("");
    let fraction_digits = format!("{fraction_digits:0<6}");
    Ok(format!("{sign}{integer_part_as_i64:05}.{fraction_digits}"))
}

/// A raw (never pre-cleaned) geometry float's ONE `clean()` application -- see
/// `format_vertex`'s doc.
pub fn format_vertex_from_f64(value: f64) -> Result<String, String> {
    format_vertex(decimal_from_f64(value)?)
}

/// The caller must pass an already-once-cleaned Decimal, so this function's own `clean()` call
/// is the correct second application -- see `format_vertex`'s doc.
pub fn format_location(value: Decimal) -> Result<String, String> {
    let mut d = clean(value)?;
    if d.is_zero() {
        d = Decimal::ZERO;
    }
    Ok(format!("{d:.6}"))
}

fn format_vector_line_from_f64(kind: &str, vector: Vector3D) -> Result<String, String> {
    Ok(format!(
        "         {kind:<8} {},{},{}",
        format_vertex_from_f64(vector.x)?,
        format_vertex_from_f64(vector.y)?,
        format_vertex_from_f64(vector.z)?
    ))
}

fn format_vector_line_from_decimal(
    kind: &str,
    vector: (Decimal, Decimal, Decimal),
) -> Result<String, String> {
    Ok(format!(
        "         {kind:<8} {},{},{}",
        format_vertex(vector.0)?,
        format_vertex(vector.1)?,
        format_vertex(vector.2)?
    ))
}

pub fn emit_polygon(polygon: &FinalizedPolygon) -> Result<String, String> {
    let mut out = vec!["         Begin Polygon Item=OUTSIDE".to_string()];
    out.push(format_vector_line_from_f64("Origin", polygon.origin)?);
    out.push(format_vector_line_from_f64("Normal", polygon.normal)?);
    out.push(format_vector_line_from_f64("TextureU", polygon.texture_u)?);
    out.push(format_vector_line_from_f64("TextureV", polygon.texture_v)?);
    for vertex in &polygon.vertices {
        out.push(format_vector_line_from_decimal("Vertex", *vertex)?);
    }
    out.push("         End Polygon".to_string());
    Ok(out.join("\n"))
}

pub fn emit_brush(model_name: &str, polygons: &[FinalizedPolygon]) -> Result<String, String> {
    let mut out =
        vec![format!("    Begin Brush Name={model_name}"), "       Begin PolyList".to_string()];
    for polygon in polygons {
        out.push(emit_polygon(polygon)?);
    }
    out.push("       End PolyList".to_string());
    out.push("    End Brush".to_string());
    Ok(out.join("\n"))
}

// location must already be cleaned once by the caller -- see format_vertex's doc.
pub fn emit_actor_t3d(
    name: &str,
    model_name: &str,
    csg_op: &str,
    poly_flags: u32,
    location: (Decimal, Decimal, Decimal),
    polygons: &[FinalizedPolygon],
) -> Result<String, String> {
    let mut out = vec![format!("Begin Actor Class=Engine.Brush Name={name}")];
    out.push(format!("    CsgOper={csg_op}"));
    if poly_flags != 0 {
        out.push(format!("    PolyFlags={poly_flags}"));
    }
    out.push(format!(
        "    Location=(X={},Y={},Z={})",
        format_location(location.0)?,
        format_location(location.1)?,
        format_location(location.2)?
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

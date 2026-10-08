//! Decimal-exact T3D number formatting, plus assembling a Polygon/Brush/Actor block. Shared
//! across uedcli's Rust verbs, not brush-specific.

use rust_decimal::prelude::ToPrimitive;
use rust_decimal::{Decimal, RoundingStrategy};
use std::str::FromStr;

use super::model::{FinalizedPolygon, Vector3D};

const CLEAN_EPS: &str = "0.001";

/// Mirrors Python's `str(float)` for an f-string substitution, which is what emit.py's error
/// messages embed verbatim.
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

/// Mirrors emit.py's `_to_decimal` + `_guard` for a raw float input: `str(value)` first (so a
/// float's binary tail never enters Decimal directly), then finite-checked.
///
/// TODO(port): for a pathologically tiny/huge finite magnitude, Rust's float Display (unlike
/// Python's str(), which switches to scientific notation) can produce a decimal string too long
/// for rust_decimal's ~28-29 digit capacity, failing `Decimal::from_str` for a value that IS
/// actually finite -- reported below as "not a finite number", which old/'s equivalent failure
/// (quantize6's InvalidOperation) correctly labels as a precision/magnitude problem instead. Only
/// reachable at magnitudes far beyond the real engine's +-32768 world.
pub fn decimal_from_f64(value: f64) -> Result<Decimal, String> {
    if !value.is_finite() {
        return Err(format!("coordinate is not a finite number: {}", format_float_like_python(value)));
    }
    Decimal::from_str(&format_float_like_python(value))
        .map_err(|_| format!("coordinate is not a finite number: {value}"))
}

/// Mirrors emit.py's `quantize6`.
///
/// TODO(port): doesn't replicate Python's InvalidOperation/28-significant-digit overflow check
/// exactly, and `format_vertex`'s `to_i64()` below narrows the accepted range further still (i64
/// tops out around 9.2e18, well short of the ~1e22 wall quantize6's own digit limit allows) --
/// so a value far beyond the real engine's +-32768 world that old/ would still (uselessly) emit,
/// this rejects instead. Not expected to diverge for any realistic cube dimension.
pub fn quantize6(d: Decimal) -> Result<Decimal, String> {
    Ok(d.round_dp_with_strategy(6, RoundingStrategy::MidpointAwayFromZero))
}

/// Mirrors emit.py's `clean`, operating on an already-Decimal value (the caller does the
/// float->Decimal step via `decimal_from_f64` first, or passes an already-Decimal `--at`
/// component straight through -- same as `_guard`'s `isinstance(value, Decimal)` fast path).
pub fn clean(d: Decimal) -> Result<Decimal, String> {
    let nearest = d.round_dp_with_strategy(0, RoundingStrategy::MidpointAwayFromZero);
    let eps = Decimal::from_str(CLEAN_EPS).unwrap();
    if (d - nearest).abs() <= eps {
        return Ok(nearest);
    }
    quantize6(d)
}

/// Mirrors emit.py's `fmt_vertex` EXACTLY: it always applies `clean()` to its input once,
/// whatever already happened to that input before this call. `clean()` is NOT idempotent right
/// at the CLEAN_EPS boundary -- quantize6's 6-dp rounding can move a value's distance from the
/// nearest integer from just above CLEAN_EPS to at-or-below it, so a SECOND clean() pass can snap
/// a value the first pass left fractional. Callers that already pre-cleaned their input once
/// (vertices, Location) get clean() applied TWICE overall by calling this; callers that never
/// pre-clean (a face's Origin/Normal/TextureU/TextureV) get it ONCE via `format_vertex_from_f64`.
/// Getting this distinction wrong is a real, byte-level divergence from old/ -- not just a style
/// choice.
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

/// Mirrors emit.py's `fmt_loc`. The caller must pass an already-once-cleaned Decimal (mirroring
/// old/'s own pre-clean pass over a Location) so this function's own `clean()` call is the
/// correct SECOND application -- see `format_vertex`'s doc.
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
    // Every cube face carries Item=OUTSIDE (builders.py's cube() passes item="OUTSIDE" to every
    // _face call), no Texture= (texture is always None in scope), no Flags= (flags always 0),
    // no Pan line (cube faces never set one).
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

/// Mirrors builders.py's SOLIDITY_FLAGS/CSG_OPER and emit.py's emit_actor, for the one Actor
/// shape make_brush_actor produces with mover_class=None and group=None (--mover-class and the
/// --prop-only Group are both out of scope here). `location` must already be once-cleaned (see
/// `format_location`'s doc) -- callers pre-clean it the same way make_brush_actor does.
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
    // MainScale/PostScale: transform.IDENTITY (unit scale, zero sheer rate, the editor's own
    // default SheerAxis=SHEER_ZX) -- emit_fscale's output for that value is this fixed string;
    // --mover-class, --rotate and --prop (the only things that could change it) are out of scope.
    out.push("    MainScale=(SheerAxis=SHEER_ZX)".to_string());
    out.push("    PostScale=(SheerAxis=SHEER_ZX)".to_string());
    out.push(emit_brush(model_name, polygons)?);
    out.push(format!("    Brush=Model'MyLevel.{model_name}'"));
    out.push(format!("    Name=\"{name}\""));
    out.push("End Actor".to_string());
    Ok(out.join("\n") + "\n")
}

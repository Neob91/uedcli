//! Decimal-exact T3D number formatting -- mirrors old/uedcli/emit.py's numeric pipeline. Generic
//! over any future verb emitting T3D, not just brush builders.

use rust_decimal::prelude::*;
use rust_decimal::Decimal;
use std::str::FromStr;

const CLEAN_EPS: &str = "0.001";

/// Mirrors Python's `str(float)` for an f-string substitution, which is what emit.py's error
/// messages embed verbatim.
pub fn py_float_repr(v: f64) -> String {
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
        return Err(format!("coordinate is not a finite number: {}", py_float_repr(value)));
    }
    Decimal::from_str(&py_float_repr(value))
        .map_err(|_| format!("coordinate is not a finite number: {value}"))
}

/// Mirrors emit.py's `quantize6`.
///
/// TODO(port): doesn't replicate Python's InvalidOperation/28-significant-digit overflow check
/// exactly, and `fmt_vertex`'s `to_i64()` below narrows the accepted range further still (i64
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
/// pre-clean (a face's Origin/Normal/TextureU/TextureV) get it ONCE via `fmt_vertex_f64`. Getting
/// this distinction wrong is a real, byte-level divergence from old/ -- not just a style choice.
pub fn fmt_vertex(d: Decimal) -> Result<String, String> {
    let d = clean(d)?;
    let sign = if d < Decimal::ZERO { "-" } else { "+" };
    let q = quantize6(d.abs())?;
    let int_part = q.trunc();
    let frac = q - int_part;
    let int_part_i: i64 =
        int_part.to_i64().ok_or_else(|| format!("coordinate {d} is out of emittable range"))?;
    let frac_str = frac.to_string(); // "0.XXXXXX" -- quantize6 fixed the scale to 6
    let frac_digits = frac_str.split('.').nth(1).unwrap_or("");
    let frac_digits = format!("{frac_digits:0<6}");
    Ok(format!("{sign}{int_part_i:05}.{frac_digits}"))
}

/// A raw (never pre-cleaned) geometry float's ONE `clean()` application -- see `fmt_vertex`'s doc.
pub fn fmt_vertex_f64(value: f64) -> Result<String, String> {
    fmt_vertex(decimal_from_f64(value)?)
}

/// Mirrors emit.py's `fmt_loc`. The caller must pass an already-once-cleaned Decimal (mirroring
/// old/'s own pre-clean pass over a Location) so this function's own `clean()` call is the
/// correct SECOND application -- see `fmt_vertex`'s doc.
pub fn fmt_loc(value: Decimal) -> Result<String, String> {
    let mut d = clean(value)?;
    if d.is_zero() {
        d = Decimal::ZERO;
    }
    Ok(format!("{d:.6}"))
}

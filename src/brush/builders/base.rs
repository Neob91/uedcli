//! Shared across every `brush build <shape>` -- the generic polygon-builder and old/'s custom
//! argv-value-ambiguity rule. Mirrors old/uedcli/builders.py's module-level `_face` and
//! old/uedcli/cli/parsers/_arguments.py's `_CoordArgumentParser`.

use rust_decimal::Decimal;
use std::str::FromStr;

use crate::core::emit::{clean, decimal_from_f64};
use crate::core::math::vectors;
use crate::core::model::{FinalizedPolygon, Polygon, Vector3D};

#[derive(Clone, Copy, clap::ValueEnum)]
pub enum CsgOperation {
    Add,
    Subtract,
}

impl CsgOperation {
    pub fn as_t3d(self) -> &'static str {
        match self {
            CsgOperation::Add => "CSG_Add",
            CsgOperation::Subtract => "CSG_Subtract",
        }
    }
}

#[derive(Clone, Copy, clap::ValueEnum)]
pub enum Solidity {
    Solid,
    Semisolid,
    Nonsolid,
}

impl Solidity {
    pub fn poly_flags(self) -> u32 {
        match self {
            Solidity::Solid => 0,
            Solidity::Semisolid => 0x0000_0020,
            Solidity::Nonsolid => 0x0000_0008,
        }
    }
}

pub fn finalize_polygon(polygon: &Polygon) -> Result<FinalizedPolygon, String> {
    let mut vertices = Vec::with_capacity(polygon.vertices.len());
    for vertex in &polygon.vertices {
        vertices.push((
            clean(decimal_from_f64(vertex.x)?)?,
            clean(decimal_from_f64(vertex.y)?)?,
            clean(decimal_from_f64(vertex.z)?)?,
        ));
    }
    Ok(FinalizedPolygon {
        vertices,
        origin: polygon.origin,
        normal: polygon.normal,
        texture_u: polygon.texture_u,
        texture_v: polygon.texture_v,
    })
}

/// Builds a `Polygon` from a boundary vertex ring + a rough outward direction. Mirrors
/// builders.py's `_face`.
pub fn build_polygon(ring: Vec<Vector3D>, outward: Vector3D) -> Polygon {
    // builders.py's _face also runs _dedup_ring and raises GeometryError on <3 distinct verts or
    // a degenerate (zero-area) face -- never reachable for cube's 4 fixed, well-separated
    // corners (guaranteed distinct whenever width/breadth/height > 0, already enforced by the
    // positive-dimension guard before this runs), so not replicated.
    let newell_normal = vectors::compute_newell_normal(&ring);
    let outward_normalized = vectors::normalize_vector(outward);
    // NOTE: cube's 6 hand-authored rings are already wound to match their declared `outward`, so
    // this branch never actually triggers for cube -- unverified by this shape's tests. The next
    // shape whose outward vector is only approximate (cylinder/cone's side quads) is this
    // translation's first real exercise; re-check against _face's Python original then.
    let ring = if vectors::dot(newell_normal, outward_normalized) < 0.0 {
        let mut reversed = ring;
        reversed.reverse();
        reversed
    } else {
        ring
    };
    let (texture_u, texture_v) = vectors::compute_texture_basis(outward_normalized);
    Polygon {
        origin: vectors::compute_centroid(&ring),
        normal: outward_normalized,
        texture_u,
        texture_v,
        vertices: ring,
    }
}

pub fn parse_at(text: &str) -> Option<(Decimal, Decimal, Decimal)> {
    let parts: Vec<&str> = text.split(',').map(|part| part.trim()).collect();
    if parts.len() != 3 {
        return None;
    }
    let decimals: Vec<Decimal> =
        parts.iter().map(|part| Decimal::from_str(part).ok()).collect::<Option<_>>()?;
    Some((decimals[0], decimals[1], decimals[2]))
}

/// Mirrors old/'s custom `_COORD_TOKEN` regex (`cli/parsers/_arguments.py`):
/// `^[-+]?[0-9.]+(,[-+]?[0-9.]+)*$` -- a signed number, or several comma-joined, digits/dots
/// only (not a "valid number" check: "1..2" matches this exactly as loosely as the Python regex
/// does -- whether it's a REAL number is a separate, later question for parse_at/f64::parse).
pub fn is_coordinate_token(text: &str) -> bool {
    !text.is_empty()
        && text.split(',').all(|part| {
            let digits = part.strip_prefix(['-', '+']).unwrap_or(part);
            !digits.is_empty() && digits.chars().all(|c| c.is_ascii_digit() || c == '.')
        })
}

/// Whether old/'s custom parser would refuse to consume `token` as a flag's value (and instead
/// error "expected one argument"). A `_COORD_TOKEN`-shaped token is ALWAYS a value, overriding
/// the usual rule -- see `is_coordinate_token`'s doc and this crate's callers for why
/// ("-10.5,20,0" must be accepted, "-1e5,0,0" and "-x" must not).
///
/// Anything else starting with `-` is treated as option-like here, which is conservative rather
/// than exactly equivalent to real argparse's `_parse_optional`: that function also treats a
/// bare single-character token (just `"-"`) and any token containing a space as a value, neither
/// of which this replicates. Both are safe to get "wrong" in this direction -- returning `true`
/// (option-like) here only means the caller's `try_build_*` returns `None` and proxies to
/// old/bin/uedcli, which reproduces old/'s real behavior byte-for-byte regardless of why the
/// fallback triggered. The only direction that would be unsafe (returning `false` for something
/// old/ actually rejects) can't happen: `is_coordinate_token` is a faithful match for
/// `_COORD_TOKEN`, which is checked first and short-circuits real `_parse_optional` before any of
/// the branches this function doesn't replicate ever run.
pub fn looks_like_option(token: &str) -> bool {
    !is_coordinate_token(token) && token.starts_with('-')
}

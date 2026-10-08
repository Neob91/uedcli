//! Shared across every `brush build <shape>` -- a Polygon/FinalizedPolygon pair, the generic
//! face-builder, T3D assembly for one brush Actor, and old/'s custom argv-value-ambiguity rule.
//! Mirrors old/uedcli/builders.py's module-level `_face`/`make_brush_actor` and
//! old/uedcli/cli/parsers/_arguments.py's `_CoordArgumentParser`.

use rust_decimal::Decimal;
use std::str::FromStr;

use crate::core::emit::{clean, decimal_from_f64, fmt_loc, fmt_vertex, fmt_vertex_f64};
use crate::core::math::{centroid, dot, newell_normal, normalize_vector, texture_basis};
use crate::core::types::Vec3;

/// One face of a brush, in raw geometry floats -- the ring may carry sub-grid float noise;
/// nothing here is Decimal-exact yet.
pub struct Polygon {
    pub vertices: Vec<Vec3>,
    pub origin: Vec3,
    /// Face normal -- advisory; the editor recomputes it from vertex winding on import.
    pub normal: Vec3,
    /// In-plane texture-U basis vector (not a texture reference -- this project's "core" scope
    /// has no per-face texture yet; see brush_build.rs's module doc for what's deferred).
    pub texture_u: Vec3,
    /// In-plane texture-V basis vector, perpendicular to `texture_u` within the face's plane.
    pub texture_v: Vec3,
}

/// A `Polygon` with its vertices pre-cleaned to Decimal exactly once -- mirrors
/// builders.py's `make_brush_actor`, which pre-cleans ONLY `p.vertices` (not
/// Origin/Normal/TextureU/TextureV) in its finalize pass. See `core::emit::fmt_vertex`'s doc
/// comment for why this matters: `clean()` is NOT idempotent at its rounding-epsilon boundary, so
/// applying it once (Origin/Normal/TextureU/TextureV) vs. twice (vertices: once here, again
/// inside `fmt_vertex` at emit time, same as old/'s own double application) can produce different
/// bytes for a value that lands in that narrow window.
pub struct FinalizedPolygon {
    pub vertices: Vec<(Decimal, Decimal, Decimal)>,
    pub origin: Vec3,
    pub normal: Vec3,
    pub texture_u: Vec3,
    pub texture_v: Vec3,
}

pub fn finalize_polygon(p: &Polygon) -> Result<FinalizedPolygon, String> {
    let mut vertices = Vec::with_capacity(p.vertices.len());
    for v in &p.vertices {
        vertices.push((
            clean(decimal_from_f64(v.x)?)?,
            clean(decimal_from_f64(v.y)?)?,
            clean(decimal_from_f64(v.z)?)?,
        ));
    }
    Ok(FinalizedPolygon {
        vertices,
        origin: p.origin,
        normal: p.normal,
        texture_u: p.texture_u,
        texture_v: p.texture_v,
    })
}

/// Builds a `Polygon` from a boundary vertex ring + a rough outward direction. Mirrors
/// builders.py's `_face`.
pub fn face(ring: Vec<Vec3>, outward: Vec3) -> Polygon {
    // builders.py's _face also runs _dedup_ring and raises GeometryError on <3 distinct verts or
    // a degenerate (zero-area) face -- never reachable for cube's 4 fixed, well-separated
    // corners (guaranteed distinct whenever width/breadth/height > 0, already enforced by the
    // positive-dimension guard before this runs), so not replicated.
    let newell = newell_normal(&ring);
    let out = normalize_vector(outward);
    // NOTE: cube's 6 hand-authored rings are already wound to match their declared `outward`, so
    // this branch never actually triggers for cube -- unverified by this shape's tests. The next
    // shape whose outward vector is only approximate (cylinder/cone's side quads) is this
    // translation's first real exercise; re-check against _face's Python original then.
    let ring = if dot(newell, out) < 0.0 {
        let mut r = ring;
        r.reverse();
        r
    } else {
        ring
    };
    let (texture_u, texture_v) = texture_basis(out);
    Polygon { origin: centroid(&ring), normal: out, texture_u, texture_v, vertices: ring }
}

fn vec_line_f64(kind: &str, v: Vec3) -> Result<String, String> {
    Ok(format!(
        "         {kind:<8} {},{},{}",
        fmt_vertex_f64(v.x)?,
        fmt_vertex_f64(v.y)?,
        fmt_vertex_f64(v.z)?
    ))
}

fn vec_line_decimal(kind: &str, v: (Decimal, Decimal, Decimal)) -> Result<String, String> {
    Ok(format!("         {kind:<8} {},{},{}", fmt_vertex(v.0)?, fmt_vertex(v.1)?, fmt_vertex(v.2)?))
}

pub fn emit_polygon(p: &FinalizedPolygon) -> Result<String, String> {
    // Every cube face carries Item=OUTSIDE (builders.py's cube() passes item="OUTSIDE" to every
    // _face call), no Texture= (texture is always None in scope), no Flags= (flags always 0),
    // no Pan line (cube faces never set one).
    let mut out = vec!["         Begin Polygon Item=OUTSIDE".to_string()];
    out.push(vec_line_f64("Origin", p.origin)?);
    out.push(vec_line_f64("Normal", p.normal)?);
    out.push(vec_line_f64("TextureU", p.texture_u)?);
    out.push(vec_line_f64("TextureV", p.texture_v)?);
    for v in &p.vertices {
        out.push(vec_line_decimal("Vertex", *v)?);
    }
    out.push("         End Polygon".to_string());
    Ok(out.join("\n"))
}

pub fn emit_brush(model_name: &str, polygons: &[FinalizedPolygon]) -> Result<String, String> {
    let mut out =
        vec![format!("    Begin Brush Name={model_name}"), "       Begin PolyList".to_string()];
    for p in polygons {
        out.push(emit_polygon(p)?);
    }
    out.push("       End PolyList".to_string());
    out.push("    End Brush".to_string());
    Ok(out.join("\n"))
}

/// Mirrors builders.py's SOLIDITY_FLAGS/CSG_OPER and emit.py's emit_actor, for the one Actor
/// shape make_brush_actor produces with mover_class=None and group=None (--mover-class and the
/// --prop-only Group are both out of scope here). `location` must already be once-cleaned (see
/// `core::emit::fmt_loc`'s doc) -- callers pre-clean it the same way make_brush_actor does.
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
        fmt_loc(location.0)?,
        fmt_loc(location.1)?,
        fmt_loc(location.2)?
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

pub fn parse_at(s: &str) -> Option<(Decimal, Decimal, Decimal)> {
    let parts: Vec<&str> = s.split(',').map(|p| p.trim()).collect();
    if parts.len() != 3 {
        return None;
    }
    let d: Vec<Decimal> = parts.iter().map(|p| Decimal::from_str(p).ok()).collect::<Option<_>>()?;
    Some((d[0], d[1], d[2]))
}

/// Mirrors old/'s custom `_COORD_TOKEN` regex (`cli/parsers/_arguments.py`):
/// `^[-+]?[0-9.]+(,[-+]?[0-9.]+)*$` -- a signed number, or several comma-joined, digits/dots
/// only (not a "valid number" check: "1..2" matches this exactly as loosely as the Python regex
/// does -- whether it's a REAL number is a separate, later question for parse_at/f64::parse).
pub fn is_coord_token(s: &str) -> bool {
    !s.is_empty()
        && s.split(',').all(|part| {
            let digits = part.strip_prefix(['-', '+']).unwrap_or(part);
            !digits.is_empty() && digits.chars().all(|c| c.is_ascii_digit() || c == '.')
        })
}

/// Whether old/'s custom parser would refuse to consume `token` as a flag's value (and instead
/// error "expected one argument"). A `_COORD_TOKEN`-shaped token is ALWAYS a value, overriding
/// the usual rule -- see `is_coord_token`'s doc and this crate's callers for why ("-10.5,20,0"
/// must be accepted, "-1e5,0,0" and "-x" must not).
///
/// Anything else starting with `-` is treated as option-like here, which is conservative rather
/// than exactly equivalent to real argparse's `_parse_optional`: that function also treats a
/// bare single-character token (just `"-"`) and any token containing a space as a value, neither
/// of which this replicates. Both are safe to get "wrong" in this direction -- returning `true`
/// (option-like) here only means the caller's `try_build_*` returns `None` and proxies to
/// old/bin/uedcli, which reproduces old/'s real behavior byte-for-byte regardless of why the
/// fallback triggered. The only direction that would be unsafe (returning `false` for something
/// old/ actually rejects) can't happen: `is_coord_token` is a faithful match for `_COORD_TOKEN`,
/// which is checked first and short-circuits real `_parse_optional` before any of the branches
/// this function doesn't replicate ever run.
pub fn looks_like_option(token: &str) -> bool {
    !is_coord_token(token) && token.starts_with('-')
}

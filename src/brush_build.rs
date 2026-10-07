//! `brush build cube` -- the first ported verb (dev/epics/refactor.md's "first vertical slice").
//! Mirrors old/uedcli/cli/commands/brush/build.py + old/uedcli/builders.py::cube +
//! old/uedcli/emit.py for this ONE shape, at reduced scope (owner-approved, 2026-10-07):
//!
//! Handled: --width --breadth --height --at --base-name --csg --solidity.
//!
//! NOT handled -- any of these present falls back to the old/bin/uedcli proxy, unchanged:
//!   TODO(port): --prop        schema-validated property editing (propedit.rs doesn't exist yet)
//!   TODO(port): --texture     per-face texture ref + existence validation against the asset catalog
//!   TODO(port): --mover-class Mover variant (no CsgOper, base pose only)
//!   TODO(port): --rotate      absolute Rotation set + off-grid warning
//!   TODO(port): --folder/--label   `// uedcli-folder:`/`// uedcli-labels:` org carriers
//! TODO(port): old/'s run() ALSO unconditionally calls ingest.validate_ingest_actors, which
//! resolves the project's class index and validates Engine.Brush exists there -- skipped
//! entirely here. Engine.Brush always exists on every real substrate, so this only diverges from
//! old/ on a malformed/missing project, which old/ would reject and this does not.
//! Known formatting gap: error messages for a pathologically large/small dimension (>1e16 or
//! <1e-4ish) may not byte-match old/'s Python repr (which switches to scientific notation at
//! different thresholds than Rust's float Display) -- never hit by `quantize6`-accepted geometry,
//! only possibly by the positive-dimension guard's own error text.

use rust_decimal::prelude::*;
use rust_decimal::Decimal;
use std::str::FromStr;

type Vec3 = (f64, f64, f64);

// ---- vector algebra (mirrors builders.py's module-level helpers) ------------------------------

fn dot(a: Vec3, b: Vec3) -> f64 {
    a.0 * b.0 + a.1 * b.1 + a.2 * b.2
}
fn cross(a: Vec3, b: Vec3) -> Vec3 {
    (a.1 * b.2 - a.2 * b.1, a.2 * b.0 - a.0 * b.2, a.0 * b.1 - a.1 * b.0)
}
fn sub(a: Vec3, b: Vec3) -> Vec3 {
    (a.0 - b.0, a.1 - b.1, a.2 - b.2)
}
fn mul(a: Vec3, s: f64) -> Vec3 {
    (a.0 * s, a.1 * s, a.2 * s)
}
fn vlen(a: Vec3) -> f64 {
    dot(a, a).sqrt()
}
fn normalize(a: Vec3) -> Vec3 {
    // builders.py's _normalize raises GeometryError on a zero-length input -- never reachable for
    // cube's fixed axis-aligned outward vectors (always unit length already), so not replicated.
    let n = vlen(a);
    (a.0 / n, a.1 / n, a.2 / n)
}
fn centroid(ring: &[Vec3]) -> Vec3 {
    let n = ring.len() as f64;
    let sx: f64 = ring.iter().map(|p| p.0).sum();
    let sy: f64 = ring.iter().map(|p| p.1).sum();
    let sz: f64 = ring.iter().map(|p| p.2).sum();
    (sx / n, sy / n, sz / n)
}
fn newell(ring: &[Vec3]) -> Vec3 {
    let mut n = (0.0, 0.0, 0.0);
    let m = ring.len();
    for i in 0..m {
        let a = ring[i];
        let b = ring[(i + 1) % m];
        n.0 += (a.1 - b.1) * (a.2 + b.2);
        n.1 += (a.2 - b.2) * (a.0 + b.0);
        n.2 += (a.0 - b.0) * (a.1 + b.1);
    }
    n
}
fn tex_basis(normal: Vec3) -> (Vec3, Vec3) {
    // Ties resolve to the LOWEST axis index -- Rust's min_by, like Python's min(), returns the
    // first minimal element on a tie (builders.py's _tex_basis docstring: this is load-bearing).
    let comps = [normal.0, normal.1, normal.2];
    let ax = (0..3).min_by(|&i, &j| comps[i].abs().partial_cmp(&comps[j].abs()).unwrap()).unwrap();
    let mut seed = [0.0, 0.0, 0.0];
    seed[ax] = 1.0;
    let seed = (seed[0], seed[1], seed[2]);
    let u = normalize(sub(seed, mul(normal, dot(seed, normal))));
    let v = cross(normal, u);
    (u, v)
}

struct Poly {
    vertices: Vec<Vec3>,
    origin: Vec3,
    normal: Vec3,
    texture_u: Vec3,
    texture_v: Vec3,
}

/// A Poly with its vertices pre-cleaned to Decimal exactly once -- mirrors builders.py's
/// make_brush_actor, which pre-cleans ONLY `p.vertices` (not Origin/Normal/TextureU/TextureV) in
/// its finalize pass. See `fmt_vertex`'s doc comment for why this matters: `clean()` is NOT
/// idempotent at the CLEAN_EPS boundary, so applying it once (Origin/Normal/TextureU/TextureV, via
/// `fmt_vertex_f64`) vs. twice (vertices: once here, again inside `fmt_vertex` at emit time, same
/// as old/'s own double application) can produce different bytes for a value that lands in that
/// narrow window.
struct FinalizedPoly {
    vertices: Vec<(Decimal, Decimal, Decimal)>,
    origin: Vec3,
    normal: Vec3,
    texture_u: Vec3,
    texture_v: Vec3,
}

fn finalize_poly(p: &Poly) -> Result<FinalizedPoly, String> {
    let mut vertices = Vec::with_capacity(p.vertices.len());
    for v in &p.vertices {
        vertices.push((
            clean(decimal_from_f64(v.0)?)?,
            clean(decimal_from_f64(v.1)?)?,
            clean(decimal_from_f64(v.2)?)?,
        ));
    }
    Ok(FinalizedPoly {
        vertices,
        origin: p.origin,
        normal: p.normal,
        texture_u: p.texture_u,
        texture_v: p.texture_v,
    })
}

fn face(ring: Vec<Vec3>, outward: Vec3) -> Poly {
    // builders.py's _face also runs _dedup_ring and raises GeometryError on <3 distinct verts or
    // a degenerate (zero-area) face -- never reachable for cube's 4 fixed, well-separated
    // corners (guaranteed distinct whenever width/breadth/height > 0, already enforced by the
    // positive-dimension guard before this runs), so not replicated.
    let nw = newell(&ring);
    let out = normalize(outward);
    // NOTE: cube's 6 hand-authored rings are already wound to match their declared `outward`, so
    // this branch never actually triggers for cube -- unverified by this shape's tests. The next
    // shape whose outward vector is only approximate (cylinder/cone's side quads) is this
    // translation's first real exercise; re-check against _face's Python original then.
    let ring = if dot(nw, out) < 0.0 {
        let mut r = ring;
        r.reverse();
        r
    } else {
        ring
    };
    let (u, v) = tex_basis(out);
    Poly { origin: centroid(&ring), normal: out, texture_u: u, texture_v: v, vertices: ring }
}

fn cube_faces(width: f64, breadth: f64, height: f64) -> Vec<Poly> {
    let (hx, hy, hz) = (width / 2.0, breadth / 2.0, height / 2.0);
    let c = |sx: f64, sy: f64, sz: f64| (sx * hx, sy * hy, sz * hz);
    let faces: [([Vec3; 4], Vec3); 6] = [
        ([c(1., -1., -1.), c(1., 1., -1.), c(1., 1., 1.), c(1., -1., 1.)], (1., 0., 0.)),
        ([c(-1., 1., -1.), c(-1., -1., -1.), c(-1., -1., 1.), c(-1., 1., 1.)], (-1., 0., 0.)),
        ([c(1., 1., -1.), c(-1., 1., -1.), c(-1., 1., 1.), c(1., 1., 1.)], (0., 1., 0.)),
        ([c(-1., -1., -1.), c(1., -1., -1.), c(1., -1., 1.), c(-1., -1., 1.)], (0., -1., 0.)),
        ([c(-1., -1., 1.), c(1., -1., 1.), c(1., 1., 1.), c(-1., 1., 1.)], (0., 0., 1.)),
        ([c(-1., 1., -1.), c(1., 1., -1.), c(1., -1., -1.), c(-1., -1., -1.)], (0., 0., -1.)),
    ];
    faces.into_iter().map(|(ring, outward)| face(ring.to_vec(), outward)).collect()
}

// ---- Decimal finalize + T3D text formatting (mirrors emit.py) ---------------------------------

const CLEAN_EPS: &str = "0.001";

/// Mirrors Python's `str(float)` for an f-string substitution, which is what emit.py's error
/// messages and `_check_positive_build_dims`'s message embed verbatim.
fn py_float_repr(v: f64) -> String {
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
fn decimal_from_f64(value: f64) -> Result<Decimal, String> {
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
fn quantize6(d: Decimal) -> Result<Decimal, String> {
    Ok(d.round_dp_with_strategy(6, RoundingStrategy::MidpointAwayFromZero))
}

/// Mirrors emit.py's `clean`, operating on an already-Decimal value (the caller does the
/// float->Decimal step via `decimal_from_f64` first, or passes an already-Decimal `--at`
/// component straight through -- same as `_guard`'s `isinstance(value, Decimal)` fast path).
fn clean(d: Decimal) -> Result<Decimal, String> {
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
/// a value the first pass left fractional. old/'s make_brush_actor pre-cleans `p.vertices` and
/// `location` once before emit, so those get clean() applied TWICE overall (pass 1 there, pass 2
/// here); Origin/Normal/TextureU/TextureV are never pre-cleaned, so they get exactly ONE
/// application. Call sites must preserve this distinction -- see `fmt_vertex_f64` (one pass) vs.
/// `FinalizedPoly`/`fmt_loc`'s callers, which pre-clean once before reaching here (two passes).
fn fmt_vertex(d: Decimal) -> Result<String, String> {
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

/// For Origin/Normal/TextureU/TextureV: a raw geometry float, never pre-cleaned (make_brush_actor
/// doesn't touch these), so this is the value's ONE clean() application overall.
fn fmt_vertex_f64(value: f64) -> Result<String, String> {
    fmt_vertex(decimal_from_f64(value)?)
}

/// Mirrors emit.py's `fmt_loc`, for the Location triple. Callers must pass an already-once-cleaned
/// Decimal (mirroring make_brush_actor's `location=(clean(...), ...)` pre-clean pass) so this
/// function's own `clean()` call is the correct SECOND application -- see `fmt_vertex`'s doc.
fn fmt_loc(value: Decimal) -> Result<String, String> {
    let mut d = clean(value)?;
    if d.is_zero() {
        d = Decimal::ZERO;
    }
    Ok(format!("{d:.6}"))
}

fn vec_line_f64(kind: &str, v: Vec3) -> Result<String, String> {
    Ok(format!(
        "         {kind:<8} {},{},{}",
        fmt_vertex_f64(v.0)?,
        fmt_vertex_f64(v.1)?,
        fmt_vertex_f64(v.2)?
    ))
}

fn vec_line_decimal(kind: &str, v: (Decimal, Decimal, Decimal)) -> Result<String, String> {
    Ok(format!("         {kind:<8} {},{},{}", fmt_vertex(v.0)?, fmt_vertex(v.1)?, fmt_vertex(v.2)?))
}

fn emit_polygon(p: &FinalizedPoly) -> Result<String, String> {
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

fn emit_brush(model_name: &str, polys: &[FinalizedPoly]) -> Result<String, String> {
    let mut out = vec![format!("    Begin Brush Name={model_name}"), "       Begin PolyList".to_string()];
    for p in polys {
        out.push(emit_polygon(p)?);
    }
    out.push("       End PolyList".to_string());
    out.push("    End Brush".to_string());
    Ok(out.join("\n"))
}

/// Mirrors builders.py's SOLIDITY_FLAGS/CSG_OPER and emit.py's emit_actor, for the one Actor
/// shape make_brush_actor produces with mover_class=None and group=None (--mover-class and the
/// --prop-only Group are both out of scope here). `location` must already be once-cleaned (see
/// `fmt_loc`'s doc) -- callers pre-clean it the same way make_brush_actor does.
fn emit_actor_t3d(
    name: &str,
    model_name: &str,
    csg_op: &str,
    poly_flags: u32,
    location: (Decimal, Decimal, Decimal),
    polys: &[FinalizedPoly],
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
    out.push(emit_brush(model_name, polys)?);
    out.push(format!("    Brush=Model'MyLevel.{model_name}'"));
    out.push(format!("    Name=\"{name}\""));
    out.push("End Actor".to_string());
    Ok(out.join("\n") + "\n")
}

fn check_positive(flag: &str, value: f64) -> Result<(), String> {
    if !(value.is_finite() && value > 0.0) {
        return Err(format!(
            "brush build cube: {flag} must be greater than 0, got {}",
            py_float_repr(value)
        ));
    }
    Ok(())
}

fn build_cube(
    width: f64,
    breadth: f64,
    height: f64,
    at: Option<(Decimal, Decimal, Decimal)>,
    base_name: Option<String>,
    csg: Option<String>,
    solidity: Option<String>,
) -> Result<String, String> {
    // _check_positive_build_dims checks in the table's declared order: width, breadth, height.
    check_positive("--width", width)?;
    check_positive("--breadth", breadth)?;
    check_positive("--height", height)?;

    // Pre-clean once, mirroring make_brush_actor's own finalize pass (see fmt_vertex's doc) --
    // emit_actor_t3d/fmt_loc/fmt_vertex apply their own clean() on top, giving the correct TWO
    // total applications for vertices and Location.
    let polys: Vec<FinalizedPoly> =
        cube_faces(width, breadth, height).iter().map(finalize_poly).collect::<Result<_, _>>()?;
    let (ax, ay, az) = at.unwrap_or((Decimal::ZERO, Decimal::ZERO, Decimal::ZERO));
    let location = (clean(ax)?, clean(ay)?, clean(az)?);

    let name = base_name.unwrap_or_else(|| "Cube".to_string());
    let model_name = format!("Model_{name}");
    let csg_op = match csg.as_deref().unwrap_or("add") {
        "add" => "CSG_Add",
        "subtract" => "CSG_Subtract",
        _ => unreachable!("validated at parse time"),
    };
    let poly_flags: u32 = match solidity.as_deref().unwrap_or("solid") {
        "solid" => 0,
        "semisolid" => 0x0000_0020,
        "nonsolid" => 0x0000_0008,
        _ => unreachable!("validated at parse time"),
    };

    emit_actor_t3d(&name, &model_name, csg_op, poly_flags, location, &polys)
}

// ---- argv parsing / dispatch entry point -------------------------------------------------------

fn parse_at(s: &str) -> Option<(Decimal, Decimal, Decimal)> {
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
fn is_coord_token(s: &str) -> bool {
    !s.is_empty()
        && s.split(',').all(|part| {
            let digits = part.strip_prefix(['-', '+']).unwrap_or(part);
            !digits.is_empty() && digits.chars().all(|c| c.is_ascii_digit() || c == '.')
        })
}

/// Whether old/'s custom parser would refuse to consume `token` as a flag's value (and instead
/// error "expected one argument"). A `_COORD_TOKEN`-shaped token is ALWAYS a value, overriding
/// the usual rule -- see `is_coord_token`'s doc and the call site's comment for why ("-10.5,20,0"
/// must be accepted, "-1e5,0,0" and "-x" must not). Anything else starting with `-` is
/// option-like, matching plain argparse's `_parse_optional` for every other case this parser's
/// small flag set can produce (no abbreviation-matching edge cases to worry about here).
fn looks_like_option(token: &str) -> bool {
    !is_coord_token(token) && token.starts_with('-')
}

/// `None`: not our case (unrecognized flag, missing/invalid value, an excluded flag, --project,
/// -h/--help) -- the caller must proxy to old/bin/uedcli, unchanged. `Some(Ok(t3d))`: emit to
/// stdout, exit 0. `Some(Err(message))`: emit to stderr, exit 2 -- a real, in-scope failure
/// (the positive-dimension guard), not a parse ambiguity.
pub fn try_build_cube(args: &[String]) -> Option<Result<String, String>> {
    if args.len() < 3 || args[0] != "brush" || args[1] != "build" || args[2] != "cube" {
        return None;
    }
    let rest = &args[3..];

    const EXCLUDED: &[&str] =
        &["--prop", "--texture", "--mover-class", "--rotate", "--folder", "--label"];

    let mut width = None;
    let mut breadth = None;
    let mut height = None;
    let mut at = None;
    let mut base_name = None;
    let mut csg = None;
    let mut solidity = None;

    let mut i = 0;
    while i < rest.len() {
        let tok = rest[i].as_str();
        if tok == "--project" || tok == "-h" || tok == "--help" || EXCLUDED.contains(&tok) {
            return None;
        }
        i += 1;
        let val = rest.get(i)?.as_str(); // every supported flag takes a value; missing one -> proxy
        // argparse refuses to consume a token that LOOKS LIKE an option as a flag's VALUE
        // (`--base-name --prop` is "expected one argument", not base_name="--prop") -- mirror
        // that here, not just rely on each flag's own value validation, since e.g. --base-name
        // accepts any string and would otherwise silently accept one of the EXCLUDED flags'
        // spellings as a literal base name instead of proxying to get argparse's real error.
        //
        // The real rule is NOT "starts with --": old/'s parser is a custom _CoordArgumentParser
        // (cli/parsers/_arguments.py) whose _parse_optional override ALWAYS treats a token
        // matching _COORD_TOKEN (`^[-+]?[0-9.]+(,[-+]?[0-9.]+)*$` -- a signed number or
        // comma-joined coordinate, digits/dots only) as a VALUE, for every flag, specifically so
        // `--at -32,-32,32` works without the awkward `--at=-32,-32,32` form. Anything else
        // starting with `-` (a bare short flag, an unregistered long flag, a value containing a
        // letter like scientific notation "-1e5") is option-like and gets the usual rejection.
        // Verified against the real parser directly, not just its docstring: `--at -10.5,20,0`
        // and `--base-name -5` ARE accepted by old/ (coord-token-shaped); `--at -1e5,0,0` and
        // `--base-name -x` are NOT (not coord-token-shaped, so "expected one argument").
        if looks_like_option(val) {
            return None;
        }
        match tok {
            "--width" => width = Some(val.parse::<f64>().ok()?),
            "--breadth" => breadth = Some(val.parse::<f64>().ok()?),
            "--height" => height = Some(val.parse::<f64>().ok()?),
            "--at" => at = Some(parse_at(val)?),
            "--base-name" => base_name = Some(val.to_string()),
            "--csg" => {
                if val != "add" && val != "subtract" {
                    return None;
                }
                csg = Some(val.to_string());
            }
            "--solidity" => {
                if val != "solid" && val != "semisolid" && val != "nonsolid" {
                    return None;
                }
                solidity = Some(val.to_string());
            }
            _ => return None, // unrecognized flag -- proxy, don't guess
        }
        i += 1;
    }

    Some(build_cube(width?, breadth?, height?, at, base_name, csg, solidity))
}

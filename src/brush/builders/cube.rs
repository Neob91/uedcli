//! `brush build cube` -- the first ported verb (dev/epics/refactor.md's "first vertical slice").
//! Mirrors old/uedcli/cli/commands/brush/build.py + old/uedcli/builders.py::cube for this ONE
//! shape, at reduced scope (owner-approved, 2026-10-07):
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

use rust_decimal::Decimal;

use super::base::{self, FinalizedPolygon, Polygon};
use crate::core::emit::{clean, py_float_repr};
use crate::core::types::Vec3;

fn cube_faces(width: f64, breadth: f64, height: f64) -> Vec<Polygon> {
    let (hx, hy, hz) = (width / 2.0, breadth / 2.0, height / 2.0);
    let c = |sx: f64, sy: f64, sz: f64| Vec3::new(sx * hx, sy * hy, sz * hz);
    let faces: [([Vec3; 4], Vec3); 6] = [
        ([c(1., -1., -1.), c(1., 1., -1.), c(1., 1., 1.), c(1., -1., 1.)], Vec3::new(1., 0., 0.)),
        ([c(-1., 1., -1.), c(-1., -1., -1.), c(-1., -1., 1.), c(-1., 1., 1.)], Vec3::new(-1., 0., 0.)),
        ([c(1., 1., -1.), c(-1., 1., -1.), c(-1., 1., 1.), c(1., 1., 1.)], Vec3::new(0., 1., 0.)),
        ([c(-1., -1., -1.), c(1., -1., -1.), c(1., -1., 1.), c(-1., -1., 1.)], Vec3::new(0., -1., 0.)),
        ([c(-1., -1., 1.), c(1., -1., 1.), c(1., 1., 1.), c(-1., 1., 1.)], Vec3::new(0., 0., 1.)),
        ([c(-1., 1., -1.), c(1., 1., -1.), c(1., -1., -1.), c(-1., -1., -1.)], Vec3::new(0., 0., -1.)),
    ];
    faces.into_iter().map(|(ring, outward)| base::face(ring.to_vec(), outward)).collect()
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

    // Pre-clean once, mirroring make_brush_actor's own finalize pass (see core::emit::fmt_vertex's
    // doc) -- emit_actor_t3d/fmt_loc/fmt_vertex apply their own clean() on top, giving the correct
    // TWO total applications for vertices and Location.
    let polygons: Vec<FinalizedPolygon> = cube_faces(width, breadth, height)
        .iter()
        .map(base::finalize_polygon)
        .collect::<Result<_, _>>()?;
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

    base::emit_actor_t3d(&name, &model_name, csg_op, poly_flags, location, &polygons)
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
        // spellings as a literal base name instead of proxying to get argparse's real error. See
        // base::looks_like_option's doc for the exact rule (old/'s custom coordinate-token
        // exception) and why the remaining mismatch with real argparse is always safe.
        if base::looks_like_option(val) {
            return None;
        }
        match tok {
            "--width" => width = Some(val.parse::<f64>().ok()?),
            "--breadth" => breadth = Some(val.parse::<f64>().ok()?),
            "--height" => height = Some(val.parse::<f64>().ok()?),
            "--at" => at = Some(base::parse_at(val)?),
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

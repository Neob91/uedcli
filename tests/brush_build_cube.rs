//! Differential tests for the ported `brush build cube` verb (src/brush_build.rs) against
//! old/bin/uedcli -- the verification method dev/epics/refactor.md's "Testing strategy" prescribes.
//!
//! Two groups:
//! - Proxy-fallback cases need no real project/substrate: both sides defer to the identical
//!   old/bin/uedcli invocation (src/brush_build.rs's try_build_cube returns None), so they're
//!   trivially byte-identical by construction and always run.
//! - Native-geometry cases need old/bin/uedcli's own run to succeed, which (unconditionally, even
//!   for a plain cube with no --texture/--prop) resolves the project's class index to validate
//!   Engine.Brush exists -- requiring a real game substrate. That substrate is gitignored/
//!   user-supplied, same disposition as old/uedcli/tests/conftest.py's install_root() /
//!   UEDCLI_TEST_INSTALL convention (not committed to the repo) -- soft-skipped with a clear
//!   message when unavailable, rather than failing the suite.

use std::fs;
use std::path::PathBuf;
use std::process::{Command, Output};

fn repo_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
}

fn old_uedcli() -> PathBuf {
    repo_root().join("old/bin/uedcli")
}

fn new_uedcli() -> PathBuf {
    PathBuf::from(env!("CARGO_BIN_EXE_uedcli"))
}

/// `home`/`project` go in as env vars, never as a leading `--project` CLI token: try_build_cube
/// requires `args[0] == "brush"`, so a leading `--project <path>` would make EVERY case fall
/// through to the proxy instead of reaching the native path under test (a real bug this file had
/// -- see the git history). `UEDCLI_PROJECT`/`UEDCLI_HOME` are always set (cleared when `None`),
/// never inherited from the host, so a stray env var on the machine running this can't produce a
/// false pass either way.
fn run(
    bin: &std::path::Path,
    args: &[&str],
    home: Option<&std::path::Path>,
    project: Option<&std::path::Path>,
) -> Output {
    let mut cmd = Command::new(bin);
    cmd.args(args).current_dir(repo_root());
    cmd.env_remove("UEDCLI_HOME");
    cmd.env_remove("UEDCLI_PROJECT");
    if let Some(h) = home {
        cmd.env("UEDCLI_HOME", h);
    }
    if let Some(p) = project {
        cmd.env("UEDCLI_PROJECT", p);
    }
    cmd.output().unwrap_or_else(|e| panic!("failed to run {}: {e}", bin.display()))
}

fn assert_identical(args: &[&str], home: Option<&std::path::Path>, project: Option<&std::path::Path>) {
    let old = run(&old_uedcli(), args, home, project);
    let new = run(&new_uedcli(), args, home, project);
    assert_eq!(old.stdout, new.stdout, "stdout differs for {args:?}");
    assert_eq!(old.stderr, new.stderr, "stderr differs for {args:?}");
    assert_eq!(old.status.code(), new.status.code(), "exit code differs for {args:?}");
}

// ---- proxy-fallback cases: no project/substrate needed -----------------------------------------

#[test]
fn excluded_flag_texture_falls_back_identically() {
    assert_identical(
        &["brush", "build", "cube", "--width", "1", "--breadth", "1", "--height", "1", "--texture", "DeusExDeco.Wood"],
        None,
        None,
    );
}

#[test]
fn excluded_flag_prop_falls_back_identically() {
    assert_identical(
        &["brush", "build", "cube", "--width", "1", "--breadth", "1", "--height", "1", "--prop", "Tag=foo"],
        None,
        None,
    );
}

#[test]
fn missing_required_flag_falls_back_identically() {
    assert_identical(&["brush", "build", "cube", "--width", "1", "--breadth", "1"], None, None);
}

#[test]
fn unknown_flag_falls_back_identically() {
    assert_identical(
        &["brush", "build", "cube", "--width", "1", "--breadth", "1", "--height", "1", "--bogus", "5"],
        None,
        None,
    );
}

#[test]
fn help_falls_back_identically() {
    assert_identical(&["brush", "build", "cube", "--help"], None, None);
}

#[test]
fn leading_project_flag_falls_back_identically() {
    // argv[0] isn't "brush" when --project comes first -- try_build_cube must not match this, so
    // it proxies (and old/ handles --project fine on its own either way).
    assert_identical(
        &["--project", ".", "brush", "build", "cube", "--width", "1", "--breadth", "1", "--height", "1"],
        None,
        None,
    );
}

#[test]
fn scientific_notation_at_value_falls_back_identically() {
    // Regression: old/'s custom _CoordArgumentParser (cli/parsers/_arguments.py) treats a value
    // matching _COORD_TOKEN (digits/dots/commas/signs only) as a value even though it starts
    // with '-', specifically so `--at -32,-32,32` works -- but "-1e5,0,0" has a letter, doesn't
    // match that pattern, and old/ refuses to consume it as --at's value at all ("expected one
    // argument", exit 2). An earlier version of this port's own ambiguity check was too narrow
    // (only rejected tokens starting with "--"), so it wrongly accepted this as a real value and
    // emitted successfully (exit 0) where old/ errors -- a real exit-code divergence, not just a
    // text mismatch.
    assert_identical(
        &["brush", "build", "cube", "--width", "1", "--breadth", "1", "--height", "1", "--at", "-1e5,0,0"],
        None,
        None,
    );
}

#[test]
fn base_name_single_dash_letter_falls_back_identically() {
    // Same root cause as the scientific-notation case above: "-x" isn't _COORD_TOKEN-shaped
    // (contains a letter), so old/ refuses to consume it as --base-name's value.
    assert_identical(
        &["brush", "build", "cube", "--width", "1", "--breadth", "1", "--height", "1", "--base-name", "-x"],
        None,
        None,
    );
}

// ---- native-geometry cases: need a real substrate for old/'s own class-index check -------------

/// Mirrors old/uedcli/tests/conftest.py's install_root()/UEDCLI_TEST_INSTALL: a real, gitignored
/// game install, not committed to the repo. Checked at a couple of conventional locations this
/// project's own dev setups have used; returns None (soft skip) if none is found.
fn find_substrate() -> Option<PathBuf> {
    if let Ok(p) = std::env::var("UEDCLI_TEST_INSTALL") {
        let p = PathBuf::from(p);
        if p.join("Engine.u").is_file() {
            return Some(p);
        }
    }
    for candidate in ["uned/DeusExAssets/System", "uned/UED22"] {
        let p = repo_root().join("old").join(candidate);
        if p.join("Engine.u").is_file() {
            return Some(p);
        }
    }
    None
}

/// A scratch $UEDCLI_HOME (config.toml pointing at the substrate) + a minimal project, under
/// target/ so it's already gitignored and left for `cargo clean` to reap. One subdirectory PER
/// TEST (keyed by name): cargo test runs tests in parallel threads by default, and every
/// substrate_test! case used to share one `home`/`project` pair, racing writes to the same
/// config.toml/uedcli.toml against concurrent reads from another test's old/new invocations
/// (caught as a one-off spurious failure under `cargo test`'s default parallelism).
struct Harness {
    home: PathBuf,
    project: PathBuf,
}

fn harness(substrate: &std::path::Path, test_name: &str) -> Harness {
    let base = repo_root().join("target/test-tmp/brush-build-cube").join(test_name);
    let home = base.join("home");
    let project = base.join("project");
    fs::create_dir_all(home.as_path()).unwrap();
    fs::create_dir_all(project.join("maps")).unwrap();
    fs::write(
        home.join("config.toml"),
        format!("[games.deusex]\npaths = {:?}\n", substrate.display().to_string()),
    )
    .unwrap();
    fs::write(project.join("uedcli.toml"), "game = \"deusex\"\nmaps = \"maps\"\n").unwrap();
    Harness { home, project }
}

fn assert_identical_with_project(h: &Harness, extra_args: &[&str]) {
    // UEDCLI_PROJECT, not a leading `--project` CLI token: try_build_cube requires
    // args[0] == "brush", so a leading --project would make the new binary fall through to the
    // proxy for every one of these cases, defeating the whole point of this test group.
    assert_identical(extra_args, Some(&h.home), Some(&h.project));
}

macro_rules! substrate_test {
    ($name:ident, $args:expr) => {
        #[test]
        fn $name() {
            let Some(substrate) = find_substrate() else {
                eprintln!(
                    "skipping {}: no real game substrate found (set UEDCLI_TEST_INSTALL, or see \
                     old/uedcli/tests/conftest.py's install_root() convention)",
                    stringify!($name)
                );
                return;
            };
            let h = harness(&substrate, stringify!($name));
            assert_identical_with_project(&h, $args);
        }
    };
}

substrate_test!(cube_basic_dims, &["brush", "build", "cube", "--width", "10", "--breadth", "20", "--height", "30"]);
substrate_test!(cube_defaults, &["brush", "build", "cube", "--width", "1", "--breadth", "1", "--height", "1"]);
substrate_test!(cube_at, &["brush", "build", "cube", "--width", "4", "--breadth", "4", "--height", "4", "--at", "100,-50,25"]);
substrate_test!(cube_base_name, &["brush", "build", "cube", "--width", "4", "--breadth", "4", "--height", "4", "--base-name", "MyBox"]);
// A coord-token-shaped (digits-only, signed) value is still a legitimate base name to old/'s own
// parser -- confirms looks_like_option's coord-token exception doesn't over-proxy the cases it's
// specifically meant to keep native.
substrate_test!(cube_base_name_negative_number_shaped, &["brush", "build", "cube", "--width", "4", "--breadth", "4", "--height", "4", "--base-name", "-5"]);
substrate_test!(cube_csg_subtract, &["brush", "build", "cube", "--width", "4", "--breadth", "4", "--height", "4", "--csg", "subtract"]);
substrate_test!(cube_solidity_semisolid, &["brush", "build", "cube", "--width", "4", "--breadth", "4", "--height", "4", "--solidity", "semisolid"]);
substrate_test!(cube_solidity_nonsolid, &["brush", "build", "cube", "--width", "4", "--breadth", "4", "--height", "4", "--solidity", "nonsolid"]);
substrate_test!(cube_fractional_dims, &["brush", "build", "cube", "--width", "7.5", "--breadth", "3.25", "--height", "11.125"]);
substrate_test!(cube_binary_noise_dims, &["brush", "build", "cube", "--width", "0.1", "--breadth", "0.2", "--height", "0.3"]);
substrate_test!(cube_near_integer_epsilon_snap, &["brush", "build", "cube", "--width", "9.9996", "--breadth", "10.0004", "--height", "10"]);
// Regression: old/'s make_brush_actor pre-cleans vertices/location once, then fmt_vertex/fmt_loc
// clean() them AGAIN at emit time -- not idempotent right at the CLEAN_EPS=0.001 boundary, since
// quantize6's 6-dp rounding can move a value's distance-from-integer from just above 0.001 to
// at-or-below it. 5.0010003 is >0.001 from 5 (no snap on a single clean), but quantize6 rounds it
// to 5.001000 first, and a SECOND clean() then sees 0.001000 <= 0.001 and snaps to 5 exactly.
substrate_test!(cube_at_clean_eps_boundary_double_clean, &["brush", "build", "cube", "--width", "1", "--breadth", "1", "--height", "1", "--at", "5.0010003,0,0"]);
substrate_test!(
    cube_all_in_scope_flags_combined,
    &[
        "brush", "build", "cube", "--width", "12.5", "--breadth", "6", "--height", "3.333", "--at",
        "-10.5,20,0", "--base-name", "Combo", "--csg", "subtract", "--solidity", "nonsolid"
    ]
);
substrate_test!(cube_negative_width_rejected, &["brush", "build", "cube", "--width", "-5", "--breadth", "1", "--height", "1"]);
substrate_test!(cube_zero_height_rejected, &["brush", "build", "cube", "--width", "1", "--breadth", "1", "--height", "0"]);
substrate_test!(cube_nan_width_rejected, &["brush", "build", "cube", "--width", "nan", "--breadth", "1", "--height", "1"]);
substrate_test!(cube_inf_width_rejected, &["brush", "build", "cube", "--width", "inf", "--breadth", "1", "--height", "1"]);

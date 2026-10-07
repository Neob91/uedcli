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

fn run(bin: &std::path::Path, args: &[&str], home: Option<&std::path::Path>) -> Output {
    let mut cmd = Command::new(bin);
    cmd.args(args).current_dir(repo_root());
    if let Some(h) = home {
        cmd.env("UEDCLI_HOME", h);
    }
    cmd.output().unwrap_or_else(|e| panic!("failed to run {}: {e}", bin.display()))
}

fn assert_identical(args: &[&str], home: Option<&std::path::Path>) {
    let old = run(&old_uedcli(), args, home);
    let new = run(&new_uedcli(), args, home);
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
    );
}

#[test]
fn excluded_flag_prop_falls_back_identically() {
    assert_identical(
        &["brush", "build", "cube", "--width", "1", "--breadth", "1", "--height", "1", "--prop", "Tag=foo"],
        None,
    );
}

#[test]
fn missing_required_flag_falls_back_identically() {
    assert_identical(&["brush", "build", "cube", "--width", "1", "--breadth", "1"], None);
}

#[test]
fn unknown_flag_falls_back_identically() {
    assert_identical(
        &["brush", "build", "cube", "--width", "1", "--breadth", "1", "--height", "1", "--bogus", "5"],
        None,
    );
}

#[test]
fn help_falls_back_identically() {
    assert_identical(&["brush", "build", "cube", "--help"], None);
}

#[test]
fn leading_project_flag_falls_back_identically() {
    // argv[0] isn't "brush" when --project comes first -- try_build_cube must not match this, so
    // it proxies (and old/ handles --project fine on its own either way).
    assert_identical(
        &["--project", ".", "brush", "build", "cube", "--width", "1", "--breadth", "1", "--height", "1"],
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
/// target/ so it's already gitignored and left for `cargo clean` to reap.
struct Harness {
    home: PathBuf,
    project: PathBuf,
}

fn harness(substrate: &std::path::Path) -> Harness {
    let base = repo_root().join("target/test-tmp/brush-build-cube");
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
    let mut args: Vec<&str> = vec!["--project"];
    let project_str = h.project.to_str().unwrap();
    args.push(project_str);
    args.extend_from_slice(extra_args);
    assert_identical(&args, Some(&h.home));
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
            let h = harness(&substrate);
            assert_identical_with_project(&h, $args);
        }
    };
}

substrate_test!(cube_basic_dims, &["brush", "build", "cube", "--width", "10", "--breadth", "20", "--height", "30"]);
substrate_test!(cube_defaults, &["brush", "build", "cube", "--width", "1", "--breadth", "1", "--height", "1"]);
substrate_test!(cube_at, &["brush", "build", "cube", "--width", "4", "--breadth", "4", "--height", "4", "--at", "100,-50,25"]);
substrate_test!(cube_base_name, &["brush", "build", "cube", "--width", "4", "--breadth", "4", "--height", "4", "--base-name", "MyBox"]);
substrate_test!(cube_csg_subtract, &["brush", "build", "cube", "--width", "4", "--breadth", "4", "--height", "4", "--csg", "subtract"]);
substrate_test!(cube_solidity_semisolid, &["brush", "build", "cube", "--width", "4", "--breadth", "4", "--height", "4", "--solidity", "semisolid"]);
substrate_test!(cube_solidity_nonsolid, &["brush", "build", "cube", "--width", "4", "--breadth", "4", "--height", "4", "--solidity", "nonsolid"]);
substrate_test!(cube_fractional_dims, &["brush", "build", "cube", "--width", "7.5", "--breadth", "3.25", "--height", "11.125"]);
substrate_test!(cube_binary_noise_dims, &["brush", "build", "cube", "--width", "0.1", "--breadth", "0.2", "--height", "0.3"]);
substrate_test!(cube_near_integer_epsilon_snap, &["brush", "build", "cube", "--width", "9.9996", "--breadth", "10.0004", "--height", "10"]);
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

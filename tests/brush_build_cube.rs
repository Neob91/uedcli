//! Differential tests for the ported `brush build cube` verb (src/cli/cube.rs's argument
//! parsing, src/brush/builders/cube.rs's geometry) against old/bin/uedcli -- the verification
//! method dev/epics/refactor.md's "Testing strategy" prescribes.
//!
//! This file covers the proxy-fallback cases: no real project/substrate needed, since both sides
//! defer to the identical old/bin/uedcli invocation (cli::cube::try_build_cube returns None), so
//! they're trivially byte-identical by construction and always run. The native-geometry cases
//! (which need a real game substrate) are a separate test group, added next.

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

#[test]
fn base_name_bare_dash_falls_back_identically() {
    // looks_like_option is conservative, not an exact replica of real argparse's
    // _parse_optional: that function has a len(arg_string) == 1 carve-out treating a bare "-" as
    // a value (confirmed directly against old/bin/uedcli -- it accepts this with no "expected
    // one argument" error), but "-" isn't _COORD_TOKEN-shaped, so this port proxies instead of
    // handling it natively. Safe either way (the proxy reproduces old/'s real behavior exactly),
    // but worth pinning since it's the one case real argparse explicitly special-cases.
    assert_identical(
        &["brush", "build", "cube", "--width", "1", "--breadth", "1", "--height", "1", "--base-name", "-"],
        None,
        None,
    );
}

#[test]
fn base_name_dash_with_space_falls_back_identically() {
    // Same conservative-proxy shape as the bare-dash case above: real argparse also treats any
    // token containing a space as a value (another _parse_optional carve-out this port doesn't
    // replicate), so this proxies rather than handling it natively -- still byte-identical either
    // way, since old/bin/uedcli runs for real on the fallback path.
    assert_identical(
        &["brush", "build", "cube", "--width", "1", "--breadth", "1", "--height", "1", "--base-name", "-foo bar"],
        None,
        None,
    );
}

#[test]
fn csg_coord_token_shaped_invalid_value_falls_back_identically() {
    // --csg's own validation (add/subtract only) runs AFTER looks_like_option -- confirms the
    // ordering is safe: "-5" is _COORD_TOKEN-shaped, so it's consumed as --csg's value both by
    // old/'s real parser and by this port, then rejected by the choices check either way (old/'s
    // own argparse "invalid choice" error vs. this port's own validation triggering a proxy) --
    // byte-identical regardless of which side actually rejects it, since any rejection here means
    // try_build_cube returns None.
    assert_identical(
        &["brush", "build", "cube", "--width", "1", "--breadth", "1", "--height", "1", "--csg", "-5"],
        None,
        None,
    );
}

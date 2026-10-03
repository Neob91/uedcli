//! Proves the proxy plumbing itself: running the new binary must be byte-identical to running
//! `old/bin/uedcli` directly, for both a success and a failure case. Every verb is unported, so
//! this is what PR #1 is actually proving.

use std::path::PathBuf;
use std::process::{Command, Output};

fn old_uedcli() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("old/bin/uedcli")
}

fn run(bin: &std::path::Path, args: &[&str]) -> Output {
    Command::new(bin)
        .args(args)
        .output()
        .unwrap_or_else(|e| panic!("failed to run {}: {e}", bin.display()))
}

fn assert_identical(args: &[&str]) {
    let new = run(&PathBuf::from(env!("CARGO_BIN_EXE_uedcli")), args);
    let old = run(&old_uedcli(), args);
    assert_eq!(new.stdout, old.stdout, "stdout differs for {args:?}");
    assert_eq!(new.stderr, old.stderr, "stderr differs for {args:?}");
    assert_eq!(
        new.status.code(),
        old.status.code(),
        "exit code differs for {args:?}"
    );
}

#[test]
fn help_is_identical() {
    assert_identical(&["--help"]);
}

#[test]
fn a_failure_case_is_identical() {
    // No project configured here -- a clean exit-2 failure, not a success path.
    assert_identical(&["class", "list", "--flat"]);
}

#[test]
fn works_from_any_cwd() {
    // Regression test: main.rs used to exec the literal relative path "old/bin/uedcli", which
    // only resolved when cwd happened to be the repo root.
    let elsewhere = std::env::temp_dir();
    let new = Command::new(env!("CARGO_BIN_EXE_uedcli"))
        .arg("--help")
        .current_dir(&elsewhere)
        .output()
        .unwrap_or_else(|e| panic!("failed to run from {}: {e}", elsewhere.display()));
    let old = Command::new(old_uedcli())
        .arg("--help")
        .current_dir(&elsewhere)
        .output()
        .unwrap();
    assert_eq!(new.stdout, old.stdout);
    assert_eq!(new.stderr, old.stderr);
    assert_eq!(new.status.code(), old.status.code());
}

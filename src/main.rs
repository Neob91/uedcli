mod brush;
mod core;

use std::env;
use std::io::Write;
use std::os::unix::process::CommandExt;
use std::process::Command;

fn main() {
    // Only a fully in-scope, successfully-parsed `brush build cube` is handled natively; any
    // ambiguity at all (an unrecognized/excluded flag, --project, -h/--help, a missing or
    // malformed value) returns None and falls through to the unconditional proxy below,
    // unchanged -- see brush::builders::cube's module doc for exactly what's in scope and why.
    let args: Vec<String> = env::args().skip(1).collect();
    if let Some(result) = brush::builders::cube::try_build_cube(&args) {
        match result {
            Ok(t3d) => {
                print!("{t3d}");
                std::process::exit(0);
            }
            Err(message) => {
                let _ = writeln!(std::io::stderr(), "{message}");
                std::process::exit(2);
            }
        }
    }

    // `old/bin/uedcli`, relative to cwd: nothing invokes this binary from outside the repo until
    // the rewrite is done and released (owner ruling on PR #1's review), so this assumes cwd is
    // the repo root -- the normal case for both `cargo run` and the built binary during dev.
    let old_uedcli = "old/bin/uedcli";

    // Every other verb is unported -- proxy to old/bin/uedcli. `exec` replaces this process
    // rather than spawning a child, so argv/stdin/stdout/stderr/exit code pass through exactly
    // as if old/bin/uedcli had been invoked directly; it only returns on failure.
    let err = Command::new(old_uedcli).args(env::args_os().skip(1)).exec();
    eprintln!("uedcli: failed to exec {old_uedcli}: {err}");
    std::process::exit(1);
}

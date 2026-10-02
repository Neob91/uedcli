use std::env;
use std::os::unix::process::CommandExt;
use std::process::Command;

fn main() {
    // `old/bin/uedcli`, relative to cwd: nothing invokes this binary from outside the repo until
    // the rewrite is done and released (owner ruling on PR #1's review), so this assumes cwd is
    // the repo root -- the normal case for both `cargo run` and the built binary during dev.
    let old_uedcli = "old/bin/uedcli";

    // Every verb is unported so far -- proxy everything to old/bin/uedcli. `exec` replaces this
    // process rather than spawning a child, so argv/stdin/stdout/stderr/exit code pass through
    // exactly as if old/bin/uedcli had been invoked directly; it only returns on failure.
    let err = Command::new(old_uedcli).args(env::args_os().skip(1)).exec();
    eprintln!("uedcli: failed to exec {old_uedcli}: {err}");
    std::process::exit(1);
}

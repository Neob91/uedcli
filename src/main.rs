mod core;

use std::env;
use std::os::unix::process::CommandExt;
use std::process::Command;

fn main() {
    // Resolve old/bin/uedcli relative to this binary's own location, not cwd -- must work when
    // invoked from any directory, not just the repo root. current_exe() on Linux reads
    // /proc/self/exe (always canonical, symlinks resolved); the binary lives at
    // <repo>/target/<profile>/uedcli, so the repo root is two parents up.
    let exe = match env::current_exe() {
        Ok(exe) => exe,
        Err(err) => {
            eprintln!("uedcli: could not resolve own executable path: {err}");
            std::process::exit(1);
        }
    };
    let repo_root = match exe.parent().and_then(|p| p.parent()).and_then(|p| p.parent()) {
        Some(root) => root,
        None => {
            eprintln!(
                "uedcli: could not resolve repo root from executable path {}",
                exe.display()
            );
            std::process::exit(1);
        }
    };
    let old_uedcli = repo_root.join("old/bin/uedcli");

    // Every verb is unported so far -- proxy everything to old/bin/uedcli. `exec` replaces this
    // process rather than spawning a child, so argv/stdin/stdout/stderr/exit code pass through
    // exactly as if old/bin/uedcli had been invoked directly; it only returns on failure.
    let err = Command::new(&old_uedcli).args(env::args_os().skip(1)).exec();
    eprintln!("uedcli: failed to exec {}: {err}", old_uedcli.display());
    std::process::exit(1);
}

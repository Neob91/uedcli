mod brush;
mod cli;
mod core;

use std::env;
use std::io::Write;
use std::os::unix::process::CommandExt;
use std::process::Command;

fn main() {
    // Only a fully in-scope, successfully-parsed `brush build cube` is handled natively; anything
    // else returns None and falls through to the unconditional proxy below, unchanged -- see
    // cli::cube's module doc for exactly what's in scope.
    let args: Vec<String> = env::args().skip(1).collect();
    if let Some(result) = cli::cube::try_build_cube(&args) {
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

    // Resolve old/bin/uedcli relative to this binary's own location, not cwd -- must work when
    // invoked from any directory, not just the repo root. current_exe() on Linux reads
    // /proc/self/exe (always canonical, symlinks resolved); the binary lives at
    // <repo>/target/<profile>/uedcli, so the repo root is two parents up.
    let executable_path = match env::current_exe() {
        Ok(path) => path,
        Err(err) => {
            eprintln!("uedcli: could not resolve own executable path: {err}");
            std::process::exit(1);
        }
    };
    let repo_root = match executable_path.parent().and_then(|p| p.parent()).and_then(|p| p.parent()) {
        Some(root) => root,
        None => {
            eprintln!(
                "uedcli: could not resolve repo root from executable path {}",
                executable_path.display()
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

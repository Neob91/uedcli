use std::env;
use std::os::unix::process::CommandExt;
use std::path::PathBuf;
use std::process::Command;

/// Find the repo root by walking up from this binary's own location until a directory
/// containing `old/bin/uedcli` turns up. A real checkout is never deeper than this from
/// `target/{debug,release}/uedcli`.
fn find_old_uedcli() -> Option<PathBuf> {
    let exe = env::current_exe().ok()?;
    let mut dir = exe.parent()?;
    for _ in 0..8 {
        let candidate = dir.join("old/bin/uedcli");
        if candidate.is_file() {
            return Some(candidate);
        }
        dir = dir.parent()?;
    }
    None
}

fn main() {
    let old_uedcli = find_old_uedcli().unwrap_or_else(|| {
        let exe = env::current_exe().unwrap_or_default();
        eprintln!("uedcli: could not find old/bin/uedcli near {}", exe.display());
        std::process::exit(1);
    });

    // Every verb is unported so far -- proxy everything to old/bin/uedcli. `exec` replaces this
    // process rather than spawning a child, so argv/stdin/stdout/stderr/exit code pass through
    // exactly as if old/bin/uedcli had been invoked directly; it only returns on failure.
    let err = Command::new(&old_uedcli).args(env::args_os().skip(1)).exec();
    eprintln!("uedcli: failed to exec {}: {err}", old_uedcli.display());
    std::process::exit(1);
}

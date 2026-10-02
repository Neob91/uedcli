# Nuitka standalone + uedcli_native bundling

Question: does `python -m nuitka --mode=standalone` bundle `uedcli_native` (a pyo3/abi3 compiled
CPython extension module, installed via the existing Docker Rust-build image + pip) the same way it
already handles third-party extensions like Pillow's `_imaging`?

Method: `run.sh` compiles `probe.py` (imports `uedcli.native_ext`, calls the real
`build_brush_model([])`) standalone, then runs the compiled binary with `PATH` stripped to
`/usr/bin:/bin` (no venv, no system `python3.12` reachable) to prove it needs no interpreter.

## Environment snags hit along the way (not the actual question, but real and worth recording)

1. **Docker-based native build unavailable from this worktree.** `bin/_venv.sh`'s
   `ensure_native_ext` failed: `docker: Error response from daemon: error while creating mount
   source path '/workspace/uedcli/.claude/worktrees/standalone-binary-build/uedcli-native': mkdir
   /workspace: permission denied`. This is the same rootless-docker-cannot-mount limitation already
   documented repeatedly in `GUI-PARITY.md` for other sessions — the daemon can't bind-mount a path
   under `.claude/worktrees/`. Unrelated to this spike's real question, so `run.sh` falls back to the
   wheel already built from this exact source in the main checkout
   (`git worktree list --porcelain`'s first entry), after confirming the source is identical
   (`git diff master -- uedcli-native/` is empty in this worktree — a fresh worktree, untouched).
2. **No `patchelf` and no root.** Nuitka's standalone mode on Linux needs `patchelf` to rewrite
   RPATHs; `apt-get install` isn't available without root in this sandbox. PyPI ships a prebuilt
   binary via the `patchelf` package (`pip install patchelf`) — a build-time-only tool, doesn't
   affect what the compiled binary depends on at runtime. Folded into `run.sh`.
3. `git worktree list --porcelain | awk '...{print $2; exit}'` (an early-exiting awk pipeline)
   tripped `set -o pipefail` with SIGPIPE (exit 141) against `git`'s still-writing output, even
   though the captured value was correct. Fixed by letting `awk` drain to EOF (`{print $2}`, no
   `exit`) before `head -1` truncates its already-complete output, plus `|| true` as a belt-and-
   braces guard.

## Result

Full `run.sh` output (fallback path engaged for reasons 1-2 above; none of this affects the actual
question):

```
docker: Error response from daemon: error while creating mount source path
'/workspace/uedcli/.claude/worktrees/standalone-binary-build/uedcli-native': mkdir /workspace:
permission denied
uedcli: uedcli_native build failed — native materialize unavailable
-- docker-based native build unavailable in this worktree; falling back to the prebuilt wheel
already on disk (source confirmed identical via git diff) --
Nuitka-Options: Used command line options:
Nuitka-Options:   --mode=standalone --output-dir=.../build .../probe.py
Nuitka: Starting Python compilation with:
Nuitka:   Version '4.2.1' on Python 3.12 (flavor 'PyEnv Python') commercial grade 'not installed'.
Nuitka: Module(s) 'csv' necessitate pass 3
Nuitka: Completed Python level compilation and optimization.
Nuitka: Generating source code for C backend compiler.
Nuitka: Running data composer tool for optimal constant value handling.
Nuitka: Running C compilation via Scons.
Nuitka-Scons: Backend C compiler: gcc (gcc 12).
Nuitka-Scons: Backend C linking with 11 files (no progress information available for this stage).
Nuitka: Keeping build directory '.../build/probe.build'.
Nuitka: Successfully created '.../build/probe.dist/probe.bin'.
-- compiled binary: .../build/probe.dist/probe.bin --
-- running with PATH stripped of the venv/system python, to prove no interpreter dependency --
OK: build_brush_model([]) -> links=[] built=<builtins.Built object at 0x7f4b9e6076e0>
```

## Verdict

**RESOLVED — proceed to Task 2 as designed.** No `--include-package`/special-casing was needed:
Nuitka's default standalone import-following found `uedcli.native_ext`'s function-local
`import uedcli_native`, located the installed compiled `.so` in the build venv's site-packages, and
copied it into `probe.dist/` alongside the compiled program — exactly the mechanism the spec assumed
by analogy with Pillow. The compiled binary called the real Rust core (`build_brush_model`, a real
`bspcsg`-backed entry point, not a stub) and produced correct output with zero interpreter on `PATH`.

Two concrete, load-bearing facts for Task 2's `bin/build-standalone`:

- **The standalone executable is named `<script-basename>.bin`** (here: `probe.bin`, not `probe`)
  when no `--output-filename` is given — Nuitka's default on Linux. `bin/build-standalone` passes
  `--output-filename=uedcli` explicitly; Task 2 verifies empirically whether that produces exactly
  `uedcli` (no `.bin` suffix) or still appends one, and adjusts the path it looks for accordingly.
- **`--static-libpython` was not exercised by this probe** (not passed) — Open risk #2 is still open,
  to be resolved by Task 2's `--static-libpython=yes` attempt with its `=no` fallback.

## Addendum (Task 2): the relative-import crash, and the size cost of standalone mode

Compiling `uedcli/__main__.py` directly (as Task 2's plan originally wrote it) produces a binary
that CRASHES at runtime: `ImportError: attempted relative import with no known parent package`.
`__main__.py` uses `from .cli.main import main` — a relative import that needs real package/`-m`
context to resolve, the same reason `python uedcli/__main__.py` (as opposed to `python -m uedcli`)
fails in plain CPython too. Nuitka's own build output even warns about this: "To compile a package
with a '__main__' module, specify its containing directory but not the '__main__.py' itself, also
consider if '--python-flag=-m' should be used."

Two fixes were compared directly:

1. `--mode=standalone --python-flag=-m ... uedcli` (compile the PACKAGE, not the file) — works,
   confirmed by running `--help` on the result.
2. A new absolute-import wrapper script (`from uedcli.cli.main import main`, compiled directly,
   no `-m`) — also works.

**Both land at ~592 linked files / ~127MB**, versus the broken direct-`__main__.py` compile's
18MB/7 files — i.e. the earlier "lean" build wasn't correctly minimal, it was incomplete (Nuitka
couldn't fully resolve the relative import at compile time either, so it silently compiled a
too-small subset that doesn't work). **`PIL` and `websockets` land in the standalone output despite
being lazily imported at runtime** (`uedcli/serve/app.py`'s module-level `from fastapi import
...`, reached only through `cli/commands/serve.py`'s deferred `from ...serve.app import
create_app`) — Nuitka's standalone mode follows the STATIC import graph reachable from `main()`,
not the RUNTIME call graph a specific invocation takes; argparse's dispatch-by-string mechanism
isn't something Nuitka's compiler can prune around, so every subcommand's handler (and whatever
it imports, however deep) is equally "reachable" at compile time. This does NOT affect the spec's
no-regression startup-time bar — the lazy imports still defer actual module *execution* at runtime,
same as plain CPython; it only means the compiled binary is much larger on disk than a naive reading
of "the code is lazy" would suggest. Worth knowing, not a blocker.

Went with fix 1 (`--python-flag=-m` on the package directory) for `bin/build-standalone`: no new
file, matches the spec's stated "compiled from the existing `uedcli/__main__.py`" approach exactly.
With this flag, Nuitka names the standalone output directory after the PACKAGE (`uedcli.dist/`, not
`__main__.dist/`) — `bin/build-standalone`'s `DIST_DIR` and tarball step account for this.

The comparison scripts (`entry_probe.py`, `try_entry_probe.sh`, `try_m_flag.sh`) were throwaway —
their finding is captured here, and the accepted approach is now `bin/build-standalone` itself, so
they aren't kept as permanent parallel tooling.

## Addendum 2 (Task 4): compiled binary crashes on Unicode output under a stripped locale

`bin/test-standalone`'s first check (`--help` with `PATH` stripped to `/usr/bin:/bin`, `env -i` so
no `LANG`/`LC_ALL` either) crashed the compiled binary:
`UnicodeEncodeError: 'ascii' codec can't encode character '—' in position 197` (the help
text's em-dashes). `check_locale.sh` (committed) reproduces the identical `env -i` environment
against the SOURCE CLI via `.venv/bin/python -m uedcli --help` -- it succeeds, exit 0, full output.

So this is a real regression Nuitka's compile introduces, not a pre-existing codebase issue: plain
CPython auto-coerces UTF-8 mode when it detects a `C`/`POSIX` locale (PEP 538/540), and Nuitka's
compiled standalone runtime doesn't replicate that coercion. Fixed in `uedcli/__main__.py`:
`sys.stdout.reconfigure(encoding="utf-8", errors="replace")` (+ `stderr`) right before calling
`main()`, forcing the same guarantee CPython already gives for free. Re-verified:
`bin/test-standalone` passes end to end after the fix, including this check with `PATH`/locale
stripped exactly as before.

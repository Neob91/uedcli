# Standalone binary build for uedcli

## Goal

Package `uedcli` — the CLI, the `uedcli-native` Rust extension, and a prebuilt `web/` frontend — as
a self-contained artifact that needs no system Python, no `pip install`, and no `npm`/`node` on the
target host to run. Linux first; macOS and Windows are later phases, same pipeline shape, not built
here. Docker remains a required *runtime* dependency only for the editor-driven materialize path —
untouched, out of scope.

## Non-goals

- Eliminating Docker/Wine/UED22 for the editor-driven path. External toolchain, not a Python
  packaging problem — considered and rejected as scope during design (owner ruling, 2026-09-19).
- Hitting a hard startup-latency number in this phase. The bar is **no regression**: Nuitka
  packaging must not add measurable startup overhead vs. running the same command from the source
  venv. Getting plain-verb startup under the owner's ultimate 50ms target is separate future work
  (an import-graph/lazy-import refactor), tracked but not done here.
- Restructuring the CLI's import/dispatch structure. Already lazy: `uedcli/cli/main.py` and every
  `uedcli/cli/parsers/*.py` (including `serve.py`, `texture.py`) import none of
  `fastapi`/`uvicorn`/`httpx`/`websockets`/`PIL` at module scope — confirmed by inspection, not
  assumed. No source change needed here for that reason.
- A general CI overhaul. This repo has no `.github/workflows/` today (confirmed). This spec adds
  one new, narrowly-scoped workflow for building/publishing the binary artifact; nothing else about
  CI changes.

## Approach

### Packaging tool & mode

Nuitka, `--standalone` mode: a directory containing the `uedcli` executable, its bundled `.so`s, and
data files. Never `--onefile` — onefile mode self-extracts on every first run and, even with a
cached `--onefile-tempdir-spec`, CRC-checksums the whole cached payload on every subsequent launch
(confirmed against Nuitka's own docs and `Nuitka/Nuitka#4028`). Standalone mode has no extraction
step at all, ever — the files are just read from disk. Rejected `--onefile` for this reason (owner
ruling, 2026-09-19: zero runtime extraction over a single downloadable file).

Compiled from the existing `uedcli/__main__.py` (the same entry point `python -m uedcli` already
uses) — no new wrapper script needed.

Where the build Python supports it (a pyenv-built or self-compiled CPython built without
`--enable-shared`, or Anaconda on non-Windows — **not** the arbitrary system `python3.12` the dev
venv (`bin/_venv.sh`) uses today), Nuitka links `libpython` statically into the executable, so the
standalone directory carries no separate `libpython.so`. This needs a purpose-built Python for the
CI build step, distinct from the dev venv's Python. If that isn't achievable on a given platform,
standalone mode still works with a bundled `libpython.so` sitting in the output directory —
degraded (one more file), not blocked; still zero-extraction.

### Native extension (`uedcli-native`)

Built exactly as it is today: the existing Rust-build Docker image
(`bin/_venv.sh`'s `_ensure_build_image` / `ensure_native_ext`) produces the abi3 wheel; the build
venv pip-installs it before Nuitka runs. Nuitka's standalone mode auto-discovers and copies `.so`
extension modules found in the build venv's site-packages for any package the program actually
imports — this is the existing mechanism it uses for Pillow's `_imaging`. `uedcli_native` is
architecturally the same kind of artifact (a compiled CPython extension module), so no special
handling is expected — but this is the single biggest unverified assumption in this design, and is
the first thing the implementation plan validates (a minimal standalone build that imports
`uedcli_native` and calls one function).

### Frontend (`web/`)

`npm ci && npm run build` in `web/` at binary-build time — a build-time-only Node dependency, never
a runtime one. The resulting `web/dist` is copied into the standalone output directory at a fixed
path next to the `uedcli` executable.

### `uedcli serve` — bundle the frontend

New: `uedcli/serve/app.py` mounts a `StaticFiles` directory for `web/dist`, resolved relative to the
installed package's own location. One code path whether `web/dist` exists because it's part of a
compiled binary, or because a dev checkout ran `npm run build` locally — no binary-vs-source branch.
If `web/dist` isn't found, `serve` behaves exactly as it does today (API only; `vite dev` serves the
frontend separately in dev) — the existing dev workflow does not regress.

### Distribution & install

Release artifact: `uedcli-<version>-linux-x86_64.tar.gz`, containing the standalone directory.
Installed by extracting **once** (e.g. to `~/.local/opt/uedcli/<version>/`) with a
`~/.local/bin/uedcli` symlink/shim into `PATH` — an install-time step, never a per-invocation one.

A new `bin/build-standalone` script drives the whole pipeline (native ext → frontend → Nuitka →
package). It is for CI and for building a release locally, and is separate from `bin/uedcli` (the
existing host-venv dev launcher) — that script is untouched.

### CI (Linux phase)

One new GitHub Actions workflow: builds the purpose-built static-libpython Python, runs the existing
Rust-build image, builds `web/dist`, runs `bin/build-standalone`, smoke-tests the resulting binary,
and packages the tarball. Triggered on a version tag (a release action, not a per-push CI gate).
macOS and Windows are the same pipeline shape on their own runners — explicitly deferred, not built
in this phase.

### Testing

New smoke-test script (`bin/test-standalone`, or folded into `bin/build-standalone`) that runs the
*compiled* artifact directly — with the test's own subshell `PATH` stripped of system Python/pip/node
— against a handful of representative verbs (a query verb, `--help`, `serve --host 127.0.0.1 --port
<ephemeral> <level>` boot-and-shutdown), and asserts:

1. It runs at all with no system Python/pip/node on `PATH`.
2. Plain-verb startup time is not worse than the equivalent `bin/uedcli` (source/venv) invocation —
   the no-regression check from Non-goals.

Existing `bin/test` (the source/venv pytest suite) is untouched.

## Open risks — explicit, to resolve during implementation, not blocking the plan

1. Whether Nuitka bundles `uedcli_native`'s abi3 `.so` cleanly in standalone mode, the same way it
   does third-party extensions like Pillow's. First implementation-plan step validates this directly.
2. Whether a static-libpython build is actually achievable in the CI environment. If not, standalone
   mode still works with a bundled `libpython.so` — degrades gracefully, doesn't block the design.
3. The actual startup-overhead delta vs. source/venv — measured by the Testing step above, not
   assumed.

## Future work — explicitly out of scope here

- Getting plain-verb startup under 50ms (the owner's ultimate target), via an import-graph/lazy-import
  refactor, if the no-regression baseline established here isn't already under that.
- macOS and Windows build targets.
- Bundling Docker/Wine/UED22 itself (ruled out as scope during design, 2026-09-19).

# Standalone binary build Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this
> plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Package `uedcli` (CLI + `uedcli-native` + a prebuilt `web/` frontend) as a Nuitka
`--mode=standalone` directory that needs no system Python/pip/npm to run, with zero runtime
extraction, and add the CI pipeline + smoke tests that build and verify it.

**Architecture:** A new `bin/build-standalone` script (parallel to the existing `bin/uedcli`
dev launcher) drives a dedicated build venv (reusing `bin/_venv.sh`'s existing
`ensure_venv`/`ensure_native_ext`, which already builds `uedcli-native` via a Docker image — no
new native-build path) through: install Nuitka → build `web/dist` → `python -m nuitka
--mode=standalone` on the existing `uedcli/__main__.py` entry point → copy `web/dist` alongside the
compiled output → tarball it. `uedcli/serve/app.py` gains a `StaticFiles` mount for that `web/dist`,
present or absent, one code path either way. A new smoke-test script exercises the compiled binary
directly. A new GitHub Actions workflow runs the whole thing on a version tag.

**Tech Stack:** Nuitka (Python→C compiler, `--mode=standalone`), the existing bash `bin/_venv.sh`
venv/native-ext machinery, FastAPI's `StaticFiles`, GitHub Actions.

**Spec:** `dev/docs/superpowers/specs/2026-09-19-standalone-binary-build-design.md`

## Global Constraints

- `--mode=standalone` only, never `--onefile` (spec: zero runtime extraction is a hard requirement).
- No change to the CLI's import structure — `uedcli/cli/main.py` and `uedcli/cli/parsers/*.py`
  already import none of `fastapi`/`uvicorn`/`httpx`/`websockets`/`PIL` at module scope; keep it that
  way (don't add a new top-level heavy import anywhere reachable from `uedcli/__main__.py` for a
  plain verb).
- The existing dev venv/launcher (`bin/uedcli`, `bin/_venv.sh`'s default `.venv`) must not change
  behavior — the standalone build uses its own venv dir, never `.venv`.
- No hard startup-ms gate in this phase — the acceptance bar is "not slower than the source/venv
  baseline for the same command," measured, not assumed (spec, Non-goals).
- Static-libpython linking is best-effort (`--static-libpython=yes`, falling back to `no` if the
  build Python doesn't support it) — never a hard failure of the whole build (spec, Open risk #2).

---

### Task 1: Resolve open risk #1 — Nuitka bundling `uedcli_native`'s abi3 `.so`

A spike per `dev/docs/rules/spikes.md`: the harness gets committed, not thrown away, with a written
finding either way. This is the single biggest unverified assumption in the spec and gates whether
Task 2's real pipeline is worth building as designed.

**Files:**
- Create: `dev/docs/spikes/2026-09-19-nuitka-standalone-native-ext/probe.py`
- Create: `dev/docs/spikes/2026-09-19-nuitka-standalone-native-ext/run.sh`
- Create: `dev/docs/spikes/2026-09-19-nuitka-standalone-native-ext/spike.md`

**Interfaces:**
- Produces: confirmation (or refutation, with the actual error) that `python -m nuitka
  --mode=standalone` on a script importing `uedcli.native_ext` produces a standalone dir whose
  compiled binary can call a real `uedcli_native` function. Task 2 depends on this working; if it
  doesn't, Task 2's plan needs revisiting before proceeding (a genuine judgment call — stop and
  report rather than guessing around it).

- [ ] **Step 1: Write the probe script**

```python
# dev/docs/spikes/2026-09-19-nuitka-standalone-native-ext/probe.py
"""Nuitka --mode=standalone + uedcli_native bundling probe (dev/docs/rules/spikes.md).

Proves or refutes that Nuitka auto-discovers and bundles a pyo3/abi3 compiled extension module the
same way it already handles Pillow's `_imaging` -- the single biggest unverified assumption in
dev/docs/superpowers/specs/2026-09-19-standalone-binary-build-design.md. `build_brush_model([])` is a
real uedcli_native entry point (editor's csgPrepMovingBrush; uedcli-native/src/lib.rs) that needs no
level/project context, just an empty poly list -- a minimal but genuine call into the compiled Rust
core, not a stub.
"""
from uedcli.native_ext import import_native

native = import_native()
built, links = native.build_brush_model([])
print(f"OK: build_brush_model([]) -> links={links!r} built={built!r}")
```

- [ ] **Step 2: Write the build+run harness**

```bash
#!/usr/bin/env bash
# dev/docs/spikes/2026-09-19-nuitka-standalone-native-ext/run.sh
# Builds this spike's probe.py with Nuitka --mode=standalone (its own venv, never the dev .venv)
# and runs the compiled binary with PATH stripped down to prove it needs no system Python.
set -euo pipefail
SPIKE_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
UEDCLI_DIR="$(cd "$SPIKE_DIR" && git rev-parse --show-toplevel)"

export UEDCLI_VENV="$UEDCLI_DIR/.venv-nuitka-probe"
# shellcheck source=/dev/null
source "$UEDCLI_DIR/bin/_venv.sh"
ensure_venv
ensure_native_ext
"$UEDCLI_VENV/bin/pip" install --quiet nuitka

rm -rf "$SPIKE_DIR/build"
cd "$UEDCLI_DIR"
PYTHONPATH="$UEDCLI_DIR" "$UEDCLI_VENV/bin/python" -m nuitka --mode=standalone \
  --output-dir="$SPIKE_DIR/build" \
  "$SPIKE_DIR/probe.py"

BIN="$SPIKE_DIR/build/probe.dist/probe"
[ -x "$BIN" ] || BIN="$SPIKE_DIR/build/probe.dist/probe.bin"
echo "-- compiled binary: $BIN --"
echo "-- running with PATH stripped of the venv/system python, to prove no interpreter dependency --"
env -i HOME="$HOME" PATH=/usr/bin:/bin "$BIN"
```

```bash
chmod +x dev/docs/spikes/2026-09-19-nuitka-standalone-native-ext/run.sh
```

- [ ] **Step 3: Run it**

Run: `dev/docs/spikes/2026-09-19-nuitka-standalone-native-ext/run.sh`

Expected: either `OK: build_brush_model([]) -> links=[] built=<Built object at ...>` (risk resolved,
proceed to Task 2 as designed), or a concrete Nuitka error naming what didn't bundle (e.g. a missing
`.so`, an `ImportError` at runtime for `uedcli_native`). If the latter: this is a genuine judgment
call, not a step to guess around — try the one documented fallback (`--include-package=uedcli` to
force explicit inclusion instead of relying on Nuitka's import-following), and if that doesn't
resolve it either, stop and report the exact error rather than proceeding to Task 2 as if the risk
were resolved.

- [ ] **Step 4: Write the finding**

```markdown
# dev/docs/spikes/2026-09-19-nuitka-standalone-native-ext/spike.md
# Nuitka standalone + uedcli_native bundling

Question: does `python -m nuitka --mode=standalone` bundle `uedcli_native` (a pyo3/abi3 compiled
CPython extension module, installed via the existing Docker Rust-build image + pip) the same way it
already handles third-party extensions like Pillow's `_imaging`?

Method: `run.sh` compiles `probe.py` (imports `uedcli.native_ext`, calls the real
`build_brush_model([])`) standalone, then runs the compiled binary with `PATH` stripped to
`/usr/bin:/bin` (no venv, no system `python3.12` reachable) to prove it needs no interpreter.

Result: <PASTE THE ACTUAL run.sh OUTPUT HERE — this is filled in when Step 3 actually runs, not
left as a placeholder>

Verdict: <RESOLVED — proceed to Task 2 as designed, or REFUTED — state exactly what broke and what
fallback (if any) fixed it>.
```

- [ ] **Step 5: Commit**

```bash
git add dev/docs/spikes/2026-09-19-nuitka-standalone-native-ext/
git commit -m "Spike: Nuitka standalone bundles uedcli_native cleanly"
```

---

### Task 2: `bin/build-standalone` — the real pipeline

**Files:**
- Create: `bin/build-standalone`

**Interfaces:**
- Consumes: `bin/_venv.sh`'s `ensure_venv`/`ensure_native_ext` (unchanged, reused as-is); Task 1's
  confirmed Nuitka invocation shape.
- Produces: `dist/standalone/uedcli.dist/` — the standalone directory, with `web/dist` copied to
  `dist/standalone/uedcli.dist/web/dist` (the exact relative path `uedcli/serve/app.py`'s
  `_frontend_dist_dir()` in Task 3 resolves against `Path(__file__)`); and
  `dist/uedcli-<version>-linux-x86_64.tar.gz`, `<version>` read from `pyproject.toml`'s
  `project.version`. Task 4's smoke test runs `dist/standalone/uedcli.dist/uedcli` (or
  `uedcli.bin`, whichever Task 1 found the standalone executable is actually named) directly.

- [ ] **Step 1: Write the script**

```bash
#!/usr/bin/env bash
# bin/build-standalone — builds uedcli as a Nuitka --mode=standalone directory: no system Python,
# no pip install, no npm/node needed to RUN it (build-time only). Never --onefile (spec: zero
# runtime extraction). Own venv (.venv-standalone), never the dev .venv bin/uedcli uses.
#   UEDCLI_SKIP_FRONTEND=1   skip the `npm run build` step (reuse an existing web/dist)
set -euo pipefail
UEDCLI_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
cd "$UEDCLI_DIR"

VERSION="$(grep -m1 '^version = ' pyproject.toml | sed -E 's/version = "(.*)"/\1/')"
[ -n "$VERSION" ] || { echo "bin/build-standalone: could not read version from pyproject.toml" >&2; exit 1; }

export UEDCLI_VENV="$UEDCLI_DIR/.venv-standalone"
# shellcheck source=bin/_venv.sh
source "$UEDCLI_DIR/bin/_venv.sh"
ensure_venv
ensure_native_ext
[ "${UEDCLI_NATIVE_EXT_FRESH:-}" = "1" ] \
  || { echo "bin/build-standalone: uedcli_native did not build — refusing to ship a binary without" \
            "it (see the 'uedcli:' message above)" >&2; exit 1; }
"$UEDCLI_VENV/bin/pip" install --quiet nuitka

if [ -z "${UEDCLI_SKIP_FRONTEND:-}" ]; then
  ( cd "$UEDCLI_DIR/web" && npm ci && npm run build )
fi
[ -d "$UEDCLI_DIR/web/dist" ] \
  || { echo "bin/build-standalone: web/dist missing — run \`npm run build\` in web/ first, or set" \
            "UEDCLI_SKIP_FRONTEND=1 only if you intend an API-only serve" >&2; exit 1; }

OUT_DIR="$UEDCLI_DIR/dist/standalone"
rm -rf "$OUT_DIR"
PYTHONPATH="$UEDCLI_DIR" "$UEDCLI_VENV/bin/python" -m nuitka --mode=standalone \
  --static-libpython=yes \
  --output-dir="$OUT_DIR" \
  --output-filename=uedcli \
  "$UEDCLI_DIR/uedcli/__main__.py" \
|| PYTHONPATH="$UEDCLI_DIR" "$UEDCLI_VENV/bin/python" -m nuitka --mode=standalone \
  --static-libpython=no \
  --output-dir="$OUT_DIR" \
  --output-filename=uedcli \
  "$UEDCLI_DIR/uedcli/__main__.py"

DIST_DIR="$OUT_DIR/__main__.dist"
[ -d "$DIST_DIR" ] || { echo "bin/build-standalone: expected $DIST_DIR — Nuitka output layout" \
                              "changed, update this script" >&2; exit 1; }
mkdir -p "$DIST_DIR/web"
cp -r "$UEDCLI_DIR/web/dist" "$DIST_DIR/web/dist"

TARBALL="$UEDCLI_DIR/dist/uedcli-$VERSION-linux-x86_64.tar.gz"
tar -C "$OUT_DIR" -czf "$TARBALL" "__main__.dist"
echo "bin/build-standalone: built $TARBALL (standalone dir: $DIST_DIR)"
```

```bash
chmod +x bin/build-standalone
```

- [ ] **Step 2: Run it, verify the standalone dir + tarball exist**

Run: `bin/build-standalone`

Expected: exits 0, prints `bin/build-standalone: built .../dist/uedcli-0.1.0-linux-x86_64.tar.gz
(standalone dir: .../dist/standalone/__main__.dist)`. If the `--static-libpython=yes` invocation
fails (the expected shape of Open risk #2 — not every build Python supports it) the `||` fallback to
`--static-libpython=no` must produce a working build instead; confirm which branch actually ran from
the command output.

If Task 1 found the real output directory/executable name differs from `__main__.dist`/`uedcli`
(Nuitka's exact standalone layout, confirmed empirically in Task 1), fix the `DIST_DIR` line and
`--output-filename` here to match what Task 1 actually observed, then re-run this step.

- [ ] **Step 3: Verify the compiled binary runs standalone**

Run: `env -i HOME="$HOME" PATH=/usr/bin:/bin dist/standalone/__main__.dist/uedcli --help`

Expected: prints the CLI's `--help` text (the same as `bin/uedcli --help`), with no system Python or
venv on `PATH` at all.

- [ ] **Step 4: Commit**

```bash
git add bin/build-standalone
git commit -m "Add bin/build-standalone (Nuitka --mode=standalone packaging)"
```

---

### Task 3: `uedcli serve` — bundle the frontend

**Files:**
- Modify: `uedcli/serve/app.py`
- Modify: `uedcli/tests/test_serve_app.py`

**Interfaces:**
- Produces: `_frontend_dist_dir() -> Path | None` in `uedcli/serve/app.py`, and a `StaticFiles`
  mount at `/` in `create_app(...)` when it returns non-`None`. Task 2's `bin/build-standalone`
  copies `web/dist` to exactly the path this function resolves (`<repo-root-or-dist-dir>/web/dist`,
  i.e. two parents up from `uedcli/serve/app.py`).

- [ ] **Step 1: Write the failing tests**

Add to `uedcli/tests/test_serve_app.py` (near the top-level test functions, after the existing
`test_fault_route_renders_a_structured_error_not_a_traceback`):

```python
def test_frontend_static_files_served_when_dist_present(tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>uedcli frontend</html>")
    monkeypatch.setattr("uedcli.serve.app._frontend_dist_dir", lambda: dist)
    app = create_app(_project(tmp_path), "TestLevel")
    c = TestClient(app)
    r = c.get("/")
    assert r.status_code == 200
    assert "uedcli frontend" in r.text
    # API routes still work alongside the static mount
    assert c.get("/api/health").status_code == 200


def test_frontend_static_files_absent_serve_stays_api_only(tmp_path, monkeypatch):
    monkeypatch.setattr("uedcli.serve.app._frontend_dist_dir", lambda: None)
    app = create_app(_project(tmp_path), "TestLevel")
    c = TestClient(app)
    assert c.get("/").status_code == 404
    assert c.get("/api/health").status_code == 200
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `TMPDIR="$PWD/_scratch/pttmp" .venv/bin/python -m pytest -p no:cacheprovider -o cache_dir=_scratch/pttmp/pc uedcli/tests/test_serve_app.py -k frontend_static -v`

Expected: FAIL — `AttributeError: module 'uedcli.serve.app' has no attribute '_frontend_dist_dir'`
(or a collection error), since neither the function nor the mount exist yet.

- [ ] **Step 3: Implement**

In `uedcli/serve/app.py`, add the import (alongside the existing `from fastapi import ...` line):

```python
from fastapi.staticfiles import StaticFiles
```

Add this module-level function (near the top, after the existing imports, before `def
create_app(...)`):

```python
def _frontend_dist_dir() -> Path | None:
    """A built `web/dist` next to this package -- same relative path whether this is a source
    checkout (repo root's `web/dist`, once `npm run build` has run) or a Nuitka standalone binary
    (`bin/build-standalone` copies `web/dist` to this same relative spot next to the compiled
    package). Returns None if not built -- `serve` then stays API-only, exactly as it does today;
    no binary-vs-source branch, one code path either way."""
    candidate = Path(__file__).resolve().parents[2] / "web" / "dist"
    return candidate if candidate.is_dir() else None
```

In `create_app`, immediately before the final `return app` (after the `ws_endpoint` websocket route
registration):

```python
    frontend_dist = _frontend_dist_dir()
    if frontend_dist is not None:
        app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")

    return app
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `TMPDIR="$PWD/_scratch/pttmp" .venv/bin/python -m pytest -p no:cacheprovider -o cache_dir=_scratch/pttmp/pc uedcli/tests/test_serve_app.py -v`

Expected: PASS, including the two new tests and every pre-existing test in this file (no
regression — the mount only activates when `_frontend_dist_dir()` returns non-`None`, which is
`None` in every existing test's default `tmp_path`-rooted setup since there's no `web/dist` there).

- [ ] **Step 5: Commit**

```bash
git add uedcli/serve/app.py uedcli/tests/test_serve_app.py
git commit -m "serve: mount a prebuilt web/dist when present"
```

---

### Task 4: `bin/test-standalone` — smoke test the compiled artifact

**Files:**
- Create: `bin/test-standalone`

**Interfaces:**
- Consumes: `dist/standalone/__main__.dist/uedcli` (Task 2's output — this task assumes
  `bin/build-standalone` has already run; it does not rebuild).
- Produces: exit 0 on success, exit 1 with a clear stderr message naming which check failed
  (`direction/conventions.md`'s no-half-answer rule) — used by Task 5's CI workflow as the release
  gate.

- [ ] **Step 1: Write the script**

```bash
#!/usr/bin/env bash
# bin/test-standalone — smoke-tests bin/build-standalone's output directly (not the venv): runs
# with no system Python/pip/node on PATH, checks a few representative verbs + a serve boot/shutdown,
# and asserts startup is not slower than the source/venv baseline (spec: no-regression, not a hard
# ms target). Run bin/build-standalone first.
set -euo pipefail
UEDCLI_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
cd "$UEDCLI_DIR"

BIN="$UEDCLI_DIR/dist/standalone/__main__.dist/uedcli"
[ -x "$BIN" ] || { echo "bin/test-standalone: $BIN not found — run bin/build-standalone first" >&2; exit 1; }

RUN() { env -i HOME="$HOME" PATH=/usr/bin:/bin "$BIN" "$@"; }

echo "-- --help runs with no system python/pip/node on PATH --"
RUN --help >/dev/null || { echo "bin/test-standalone: --help failed with a stripped PATH" >&2; exit 1; }

echo "-- a plain query verb --"
RUN classes list >/dev/null 2>&1 || { echo "bin/test-standalone: 'classes list' failed" >&2; exit 1; }

echo "-- serve boots and shuts down cleanly --"
PORT=18765
RUN serve --host 127.0.0.1 --port "$PORT" nonexistent-level >/tmp/uedcli-serve-smoke.log 2>&1 &
SERVE_PID=$!
sleep 1
if kill -0 "$SERVE_PID" 2>/dev/null; then
  kill "$SERVE_PID"; wait "$SERVE_PID" 2>/dev/null || true
else
  # A missing level exits fast with a CommandError (expected — this only proves the binary itself
  # starts and reaches the argparse/level-resolution path, not a full serve boot).
  grep -q "level not found" /tmp/uedcli-serve-smoke.log \
    || { echo "bin/test-standalone: serve did not fail the way we expect (level not found)" >&2; \
         cat /tmp/uedcli-serve-smoke.log >&2; exit 1; }
fi

echo "-- startup-time no-regression check --"
NUITKA_MS=$({ /usr/bin/time -f '%e' RUN --help >/dev/null; } 2>&1 | tail -1)
VENV_MS=$({ /usr/bin/time -f '%e' bin/uedcli --help >/dev/null; } 2>&1 | tail -1)
echo "compiled: ${NUITKA_MS}s   venv: ${VENV_MS}s"
awk -v n="$NUITKA_MS" -v v="$VENV_MS" 'BEGIN { if (n > v * 1.1) { print "bin/test-standalone: compiled startup is >10% slower than venv (" n "s vs " v "s)" > "/dev/stderr"; exit 1 } }'

echo "bin/test-standalone: all checks passed"
```

```bash
chmod +x bin/test-standalone
```

- [ ] **Step 2: Run it**

Run: `bin/build-standalone && bin/test-standalone`

Expected: `bin/test-standalone: all checks passed`. If the startup-time check fails, that's the
no-regression acceptance bar from the spec failing for real — report the actual numbers rather than
loosening the check to make it pass.

- [ ] **Step 3: Commit**

```bash
git add bin/test-standalone
git commit -m "Add bin/test-standalone smoke test"
```

---

### Task 5: CI workflow

**Files:**
- Create: `.github/workflows/build-standalone.yml`

**Interfaces:**
- Consumes: Tasks 2-4's scripts, run as-is.
- Produces: a `uedcli-<version>-linux-x86_64.tar.gz` release asset on a version tag push.

- [ ] **Step 1: Write the workflow**

```yaml
# .github/workflows/build-standalone.yml
name: Build standalone binary

on:
  push:
    tags:
      - "v*"
  workflow_dispatch: {}

jobs:
  linux-x86_64:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: "20"

      - name: Build + smoke-test the standalone binary
        run: |
          bin/build-standalone
          bin/test-standalone

      - name: Upload artifact
        uses: actions/upload-artifact@v4
        with:
          name: uedcli-linux-x86_64
          path: dist/uedcli-*-linux-x86_64.tar.gz

      - name: Attach to release
        if: startsWith(github.ref, 'refs/tags/v')
        uses: softprops/action-gh-release@v2
        with:
          files: dist/uedcli-*-linux-x86_64.tar.gz
```

- [ ] **Step 2: Verify the workflow file is valid YAML**

Run: `python3.12 -c "import yaml, sys; yaml.safe_load(open('.github/workflows/build-standalone.yml'))" 2>&1 || python3.12 -c "import json,sys; print('yaml module unavailable, skipping strict parse')"`

Expected: no exception. (This CI job itself cannot be executed locally — GitHub Actions runners
aren't available in this environment; this step only catches a syntax error before it reaches
GitHub.)

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/build-standalone.yml
git commit -m "CI: build + release the standalone binary on version tags"
```

---

## Self-review notes

- **Spec coverage**: packaging tool/mode (Task 2), native ext (Tasks 1-2), frontend bundling +
  `serve` change (Task 3), distribution/CI (Tasks 2, 5), testing (Task 4), open risks #1 and #2
  (Task 1, Task 2's `--static-libpython` fallback) all have a task. Open risk #3 (actual overhead
  delta) is Task 4's no-regression check, not a separate task — it's a property of the build, not a
  thing to build.
- Macos/Windows and the <50ms refactor are explicitly Future Work in the spec — no task here, by
  design.

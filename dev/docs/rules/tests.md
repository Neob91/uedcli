# Tests

Run the offline suite through the **`bin/test`** wrapper — it runs pytest
HOST-NATIVE in the auto-managed dev venv (`bin/_venv.sh`, `.venv/`,
Python 3.12 + `Pillow`/`pytest`), the same runtime `bin/uedctl` uses. It
needs `python3.12` on PATH (pyenv provides it here); the venv self-creates
on first run. Extra args pass straight through (invoke it path-qualified —
`test` alone is a shell builtin):
```
bin/test                 # whole offline suite, from the repo root
bin/test -k preview -x
```
Integration tests (`-m integration`) require the live `dx-lum-uned`
container and are deselected by default (`pytest.ini`).

**`bin/test` runs TWO suites:** pytest, then `cargo test` in `uedctl-native/`
(the Rust PyO3 extension). The Rust half is **optional** — if `cargo` is
missing, or `UEDCTL_SKIP_NATIVE=1` is set, it warns and skips, and the Python
tests that need the extension `importorskip("uedctl_native")` themselves. So a
green run on a machine without cargo means **less was tested than it looks**:
`level materialize --native` and `preview --native` were not exercised. See
`../dev-runtime.md` for the build gating and the `UEDCTL_VENV*` knobs.

**uedctl itself runs host-native too** (via `bin/uedctl` → the same venv),
NOT inside a container — mirroring the eventual Nuitka release binary, so it
has native filesystem access to the game's asset dirs and needs no
bind-mounting of external roots into a dev container. Only the editor/build
containers it drives run under Docker. (The old Python-3.12 *dev image* +
`_dev-run.sh` were retired 2026-07-14 — decisions.md "venv for dev".)

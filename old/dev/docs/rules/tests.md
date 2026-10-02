# Tests

Run the offline suite through the `bin/test` wrapper. It runs pytest HOST-NATIVE in an auto-managed
`python3.12` venv, then the Rust `cargo test` goldens in a container (Rust isn't on most hosts, so
only that step is containerized — the same image builds `uedcli_native` into the venv). The host needs
`python3.12` on PATH and Docker; the venv + the native ext self-provision on first run. Extra args pass
through (invoke it path-qualified — `test` alone is a shell builtin):
```
bin/test                 # whole offline suite (pytest + cargo test)
bin/test -k preview -x
```
Integration tests (`-m integration`) require the live editor RUNTIME container, and real-corpus
`-m slow` tests (e.g. the retail Unreal Gold map import) are both deselected by default
(`pytest.ini`); run either explicitly with `bin/test -m integration` / `bin/test -m slow`.

The default (no-args) run is parallelized (`pytest-xdist`, `-n 4 --dist=loadfile`, override worker
count with `UEDCLI_TEST_WORKERS`) on a private per-invocation `TMPDIR` under `/tmp` — cuts the suite
from ~26 min to ~2 min. An explicit-args invocation (`bin/test -k ...`, `-m integration`) stays
serial on the OS default `TMPDIR`.

The Rust goldens run every time (the container supplies cargo + `libpython`), so a green run exercises
the native `uedcli_native` core — `level materialize` and `photo` native paths — not just the
Python. `UEDCLI_SKIP_NATIVE=1` skips the extension build + `cargo test` for a pytest-only run (the
native pytest tests `importorskip("uedcli_native")`). See `../dev-runtime.md` for the build mechanics
and the `UEDCLI_VENV*` knobs.

uedcli itself runs host-native too (via `bin/uedcli`, the same venv), so it has native asset-dir
access and reaches the docker daemon directly to drive the editor/game RUNTIME containers.
`../direction/process.md` "host-native; only the Rust build is containerized".

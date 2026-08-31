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
Integration tests (`-m integration`) require the live editor RUNTIME container and are deselected by
default (`pytest.ini`).

The Rust goldens run every time (the container supplies cargo + `libpython`), so a green run exercises
the native `uedcli_native` core — `level materialize` and `photo` native paths — not just the
Python. `UEDCLI_SKIP_NATIVE=1` skips the extension build + `cargo test` for a pytest-only run (the
native pytest tests `importorskip("uedcli_native")`). See `../dev-runtime.md` for the build mechanics
and the `UEDCLI_VENV*` knobs.

uedcli itself runs host-native too (via `bin/uedcli`, the same venv), so it has native asset-dir
access and reaches the docker daemon directly to drive the editor/game RUNTIME containers.
`../direction/process.md` "host-native; only the Rust build is containerized".

# Tests

Run the offline suite through the `bin/test` wrapper. It runs pytest, then
`cargo test` in `uedcli-native/` (the Rust PyO3 extension), INSIDE the
long-running dev container (Rust + Python + deps), `docker exec`'d into — the
same container `bin/uedcli` uses. The container builds on first run and the repo
is identity-mounted, so the host needs only Docker (no `python3.12`, cargo, or
`libpython` on PATH). Extra args pass through (invoke it path-qualified —
`test` alone is a shell builtin):
```
bin/test                 # whole offline suite (pytest + cargo test), in the container
bin/test -k preview -x
```
Integration tests (`-m integration`) require the live editor RUNTIME container
and are deselected by default (`pytest.ini`).

The Rust goldens run every time (cargo is in the container), so a green run
exercises the native `uedcli_native` core — including `level materialize` and
`preview` native paths — not just the Python. `UEDCLI_SKIP_NATIVE=1` skips the
extension build + `cargo test` for a pytest-only run (the native pytest tests
`importorskip("uedcli_native")`). `UEDCLI_DEV_REBUILD=1` forces an image rebuild;
`UEDCLI_DEV_MOUNTS="/a /b"` identity-mounts extra host dirs (asset roots) into the
container. See `../dev-runtime.md` for the container mechanics and knobs.

uedcli itself runs in the same dev container (via `bin/uedcli`, as the invoking
uid so its outputs are yours, not root's). The repo is identity-mounted, so
uedcli's paths are the same inside the container as on the host — it never
branches on "am I in a container?". The editor/game RUNTIME containers it drives
run on the host via the mounted docker socket. `../direction/process.md`
"dev container".

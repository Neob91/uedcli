# Dev runtime: how uedcli runs during development

uedcli — the CLI and its pytest suite — runs HOST-NATIVE in an auto-managed `python3.12` venv. Python
3 is on most hosts; what isn't is Rust, so the ONE thing that needs a container is building the
`uedcli_native` extension: it is built as an abi3 wheel in a Rust+`libpython` image and `pip`-installed
into the venv, and the `cargo test` goldens run in that image too. Host-native means the CLI has native
access to asset dirs and reaches the docker daemon directly to drive the editor/game RUNTIME
containers. Host needs only `python3.12` on PATH + Docker with the `buildx` plugin (bundled by
default in Docker 23+/Desktop) — no Rust. Owner ruling 2026-08-06; [`direction/process.md`](direction/process.md).

## The pieces

| Path | Role |
|------------------------------|---
| `bin/_venv.sh` | sourced helper: `ensure_venv` finds `python3.12`, creates `.venv/`, installs `Pillow`+`pytest`. `ensure_native_ext` builds `uedcli_native` via `docker buildx build` and pip-installs the wheel (source-hash-gated), exporting `UEDCLI_NATIVE_EXT_FRESH=1`/`0` for `uedcli.native_ext.import_native` (every `uedcli_native` call site) to refuse a confirmed-stale build rather than silently running old compiled code — owner ruling 2026-09-11. `run_cargo_test` runs the goldens the same way. |
| `bin/uedcli` | runs the CLI host-native through the venv (`ensure_venv` + `ensure_native_ext`). |
| `bin/test` | host-native pytest through the venv, then `run_cargo_test` — see [`rules/tests.md`](rules/tests.md). |
| `dev-container/Dockerfile` | the Rust-BUILD image `uedcli-rust-build`: `python:3.12` + Rust (rustup) + `build-essential` + maturin. Not a run env; the base every actual build/test run FROMs. |
| `dev-container/build.Dockerfile` | the actual build: `COPY`s the crate in as build context, `RUN`s `cargo test`/`maturin build` against a `RUN --mount=type=cache` target dir, exports the wheel via a `scratch` stage. Two `buildx --target`s: `test`, `wheel-export`. |
| `uedcli-native/` | the Rust PyO3 extension; built with `maturin build` → wheel → pip-installed. |
| `.venv/` | gitignored; self-creates. |

The build is driven by `docker buildx build`, never `docker run -v` — a bind mount needs the
source path to exist on the DAEMON's own filesystem, which a remote/sibling daemon (Docker
reached via `DOCKER_HOST`, not local) has no way to see. `buildx`'s context upload and its local
exporter both go over the same client↔daemon connection a plain `docker build` already uses, so
neither needs a shared filesystem. Cargo's own incremental target dir persists across builds via
a `RUN --mount=type=cache` (locked, since more than one build can hit the same daemon at once) —
this is what keeps a warm rebuild fast without a bind-mounted host directory to cache into.

The native ext builds automatically on `bin/test`/`bin/uedcli`, so `level materialize` native and the
`cargo test` goldens run on every host with Docker — no "cargo absent, silently skipped" gap.
`UEDCLI_SKIP_NATIVE=1` skips the build + `cargo test`. The Python side has one third-party runtime
dependency, Pillow (texture-catalog PCX decode), and targets one interpreter version (3.12).

| Env knob | Effect |
|-------------------------------|---
| `UEDCLI_VENV=<dir>` | put the venv somewhere other than `.venv/` |
| `UEDCLI_VENV_REBUILD=1` | force a venv dependency reinstall |
| `UEDCLI_SKIP_NATIVE=1` | skip the Rust build *and* `cargo test` |

## Usage

```bash
bin/uedcli level status
printf '%s' "$t3d" | bin/uedcli actor add -    # stdin piping works

bin/test                                       # whole offline suite (pytest + cargo)
bin/test -k texture -x                         # args pass through to pytest
```

Invoke both path-qualified from the repo root — `test` alone is a shell builtin. To put the CLI on
`PATH`: `ln -s "$PWD/bin/uedcli" ~/.local/bin/uedcli`. A fresh checkout's first `bin/test` pays the
one-time venv + Rust-build-image + native-extension build.

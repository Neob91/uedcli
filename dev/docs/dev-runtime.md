# Dev runtime: how uedcli runs during development

uedcli — the CLI and its test suite — runs inside a long-running dev container (Rust + Python +
deps), `docker exec`'d into so each call is cheap. The repo is identity-mounted (same path inside the
container as on the host), so uedcli's paths are container-agnostic. Only Docker is required on the
host — no `python3.12`, cargo, or `libpython` on `PATH`. The editor/game RUNTIME containers uedcli
*drives* are separate and reached via the mounted host docker socket. Owner ruling 2026-08-06;
[`direction/process.md`](direction/process.md) "dev container".

## The pieces

| Path | Role |
|------------------------------|---
| `dev-container/Dockerfile` | the dev image `uedcli-dev`: `python:3.12` + Rust (rustup) + `build-essential`/`git` + `Pillow`/`pytest`/`maturin` + the docker client. arm64/amd64-native (no emulation). |
| `bin/_dev-container.sh` | sourced helper: builds the image on first use / when the Dockerfile changes, starts the long-running container (identity-mounting the repo, the git common dir, the docker socket, and `UEDCLI_DEV_MOUNTS`), and builds `uedcli_native` into it. `dev_exec` runs a command inside it. |
| `bin/uedcli` | runs the CLI in the container **as the invoking uid**, so its outputs are yours, not root's, at your current dir (which must be under a mounted path). |
| `bin/test` | runs pytest then `cargo test` in the container via `dev-container/run-tests.sh` — see [`rules/tests.md`](rules/tests.md). |
| `uedcli-native/` | the Rust PyO3 extension (`uedcli_native`), built with `maturin build` + `pip install` into the container's interpreter, source-hash-gated. |

Build/cache writes stay container-internal (`CARGO_TARGET_DIR`, `PYTHONPYCACHEPREFIX`, pytest
`cache_dir=/tmp`), so the root-run container leaves no root-owned artifacts in the identity-mounted
repo.

The Rust extension builds automatically (`ensure_dev_container` → `_ensure_native_ext`), so `level
materialize` native and the `cargo test` goldens run on every host — no "cargo absent, silently
skipped" gap. `UEDCLI_SKIP_NATIVE=1` skips the build + `cargo test` for a pytest-only run (the native
pytest tests `importorskip("uedcli_native")`).

The Python side has one third-party runtime dependency, Pillow (texture-catalog PCX decode), and
carries no compatibility shims — it targets one interpreter version (3.12).

| Env knob | Effect |
|-------------------------------|---
| `UEDCLI_DEV_MOUNTS="/a /b"` | identity-mount extra host dirs (asset roots) into the container |
| `UEDCLI_DEV_REBUILD=1` | force a dev-image rebuild |
| `UEDCLI_SKIP_NATIVE=1` | skip the Rust build *and* `cargo test` |

## Usage

```bash
bin/uedcli level status
printf '%s' "$t3d" | bin/uedcli actor add -    # stdin piping works

bin/test                                       # whole offline suite (pytest + cargo)
bin/test -k texture -x                         # args pass through to pytest
```

Invoke both path-qualified from the repo root — `test` alone is a shell builtin. To put the CLI on
`PATH`: `ln -s "$PWD/bin/uedcli" ~/.local/bin/uedcli`. The first `bin/test`/`bin/uedcli` in a fresh
checkout pays the one-time image build + native-extension build.

Each checkout (the main checkout or a worktree) gets its own long-running container, keyed by the
repo path, so parallel sessions do not collide.

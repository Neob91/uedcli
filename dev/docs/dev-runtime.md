# Dev runtime: how uedcli runs during development

uedcli runs host-native, in an auto-managed Python 3.12 virtualenv. It is not containerised.
Only the editor/build containers it drives run under Docker.

> Superseded 2026-07-14. This doc previously described a `uedcli-dev` Docker image, a
> `bin/_dev-run.sh` launcher, docker-out-of-docker socket mounting, and a persistent container
> driven by `docker exec`. That runtime was retired; `docker/Dockerfile` and `bin/_dev-run.sh`
> exist only in git history. Reason: uedcli needs native filesystem access to the game's asset
> dirs wherever they live, and bind-mounting arbitrary host roots into a dev container could
> shadow or clobber the container's own dirs. Running on the host also mirrors the eventual
> release binary.

## The pieces

| Path | Role |
|------------------|---
| `bin/_venv.sh` | sourced helper: finds `python3.12`, creates `.venv/` on first use, installs `Pillow` + `pytest`. Defines `ensure_native_ext` but does not call it. |
| `bin/uedcli` | runs the CLI through that venv. Calls `ensure_venv` only — it does not build the Rust extension. |
| `bin/test` | calls `ensure_native_ext`, runs pytest through the same venv, then `cargo test` in `uedcli-native/` — see [`rules/tests.md`](rules/tests.md). |
| `uedcli-native/` | the Rust PyO3 extension (`uedcli_native`), built into the venv with `maturin develop --release`. |
| `.venv/` | gitignored; self-creates, so a fresh checkout needs no setup step. |

Requirements: `python3.12` on `PATH` (pyenv provides it here), and `cargo` if you need the
native paths. The Python side has one third-party runtime dependency, Pillow (texture-catalog
PCX decode), and carries no compatibility shims — no `tomllib`→`tomli` fallback, no 3.10
support. It targets one interpreter version.

`bin/test` is the only thing that builds the extension. On a fresh checkout,
`bin/uedcli level materialize --native` will not compile it first — `uedcli/native/materialize.py`
swallows the `ImportError` and falls back. Run `bin/test` once before expecting a native path to
work.

The Rust extension is optional. `ensure_native_ext` is source-hash-gated on `Cargo.toml` +
`src/*.rs`; if `cargo` is absent it warns and returns success, so a docs-only or pure-Python
change still runs the suite. The native tests `importorskip("uedcli_native")` and `bin/test`
skips `cargo test` with a message. So without cargo, part of the suite silently does not run —
`level materialize --native` and `preview --native` depend on that extension.

| Env knob | Effect |
|-----------------------|---
| `UEDCLI_VENV=<dir>` | put the venv somewhere other than `.venv/` |
| `UEDCLI_VENV_REBUILD=1` | force a dependency reinstall |
| `UEDCLI_SKIP_NATIVE=1` | skip the Rust build *and* `cargo test` entirely |

## Usage

```bash
bin/uedcli level status
printf '%s' "$t3d" | bin/uedcli actor add -    # stdin piping works (raw, no TTY mangling)

bin/test                                       # whole offline suite
bin/test -k texture -x                         # args pass through to pytest
```

Invoke both path-qualified from the repo root — `test` alone is a shell builtin, so `bin/test` is
required. To put the CLI on `PATH`: `ln -s "$PWD/bin/uedcli" ~/.local/bin/uedcli`.

A fresh worktree has no `.venv/` (gitignored), so the first `bin/test` there pays the
venv-creation cost once.

## Releases (deferred)

The release artifact is intended to be a Nuitka-compiled standalone binary: one executable with
the Python runtime, Pillow, and the compiled `uedcli_native` extension baked in, so an end user
runs `uedcli` with nothing installed — no Docker, no Python, no cargo. Building it (and deciding
how the editor-driving verbs' Docker dependency is handled) is an open board item. The
host-native venv stands in for that binary during development.

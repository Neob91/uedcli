# Dev runtime: how uedctl runs during development

uedctl runs **host-native**, in an auto-managed Python 3.12 virtualenv. It is **not** containerised.
Only the editor/build containers it *drives* run under Docker.

> **Superseded 2026-07-14.** This doc previously described a `uedctl-dev` Docker image, a
> `bin/_dev-run.sh` launcher, docker-out-of-docker socket mounting, and a persistent container
> driven by `docker exec`. **That runtime was retired and both files are gone**
> (`docker/Dockerfile`, `bin/_dev-run.sh`) — they exist only in git history. The reason: uedctl
> needs native filesystem access to the game's asset dirs wherever they live, and bind-mounting
> arbitrary host roots into a dev container could shadow or clobber the container's own dirs.
> Running on the host also mirrors the eventual release binary.

## The pieces

| Path | Role |
|-----------------|---
| `bin/_venv.sh` | sourced helper: finds `python3.12`, creates `.venv/` on first use, installs `Pillow` + `pytest`. |
| `bin/uedctl` | runs the CLI through that venv. |
| `bin/test` | runs pytest through the same venv — see [`rules/tests.md`](rules/tests.md). |
| `.venv/` | gitignored; self-creates, so a fresh checkout needs no setup step. |

**Requirement:** `python3.12` on `PATH` (pyenv provides it here). uedctl is pure Python 3.12 with
one third-party runtime dependency, **Pillow** (texture-catalog PCX decode), and carries **no
compatibility shims** — no `tomllib`→`tomli` fallback, no 3.10 support. That is deliberate: the code
targets one interpreter version and stays clean.

## Usage

```bash
bin/uedctl level status
printf '%s' "$t3d" | bin/uedctl actor add -    # stdin piping works (raw, no TTY mangling)

bin/test                                       # whole offline suite
bin/test -k texture -x                         # args pass through to pytest
```

Invoke both path-qualified from the repo root — `test` alone is a shell builtin, so `bin/test` is
not optional spelling. To put the CLI on `PATH`:
`ln -s "$PWD/bin/uedctl" ~/.local/bin/uedctl`.

A fresh worktree has no `.venv/` (it is gitignored), so the first `bin/test` there pays the
venv-creation cost once.

## Releases (deferred)

The release artifact is intended to be a **Nuitka**-compiled standalone binary: a single executable
with the Python runtime and Pillow baked in, so an end user runs `uedctl` with nothing installed —
no Docker, no Python. Building it (and deciding how the editor-driving verbs' Docker dependency is
handled for a standalone binary) is an open board item. The host-native venv is what stands in for
that binary during development, which is part of why the dev path mirrors it.

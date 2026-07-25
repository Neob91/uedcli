# Dev runtime: running uedctl without host-installed deps

uedctl is **pure Python 3.12** (`pyproject`: `requires-python >=3.12`) with exactly one
third-party runtime dependency, **Pillow** (texture-catalog PCX decode). It contains **no
compatibility shims** — no `tomllib`→`tomli` fallback, no 3.10 support. That is deliberate: the
code targets one interpreter version and stays clean.

The consequence is that a developer host running an older Python (e.g. 3.10, which lacks the
stdlib `tomllib` uedctl imports) **cannot run uedctl natively**. Rather than pollute the host
with a pyenv/venv/3.12 install, the dev loop runs uedctl **inside a Docker container** that
carries the right interpreter. The host needs only Docker.

*(This is the DEV path. The intended RELEASE path is a standalone **Nuitka**-compiled binary —
one self-contained executable, no interpreter or deps on the target machine. That is not built
yet; it is tracked on the board. See "Releases" below.)*

## The pieces

| File | Role |
|---|---|
| `docker/Dockerfile` | builds the `uedctl-dev` image: `python:3.12-slim` + Pillow + `pytest` (dev/test) + the docker CLI/compose plugin + `git`. |
| `bin/_dev-run.sh` | sourced helper: locates the repo, builds the image on demand, assembles the `docker run` invocation. |
| `bin/uedctl` | the launcher — runs `python -m uedctl "$@"` in the image. Put its dir on `PATH` (or symlink into `~/.local/bin`). |
| `bin/test` | runs the offline unit suite (`pytest`) in the same image (this host has no other 3.12). Invoke path-qualified (`bin/test`) — `test` alone is a shell builtin. |

The uedctl **source is not baked into the image** — `bin/_dev-run.sh` mounts the checkout at
runtime and sets `PYTHONPATH`, so editing uedctl code needs **no rebuild**. The image is rebuilt
only when `docker/Dockerfile` itself changes (detected via a `sha256` label the launcher compares)
or when forced with `UEDCTL_DEV_REBUILD=1`.

### Persistent container + `docker exec` (why it's not `docker run` per command)

`docker run --rm` per command costs **~2s** (container create + start + teardown) — unacceptable for
an interactive CLI. Instead `bin/_dev-run.sh` keeps **one long-lived idle container per checkout**
(`uedctl-run-<hash>`, running `sleep infinity`, mounts baked once) and enters it per command with
`docker exec` (**~0.4s**). Only the per-command working dir and a few `UEDCTL_*` env knobs vary, and
those ride on `docker exec -w/-e`.

The hot path is a **single** `docker inspect` that checks the container is running *and* was built
from the current Dockerfile (a `uedctl.dockerfile-sha` label baked at create). On a mismatch — image
rebuilt, container missing/stopped, or `UEDCTL_DEV_REBUILD=1` — it rebuilds the image and recreates
the container; otherwise it `exec`s straight in. The container is keyed on `(repo root, home, uid)`,
so separate checkouts get separate containers and every command from one checkout shares one warm
container.

Teardown: it's a harmless idle container; remove it with
`docker rm -f $(docker ps -aq --filter name=uedctl-run-)`. It auto-recreates on the next command.

> **Remaining latency is uedctl's own import chain, not the wrapper.** With a warm container a command
> is ~2s, of which ~0.4s is `docker exec`, ~0.6s is Python+site startup, and **~1s is uedctl eagerly
> importing its whole verb tree** (`dispatch` imports every verb module at load; `cli.main` imports
> `dispatch` unconditionally) even for a trivial verb like `level select`. Lazy-loading per-verb
> imports is a tracked uedctl-code optimization (board `inbox.md`), independent of this wrapper.

## How the container reaches the host (the two design points)

uedctl's *model-side* verbs (`level status`, `actor find`, …) are pure file compute and need
nothing special. Its *editor-driving* verbs (`level materialize`, `level preview`) shell out to
`docker`/`docker compose` to spawn **sibling** editor containers. Two mechanics make that work
from inside a container:

1. **Docker-out-of-docker.** The host's `/var/run/docker.sock` is bind-mounted in, and the docker
   CLI in the image talks to it — so "sibling" editor containers are created on the **host**
   daemon, not nested. `bin/_dev-run.sh` honors `DOCKER_HOST` (incl. rootless unix sockets) and
   adds the socket's group so the non-root container user can use it.
2. **Identity path-mapping.** The repo root and `~/.uedctl` are mounted at the **same absolute
   path** inside the container as on the host. So every host path uedctl computes is valid both
   for its own file I/O *and* as a `docker run -v <hostpath>:…` argument to a sibling container
   (whose mounts resolve on the host daemon). Without this, in-container paths wouldn't exist on
   the host and sibling mounts would silently break.

The container runs as the **host uid:gid** (`--user`) so anything written into the repo or caches
is user-owned, not root.

> **Security note.** Mounting the docker socket means anything running in `uedctl-dev` can start a
> privileged sibling container and reach host root. Treat the image as a convenience runtime, not
> a sandbox.

## Known caveats (editor-driving path)

These do **not** affect model-side verbs; they are open items for the editor path under the
wrapper (tracked on the board — `dev/docs/board/inbox.md`):

- **Sibling editor containers run as root.** `editor.py`'s `docker compose run` does not pass
  `--user`, so files those containers write into mounted host paths (e.g. `~/.uedctl/cache/stubs`,
  editor scratch) become **root-owned** — which can then block the host user / the `--user` dev
  container from rewriting them. If you hit `Permission denied` under `~/.uedctl`, a stale
  root-owned tree from an earlier editor/stub run is the cause; `sudo chown -R "$USER":"$USER"
  ~/.uedctl` clears it. The real fix (run editor containers as the host user, or make the caches
  tolerate it) is not done yet.
- **Only the repo + `~/.uedctl` are identity-mounted.** Once per-game base-asset `paths` outside
  the repo are wired into materialize (config.py's `[games.*]`), those roots will also need
  identity mounts.

## Usage

```bash
# put the launcher on PATH once
export PATH="$PWD/Tools/uedctl/bin:$PATH"     # or: ln -s .../bin/uedctl ~/.local/bin/uedctl

uedctl level status
printf '%s' "$t3d" | uedctl actor add -        # stdin piping works (raw, no TTY mangling)

bin/test                                       # whole offline suite
bin/test -k texture -x                         # args pass through to pytest

UEDCTL_DEV_REBUILD=1 uedctl level status       # force an image rebuild
```

First run builds the image (~1–2 min) and starts the persistent container; subsequent commands are a
`docker exec` into it (~0.4s of Docker overhead, plus uedctl's own startup — see above).

## Releases (deferred)

The release artifact is intended to be a **Nuitka**-compiled standalone binary: a single
executable with the Python runtime and Pillow baked in, so an end user runs `uedctl` with nothing
installed — no Docker, no Python. This wrapper is strictly the developer loop; it is not shipped.
Building the Nuitka release (and deciding how the editor-driving verbs' Docker dependency is
handled for a standalone binary) is an open board item.

+++
priority = "p2"
kind = "debug"
summary = "setup-game-preview.sh step 1 (dx-lum-uned build) untested on a fresh arm64 host"
+++

# setup-game-preview.sh step 1 (dx-lum-uned build) untested on a fresh arm64 host

On branch `andrzej/p1/game-preview-generic`, `dev/scripts/setup-game-preview.sh` builds the
`dx-lum-uned` base image in step 1 if absent. On this box the image already existed, so steps 2–5
and a full `level preview --game` render were verified end to end, but **step 1's build was never
exercised here**.

The amd64 wiring is sound but unverified on a clean build: `uned/Dockerfile` is `FROM
debian:bookworm-slim` (multi-arch) with no `platform:` in `uned/docker-compose.yml`, and step 1
exports `DOCKER_DEFAULT_PLATFORM=linux/amd64`, so `docker compose build` should produce an amd64
`dx-lum-uned:latest` that runs under qemu on arm64 — the same emulation the running images already
use. Verify on a fresh arm64 host that this build completes and the resulting base boots wine.

Also noticed (orthogonal, not from this change): `bin/test` cannot run on this host — the
`uedcli-native` Rust extension fails to link (`cannot find -lpython3.12`). The Python suite itself is
fine (`.venv/bin/python -m pytest uedcli/tests/test_preview_game.py` → 46 passed); only the native
build step is broken here.

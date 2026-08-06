# uedcli dev/test container — Rust + Python 3.12 + deps.
# uedcli dev (the CLI and its test suite) runs INSIDE this long-running container, docker-exec'd
# into (owner ruling 2026-08-06; dev/docs/direction/process.md). NOT the FEX editor/game RUNTIME
# container that ships in releases — this is dev tooling only.
#
# arm64/amd64-native (no emulation): uedcli and the uedcli_native CSG/BSP core are arch-agnostic and
# run at native speed. The repo is identity-mounted at its host path, so in-container paths equal host
# paths and uedcli never branches on "am I in a container?".
FROM python:3.12-bookworm

# C toolchain for the pyo3 native build; the base image already ships libpython3.12 (shared), which
# `cargo test` links (-lpython3.12) — the exact link the host lacked.
# build-essential: pyo3's C linker. git: uedcli and its tests shell out to git (board, git-native
# materialize, _git_hint).
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential git \
 && rm -rf /var/lib/apt/lists/*

# Rust toolchain for uedcli_native (cargo test goldens + maturin build of the extension module).
ENV RUSTUP_HOME=/opt/rustup CARGO_HOME=/opt/cargo PATH=/opt/cargo/bin:$PATH
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \
    | sh -s -- -y --default-toolchain stable --profile minimal

# Python dev deps — mirror bin/_venv.sh's _DEPS_SPEC (Pillow runtime, pytest dev) plus maturin to
# build the native extension into this container's interpreter.
RUN pip install --no-cache-dir 'Pillow>=11' 'pytest>=8,<9' 'maturin>=1,<2'

# docker CLI (client only) — uedcli-the-CLI drives the editor/game RUNTIME containers via the host
# docker daemon (socket mounted at run time), so the containerized CLI still spins them on the host.
# Static client binary, no daemon. dpkg arch (arm64/amd64) -> docker's static-bin arch (aarch64/x86_64).
RUN set -eux; \
    a="$(dpkg --print-architecture)"; case "$a" in arm64) da=aarch64;; amd64) da=x86_64;; *) da="$a";; esac; \
    v=27.3.1; \
    curl -fsSL "https://download.docker.com/linux/static/stable/${da}/docker-${v}.tgz" \
      | tar -xz -C /usr/local/bin --strip-components=1 docker/docker; \
    docker --version

# Keep ALL build/cache writes OUT of the identity-mounted repo, so the root-run container leaves no
# root-owned artifacts on the host: cargo builds to a container-internal target dir, and Python
# bytecode caches go to /tmp instead of the source tree. (cargo registry cache is CARGO_HOME above.)
ENV CARGO_TARGET_DIR=/opt/cargo-target PYTHONPYCACHEPREFIX=/tmp/pycache
WORKDIR /workspace/uedcli

# uedcli Rust-build container — builds the `uedcli_native` extension (abi3 wheel) and runs the
# `cargo test` goldens. uedcli itself and pytest run HOST-NATIVE (Python 3 is on most hosts); only
# Rust isn't, so ONLY the Rust step is containerized (owner ruling 2026-08-06). NOT a run env, NOT the
# FEX editor/game runtime. arm64/amd64-native — the wheel is built for the host's arch.
FROM python:3.12-bookworm

# build-essential: the C linker pyo3 needs. The base image ships libpython3.12 (shared), which
# `cargo test` links (-lpython3.12) — the exact link a bare host lacked.
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential \
 && rm -rf /var/lib/apt/lists/*

# Rust toolchain + maturin (builds the extension module into an abi3 wheel).
ENV RUSTUP_HOME=/opt/rustup CARGO_HOME=/opt/cargo PATH=/opt/cargo/bin:$PATH
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \
    | sh -s -- -y --default-toolchain stable --profile minimal \
 && pip install --no-cache-dir 'maturin>=1,<2'

# The crate is bind-mounted at /io; the registry cache + target go under /io/target (a
# CARGO_HOME=/io/target/.cargo override at run time) so they persist and stay off the image.
WORKDIR /io

#!/usr/bin/env bash
# SPIKE 40 — reproduce the Nuitka+PyO3 end-to-end bundling proof.
# Requires: python3.12, a Rust toolchain (rustup/cargo), internet (PyPI + crates.io).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
WORK="${1:-/tmp/spike40}"
rm -rf "$WORK"; mkdir -p "$WORK"
cp -r "$HERE/spikemod" "$WORK/spikemod"
cp "$HERE/app.py" "$WORK/app.py"
cd "$WORK"
python3.12 -m venv venv
./venv/bin/pip install -q --upgrade pip
./venv/bin/pip install -q maturin nuitka patchelf   # patchelf: Nuitka standalone needs it on Linux
export VIRTUAL_ENV="$WORK/venv"
export PATH="$WORK/venv/bin:$PATH"
( cd spikemod && ../venv/bin/maturin develop --release )   # builds abi3-py312 .so into venv
./venv/bin/python app.py                                   # expect: spikemod.add(2,3) = 5
./venv/bin/python -m nuitka --standalone --assume-yes-for-downloads --output-dir="$WORK/nuitka_out" app.py
env -i "$WORK/nuitka_out/app.dist/app.bin"                 # expect: 5   (auto-detected, no --include-module)
./venv/bin/python -m nuitka --onefile   --assume-yes-for-downloads --output-dir="$WORK/onefile_out" app.py
env -i "$WORK/onefile_out/app.bin"                         # expect: 5
echo "SPIKE 40 OK"

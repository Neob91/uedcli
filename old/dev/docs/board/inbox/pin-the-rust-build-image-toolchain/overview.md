+++
priority = "p3"
kind = "chore"
summary = "dev-container/Dockerfile installs --default-toolchain stable and an unpinned maturin, so rebuilding the build image silently changes the compiler that produces every parity result."
spikes = ["dev/docs/spikes/2026-09-07-native-ext-build-staleness/"]
+++

# The Rust build image is not pinned

`dev-container/Dockerfile` installs `rustup ... --default-toolchain stable` and
`pip install 'maturin>=1,<2'`. `_ensure_build_image` rebuilds whenever the Dockerfile's sha256
changes, and a rebuild after a `docker system prune` picks up whatever `stable` is that day
(currently rustc 1.98.1 / LLVM 22.1.8; the image was built 2026-09-03). Nothing records which
compiler made a wheel, so "the same source always produces the same binary" does not hold across an
image rebuild.

Low priority because the risk is cosmetic so far: a compiler change moves the bytes, not the
results. Measured 2026-09-07 — `-C opt-level=1 -C codegen-units=1` and `-C target-cpu=native`
(AVX2 + FMA) leave the entire UNATCO N=116 permeating-light margin trace byte-identical, because
Rust emits strict IEEE f32 with no reassociation and no FMA contraction. A future rustc could still
change it.

The fix is a pinned toolchain version and maturin version in the Dockerfile. It costs every session
one image rebuild (a rustup download), which is why it was not folded into the campaign's active
ladder work.

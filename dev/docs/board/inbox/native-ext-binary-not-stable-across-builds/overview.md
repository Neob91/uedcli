+++
priority = "p2"
kind = "debug"
summary = "Two builds of the identical uedcli-native source produce different .so binaries and different lighting output — a ladder N can flip PASS/FAIL with no source change. Found closing UNATCO N=116."
+++

# The `uedcli_native` binary is not stable across builds, and the lighting notices

Building `uedcli-native` twice from the same committed `src/` gives two different extension modules,
and they disagree about a real parity result.

Measured 2026-09-07 while closing `unatco-n-116-world-model2-light-runs-differ-on`:

- Canonical layout (an exact copy of the crate directory, which is what `bin/_venv.sh` builds):
  `uedcli_native.abi3.so` = **1 650 840** bytes. UNATCO N=116 gates **PASS**.
- The same `src/`, same `Cargo.toml`/`Cargo.lock`/`pyproject.toml`, same build image and flags, in a
  directory missing `uedcli-native/.cargo/config.toml`: **1 645 752** bytes. UNATCO N=116 gates
  **FAIL** — `Model.Lights` 941 against UED22's 940, one extra permeating light on leaf 9, every
  later `iPermeating` and `iLightActors` shifted by one. Every geometry array stays byte-exact.

Each build is itself deterministic: two from-scratch builds of the same directory are sha256-equal,
and three native builds from one binary produce byte-identical packages. So this is not a race in
`bake`'s parallel gather — that path is explicitly replayed in light order — it is the compiled code
differing.

Two things follow, and the second is the expensive one:

1. **A parity result is only as reproducible as the wheel that produced it.** `verify_refs.py` checks
   the editor half of a ladder pair; nothing checks which `uedcli_native` build made the native half.
   `bin/test`'s `run_cargo_test` also shares `uedcli-native/target/` with the maturin build, so what
   `ensure_native_ext` packages can depend on whether `cargo test` ran first.
2. **Some lighting decisions are inside codegen noise.** A decision that flips between two
   compilations of the same arithmetic is one native is not computing the way the editor does; it
   currently lands on UED22's side by luck of the build. UNATCO N=116 leaf 9 is one instance and the
   cheapest known repro (~1 min per rebuild); `island-n-123-world-model2-leaf-permeating-light`
   (leaf 26) is the open, more expensive one. Both are `FEditorVisibility::ActorVisibility` beam-flood
   margins.

## What a build here needs

- Find what in `.cargo/config.toml` reaches codegen at all — the committed file only sets
  `[env] RUST_TEST_THREADS = "1"`, which should not — and pin the answer with a test, because until
  it is known, "same source" does not imply "same parity result".
- Record the wheel's sha256 beside every ladder result (`ref_N<n>.recipe` already does this for the
  editor half) so a bail can be attributed.
- Then treat the leaf-9 flip as a live probe for the flood's decision boundary.

## Repro

    tar -C uedcli-native --exclude=./target -cf - . | tar -C /tmp/exact -xf -   # PASS
    rm -rf /tmp/exact/.cargo                                                    # rebuild -> FAIL

Build each with `maturin build --release` in the `uedcli-rust-build` image, unpack the wheel, put it
first on `sys.path`, then `actor_parity.py --dx 03_NYC_UNATCOHQ.dx native 116` and `parity_gate.py`.

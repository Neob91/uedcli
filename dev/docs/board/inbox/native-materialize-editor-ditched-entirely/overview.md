+++
priority = "p1"
kind = "unknown"
summary = "Native materialize: editor DITCHED entirely (no `--native`/`--verify`), and hot loops go in RUST"
+++

# Native materialize: editor DITCHED entirely (no `--native`/`--verify`), and hot loops go in RUST

p1. Andrzej directed (2026-07-14): `level materialize` IS the native build,
no flags, no fallback editor path; correctness = an always-on OFFLINE self-consistency check; the
editor survives only as a dev-time golden-capture oracle. Perf was measured early (harness
`.../harness/perf_probe.py`+`bench.py`): pure CPython misses the ≤2min/≤20s target — UNATCO-HQ ~71s,
**UNATCO-Island ~7.6min** — so the two hot loops (CSG classify/split + BSP LineCheck) go in Rust with
Python orchestration + the proven serializers. **Glue DECIDED: PyO3/maturin extension `uedcli-native`**
(in-process; FFI boundary = the `UModel` body as bulk `bytes`; ship=Nuitka, venv=dev-only; sidecar
rejected). Adds a Rust toolchain to dev. Spec §3/§4/§6/§8/§9 updated. **Reviewed (2 architecture
reviewers, findings folded):** mandatory §6 **gate 5** (Rust↔Python serializer cross-check — anti-drift);
FFI mechanics (`Result`→`BuildError`, panic-catch, `Python::allow_threads` for interruptibility);
staged API (geometry/bake/paths, paths returns separately); rayon determinism invariant; **M0**
glue+game-load proof before N-1; `_venv.sh`/`bin/test` need real Rust-build integration (optional/
skippable, source-hash-gated). **Two flagged open items now RESOLVED by spikes 40/41
(`spikes/2026-07-15-native-materialize/40-nuitka-pyo3.md`, `41-fp-model-x87-vs-sse.md`):** (1) **Nuitka
+ PyO3 PROVEN** — trivial `abi3-py312` module bundles + loads under both `--standalone` and `--onefile`
(auto-detected, like Pillow); gotchas measured (needs `patchelf`; glibc floor 2.34; Linux/x86_64 only —
cross-platform matrix separate; `level preview`/stub-build still need Docker). (2) **FP model = SSE,
NOT x87** — the UED22 DLLs are 2022 MSVC `/arch:SSE2` rebuilds (zero x87/`fldcw`/FMA), so **bit-exact
parity IS reachable with native Rust `f32`**; remaining work is deterministic op-ORDER fidelity
(replicate `PlaneDot`'s reduction, forbid FMA). **Still open:** there is NO CI — gates are a
local-runner responsibility until one exists. **Build STARTED** (M0 + Python glue + Rust core) in a
worktree; port not sign-off-complete.

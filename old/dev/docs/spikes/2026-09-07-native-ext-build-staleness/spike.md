# The `uedcli_native` build was never non-deterministic — cargo shipped a stale binary

**Result: one root cause, fixed, no parity-bar change.** Board
`native-ext-binary-not-stable-across-builds` reported that two builds of the identical committed
`uedcli-native/src/` produced `.so`s 5472 bytes apart that disagreed about UNATCO N=116 (world leaf
9 getting a permeating-light run UED22 leaves empty), and blamed three non-source files. That is not
what happened. **Cargo decides freshness by MTIME**, so a crate whose sources were restored with
older timestamps was taken as up to date and never recompiled: the wheel kept the PREVIOUS build's
code. The "second binary" was an older revision's artifact.

`bin/_venv.sh` now refreshes the crate's source mtimes before `maturin build`, so the content hash
it already gates on is what actually decides. Regression:
`test_native_roundtrip.py::test_native_ext_build_refreshes_crate_mtimes_before_cargo_sees_them`.

## The mechanism, reproduced directly

In a crate copy with a warm `target/`, `src/permeating_lights.rs` was replaced with a materially
different file (a 200-line margin probe) and its mtime set to an earlier day. `maturin build
--release` in the `uedcli-rust-build` image then printed no `Compiling uedcli-native` line at all,
left `target/release/libuedcli_native.so` byte-identical, and packaged that stale `.so` into a fresh
wheel. Touching the sources first (the fix) makes the same build recompile and the `.so` change
(1 650 840 → 1 655 576 bytes).

Every workflow that restores sources this way is exposed: **`git archive` stamps files with the
commit's timestamp** (verified: `git archive 59ada80e uedcli-native` writes `src/zones.rs` with
mtime `2026-09-06 21:32`), and `tar -x`, `cp -p` and `rsync -t` preserve whatever the source had.
`git checkout` does not — it writes mtime `now` — which is why the live repo path was never wrong.

## The forensic proof that this is what produced the N=116 bail

The prior session left its N=116 packages in `_scratch/`. With the 16-byte package GUID blanked:

| Packages | sha256 | `Model.Lights` |
|---|---|---|
| `native_N116_{23fa4fc9,59ada80e,567291a2,b028ccf7,at1427,HEAD}.dx` | `0f4a04577bf9c221` | 941 |
| `native_N116_{control,current,exact,fresh,premover}.dx` | `cc645eee04435a15` | 940 |

The first six are labelled with six different commits — including the `MakePortals` port, the
beam-clip-plane normalize, the lightmap zero-vertex gate and the `ClipBspSurf` rasterizer port, all
of which change native's geometry or lighting code. Six materially different sources cannot compile
to one byte-identical package. They were never compiled: all six runs used one stale wheel.

Freshly built from scratch, those same commits give different binaries and different results —
`59ada80e` builds to a 1 649 272-byte `.so` (not the stale 1 645 368) and its N=116 package is the
940-light PASS one, not the 941-light package filed under its name.

The extra light is `Model.Lights` index 74 (Actors-array index; light 64 in trunk light order)
prepended to leaf 9's run: `[74, 31, 30, 28]` where a real build gives `[31, 30, 28]`. The current
code never brings light 64 adjacent to leaf 9 at all, so this was a whole-algorithm difference, not
a marginal one.

## What was ruled out (the "codegen noise" story)

Rust/LLVM emits strict IEEE f32 — no reassociation, no FMA contraction — so optimisation settings
cannot move these values, and they don't:

- **The three non-source files do nothing.** A copy of the crate minus `.cargo/config.toml`,
  `.gitignore` and the empty `uedcli-native/uedcli-native/` builds to a `.so` with the SAME sha256
  as the full copy. (`.cargo/config.toml` only sets `[env] RUST_TEST_THREADS`.)
- **Four independent from-scratch builds** of the committed source (two crate copies, a third at a
  different path, and `bin/_venv.sh`'s own) all produce `1 650 840` bytes / `39afacf403d0e2dd`.
- **Codegen variation changes nothing measurable.** Built at `-C opt-level=1 -C codegen-units=1` and
  at `-C target-cpu=native` (this host: AVX2 + FMA), the full margin trace of the leaf-9 flood —
  every plane distance, every clip classification, on every path tried — is byte-identical to the
  default build's, though the `.so`s differ by 60 KB and 25 KB respectively.
- **Runs are stable.** N=116 rebuilt at `RAYON_NUM_THREADS` 1, 8 (twice) and 14 differs only in the
  16 bytes of the package GUID, which the gate already excludes.
- **Path length changes the bytes but not the code.** `CARGO_HOME=/tmp/.cargo` instead of
  `/io/target/.cargo` shortens the dependency source paths embedded in panic locations and moves
  `.rodata` by 240 bytes; `.text` keeps its exact size and all 2498 differing byte-runs are the same
  RIP-relative displacement shifted by 240. No instruction differs.

## The near-tie is real, but it is not build-sensitive

A margin probe (`harness/permeating_margin_probe.patch`) dumps every gate along every path the flood
tries into a target leaf. UNATCO N=116 leaf 9 is marked by three lights and has one close near-miss:
light 56 down `37 → 35 → 34 → 36 → 29 → 30`, where a clipped vertex's `plane_dot` is
`-3.0517578e-05` — **exactly one f32 ULP** at magnitude 256-512, i.e. a vertex that lies
mathematically ON the beam plane. Island N=123's decisive path carries an exact `0.0` of the same
kind two hops before leaf 26.

These are unavoidable: `clip_beam` builds each beam plane through the light and an edge of the poly
the beam entered by, and portal polys share vertices, so the shared vertex's distance is zero plus
rounding. `FPoly::SplitWithPlaneFast` sends a tie to the front (`jb` at `0x10152021` fires only on
strictly negative) and native's `ds >= 0.0` matches that, so both engines resolve the tie the same
way as long as the arithmetic agrees bit for bit — which is what the `plane_w`/`plane_dot`/
`safe_normal` ports exist to guarantee. Nothing in the build can move them.

## Island N=123 does not share this cause

Re-gated with the verified wheel: Island is still PASS at N=122 and still bails at N=123 on
`BODY model model2`, unchanged. The leaf-26 census reproduces the earlier measurement exactly — the
mark comes from light 34 down `85 → 32 → 27 → 26`, and the tightest of the final clip's six
constraints clears by `1.795` (the probe reports `neg = 2.045 = min_dot + 0.25`). That is 7x the
`0.25` epsilon, so it is not a rounding question, and it is unaffected by which build produced it.
Its open item stands as written.

## Files

- `bin/_venv.sh` — the mtime refresh in `ensure_native_ext`.
- `uedcli/tests/test_native_roundtrip.py` — the regression.
- `dev/docs/spikes/2026-09-03-incremental-actor-parity/harness/ladder_run.py` — now prints the
  extension's sha256 and path before the walk, so a bail can be attributed to a binary.
- `harness/run_native.py` — build one level's first-N native package against a chosen unpacked wheel.
- `harness/leafrun.py` — dump each leaf's permeating-light run from a built package.
- `harness/permeating_margin_probe.patch` — the temporary `UEDCLI_PERM_MARGIN=<leaf>` instrumentation
  of `permeating_lights.rs` (`PERMTRY` per attempted crossing, `PERMMARGIN` per mark). Not applied.

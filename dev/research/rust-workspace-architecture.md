# Rust workspace and crate architecture for the rewrite

**Date:** 2026-10-03 · **Status:** research only — no decisions taken, nothing implemented.
**Question:** What crate/module structure should the new tree grow into, and what of
`old/uedcli-native/` is worth reintroducing?

## Summary

- The new root is a **single package, not a workspace** (`Cargo.toml` is 4 lines, `[package]`
  only). Every prior-art project of this size uses a virtual root manifest + flat `crates/`.
  Converting the root costs one PR and should happen before the second crate exists, not after.
- The Python tree has **six strongly-connected import components**, each held acyclic only by
  function-local imports. The largest — `model`, `emit`, `transform`, `rotation`, `geometry`,
  `writes` — is mutually recursive at runtime. Rust has no function-local import escape hatch, so
  **those six are one crate or nothing**. That single fact fixes the bottom of the graph.
- `old/uedcli-native/` is 31,938 Rust LOC of which **1,364 (4.3%) is PyO3 glue** — all of it in
  `src/lib.rs` (1,073) and `src/paths_py.rs` (291). The remaining 95.7% is pure Rust that
  `cargo test` already exercises with no interpreter. Reintroduction is mostly a lift-and-review,
  not a port.
- `resolve-core` (5,320 LOC: `package_read.rs` 582, `resolve.rs` 4,720, `lib.rs` 18) contains
  **zero** `std::env`, `std::fs`, `std::time` or thread references. It is already proven on both
  PyO3 and `wasm32-unknown-unknown`. It is the single highest-value, lowest-risk reintroduction and
  should be one of the first library crates in the new tree.
- The CSG/BSP core is the opposite: ~30 `std::env::var` debug-flag reads inside `bspcsg.rs`,
  `zones.rs`, `visible_surfs.rs`, `light.rs`, `bspoptgeom.rs`, `fpoly.rs`, plus `rayon`. It already
  forced `RUST_TEST_THREADS = "1"` into `old/uedcli-native/.cargo/config.toml` because those
  process-global flags race the test suite. Reintroducing it unchanged imports that defect.
- `old/uedcli/serve/` imports `old/uedcli/cli/` today (8 edges: `cli.errors`, `cli.resources`).
  That is exactly the trap named in the `jj` crate-split RFC — once command plumbing lives in the
  CLI crate, the server must link the CLI. The shared pieces belong in library crates.
- Prior art is unanimous on one point: **nobody splits crates per verb.** `ruff` has 53 crates but
  keeps every lint rule in one (`ruff_linter`); `nushell` tried a single giant command crate and is
  still unwinding it years later. Crates are *layers*, the verb surface is *one crate*.
- External consensus on errors is unchanged: `thiserror` enums in library crates, type-erased
  report at the binary edge. uedcli already has the right shape in Python — one taxonomy,
  two presentations (`error_to_status` returns `(status, message)` and is called by both
  `cli/dispatch.py` and the `serve` exception handler).
- Suggested shape (proposal, not a decision): **flat `crates/`, ~11 library crates + 1 bin + 1
  server**, growing in a fixed order aligned to the spec's PR sequence, with two crates
  (package decode, schema resolution) held permanently wasm-clean.

## What we have today

### New tree (the whole of it)

`Cargo.toml` is 4 lines (`[package]` only — no `[workspace]`, no dependencies); `Cargo.lock` is 7
lines; `src/main.rs` is 17 lines that `exec` `old/bin/uedcli` with argv passed through; plus PR #1's
`tests/proxy.rs`. Nothing else.

### `old/uedcli/` — 67,242 non-test LOC (220 modules), 73,342 test LOC (262 files)

Grouped into candidate crates. Membership is my grouping, not the doc's.

| candidate area | files | LOC | principal modules |
|---|---|---|---|
| CLI (parsers + dispatch + commands) | 65 | 11,476 | `cli/parsers/`, `cli/dispatch.py`, `cli/commands/`, `cli/rendering.py` |
| uscript compiler | 22 | 11,043 | `uscript/compile.py` (3,299), `uscript/lower.py`, `uscript/parser.py` |
| native glue (Python side of PyO3) | 18 | 6,885 | `native/unbuilt.py`, `native/saveorder.py`, `native/umodel.py`, `native/codec.py` |
| render / preview | 8 | 5,927 | `preview.py` (2,847), `preview_native.py`, `preview_game.py`, `meshrender.py` |
| level model + T3D tree | 22 | 5,409 | `model.py`, `emit.py`, `normalize.py`, `transform.py`, `rotation.py`, `t3dtree.py` |
| survey / relations | 4 | 4,575 | `actor_survey.py` (2,449), `relation.py`, `actorgraph.py`, `eventgraph.py` |
| GUI backend | 16 | 3,250 | `serve/app.py` (1,306, FastAPI, 23 routes), `serve/scene.py`, `serve/errors.py` |
| package decode | 8 | 3,183 | `upackage.py`, `utexture.py`, `dxpkg.py`, `umesh.py`, `pkg_cache.py` |
| editor driver + materialize | 11 | 2,909 | `driver.py`, `editor.py`, `apply.py`, `packages.py`, `xfer.py` |
| brush build / surface | 5 | 2,715 | `builders.py`, `surface.py`, `polyalign.py`, `brushcsg.py`, `texframe.py` |
| stash / prefab / stub / map import | 7 | 2,357 | `mapimport.py`, `stub.py`, `stashlib.py`, `uscript_rewrite.py` |
| project / config / docs | 5 | 1,770 | `config.py`, `doctor.py`, `userdocs.py`, `build_cache.py` |
| class schema (index + caches) | 5 | 1,547 | `classindex.py`, `schema_cache.py`, `class_catalog.py` |
| `uprops/` (offline schema + defaults) | 5 | 1,454 | `base` < `ufield` < `uclass` < `values` |
| `propedit/` (prop-set verb logic) | 7 | 1,380 | `base` < `tokens` < `paths` < `structtext` < `fields` < `edit` |
| asset catalogs | 4 | 703 | `texture_catalog.py`, `audio_catalog.py`, `audioindex.py` |

145 `add_parser(` calls across `cli/`; `old/web/` is 22,630 TS LOC and stays TypeScript per the
spec.

### `old/dev/docs/architecture.md`'s four layers

Four, plus Materialize as a fifth bullet:

1. **Command API** — `cli.py`/`dispatch.py` (now `cli/`), `tool_assets.py`, `userdocs.py`, the
   ordered exit-2 error guard.
2. **Level model** — `model.py`, `emit.py`, `normalize.py`, `typedprops.py`, `classdefaults.py`,
   `geometry.py`, `clip.py`, `vertex.py`, `builders.py`, `profile.py`, `movers.py`, `query.py`,
   `preview.py`, `eventgraph.py`, `upackage.py`, `uprops/`, `propedit/`, `surface.py`,
   `polyalign.py`.
3. **Editor driver** — `driver.py` over `old/uned/wine_ctl.py`, the four-signal `map_save`
   verification, the bounded-`docker exec` rule.
4. **T3D tree I/O** — `t3dtree.py` as the one reader/writer for all three trees; `trunk.py`
   re-exports it under level-facing names.
5. **Materialize** — `apply.py`, `materialize.py`, `packages.py`, `store_export.py`, `dxpkg.py`,
   `verify.py`.

A reasonable crate skeleton, but it under-describes two things: layer 2 is roughly half the codebase
and is not one layer, and the doc is stale on the Rust side — a board item says so
(`old/dev/docs/board/inbox/architecture-md-stale-on-the-new-resolve-core/`).

## Findings

### 1. The import graph: hubs, leaves, and six cycles

220 non-test modules, 652 internal import edges.

Top hubs by in-degree: `model` 43, `cli.errors` 38, `upackage` 24, `uprops` 24, `emit` 20,
`normalize` 18, `rotation` 16, `geometry` 14, `classindex` 14, `config` 13, `transform` 12,
`movers` 12, `driver` 11, `native_ext` 10, `native.codec` 10.

Top out-degree: `cli.dispatch` 29, `native.unbuilt` 22, `preview_native` 21, `apply` 19,
`serve.app` 19, `uscript.compile` 18.

True leaves with ≥4 importers (nothing internal imported): `cli.errors` 38, `config` 13,
`native_ext` 10, `native.codec` 10, `typedprops` 8, `container_assets` 8, `preview_shots` 5,
`stub_cache` 4, `tool_assets` 4.

**Six strongly-connected components:**

| SCC | members | how it is broken today |
|---|---|---|
| A | `emit`, `geometry`, `model`, `rotation`, `transform`, `writes` | all function-local imports |
| B | `builders`, `query`, `surface`, `texframe` | function-local imports |
| C | `pkg_cache`, `upackage` | `upackage` → `pkg_cache` function-local |
| D | `utexture`, `utexture_decode` | `utexture_decode` → `utexture` function-local |
| E | `driver`, `xfer` | both directions function-local |
| F | `apply`, `native.unbuilt` | both directions function-local |

These are the crate-boundary decisions, because Rust has no equivalent escape hatch — a
function-local `use` does not break a crate-level cycle, and Cargo forbids crate cycles outright.
Practical reading:

- **SCC A is one crate, non-negotiable.** `model.py` itself documents the constraint at line 29:
  `CoordinateError` "lives here, in the lowest layer, because `emit` (which detects it) may not
  import `geometry` (which owns `GeometryError`) — `geometry` already imports `emit`".
- **SCC B is one crate** (or a module tree inside the model crate). `builders` → `surface`,
  `builders` → `query`, `query` → `builders`.
- SCCs C and D fold into a package-decode crate. E folds into an editor-driver crate. F is the
  only one that spans two natural crates (materialize orchestration vs the native writer) and is
  the one that will need a trait or a parameter rather than a mutual import.

**The cycle `architecture.md` names explicitly** is a different, *avoided* one:
`old/uedcli/profile.py` owns the constant `WELD`, which `builders.py` imports at module scope,
"because the reverse direction is a load-time cycle". `builders.py` then re-imports `profile`
function-locally at four call sites with the comment `# function-local: see the WELD note at the
imports`. In Rust this evaporates — both end up in the same crate.

### 2. The CLI/server edge that must not be reproduced

Cross-area edge counts (A depends on B), largest first:

```
 82 CLI -> level model      18 native glue    -> level model
 26 CLI -> class schema     16 render/preview -> level model
 21 brush/surface -> model  14 GUI backend    -> level model
 15 CLI -> project/config   13 editor driver  -> level model
  8 GUI backend -> CLI   <-- the problem
  2 CLI -> GUI backend   <-- and the back-edge
```

`old/uedcli/serve/app.py` imports `..cli.resources` and `..cli.errors`;
`old/uedcli/cli/dispatch.py` imports `..serve.errors.error_to_status`. Two modules are doing
double duty:

- `cli/resources.py` (373 LOC) — "Project and game-resource resolution shared across command
  families": `resolve_project`, `composed_dirs`, `class_defaults`, `mover_index`.
- `cli/errors.py` (26 LOC) — `CommandError`/`ProjectError`/`LevelSelectionError`, the taxonomy
  `dispatch()` catches.

Neither is CLI-specific. In a Rust workspace they belong in library crates, with the CLI crate
holding only clap definitions, argv→request translation and exit-code mapping, and the server crate
holding only axum routing and HTTP-status mapping. This mirrors rust-analyzer's stated invariant:
the `rust-analyzer` crate is "the only crate that knows about LSP and JSON serialization", and if
you want to expose something to LSP you create a serializable counterpart there rather than making
the core type serializable
(<https://github.com/rust-lang/rust-analyzer/blob/master/docs/book/src/contributing/architecture.md>).

### 3. `old/uedcli-native/` inventory

Already a 3-member workspace (`members = [".", "resolve-core", "resolve-wasm"]`) with the root
crate *also* being a package — the thing matklad advises against (a root package "pollutes the
root with `src/`" and forces `--workspace` everywhere;
<https://matklad.github.io/2021/08/22/large-rust-workspaces.html>).

| file | LOC | purpose | reintroduce? |
|---|---|---|---|
| `resolve-core/src/resolve.rs` | 4,720 | class-schema resolution: `ResolutionContext`, `resolve_class`, `resolve_actor_props`, serde wire contract | **yes, early, near-verbatim** |
| `resolve-core/src/package_read.rs` | 582 | the one UE1 package wire decoder (header, name/import/export tables, compact index, tagged props) | **yes, first** |
| `resolve-core/src/lib.rs` | 18 | `BuildError`/`BResult` | yes, folds into the error crate |
| `resolve-wasm/src/lib.rs` | 29 | wasm-bindgen shim over `resolve-core`, zero logic | yes, when the web GUI lands |
| `src/bspcsg.rs` | 6,150 | feature-flagged incremental CSG — the `bspBrushCSG` port driving at a byte-identical `UModel` | yes, but last and with a cleanup |
| `src/visible_surfs.rs` | 2,042 | `URender::GetVisibleSurfs` — per-light visible-surface gather by cube-face rasterization | yes, with lighting |
| `src/render.rs` | 1,953 | software rasterizer for `level photo --native`; takes flat world-space polys, independent of the Model format | **yes — cleanest standalone unit** |
| `src/light.rs` | 1,908 | `LIGHT APPLY` lightmap bake (1-bit-per-lumel visibility masks) | yes, after the BSP core |
| `src/zones.rs` | 1,859 | native `TestVisibility` portalization, zone flood, per-node `iZone`/`ZoneMask` | yes, with the BSP core |
| `src/build.rs` | 1,542 | pooling, `bspAddNode`, `FindBestSplit`/`SplitPolyList`/`bspBuild`, `bound_leaked_solid_leaves` | yes |
| `src/paths.rs` | 1,511 | `PATHS DEFINE` reachspec build; every geometric probe behind a `ReachWorld` trait | yes — the trait seam makes it testable alone |
| `src/lib.rs` | 1,073 | **PyO3 shim** — 19 `#[pyfunction]`, 3 `#[pyclass]`, 1 `#[pymodule]`, 4 exception types | **no — delete; it is the seam** |
| `src/bspoptgeom.rs` | 980 | `bspOptGeom`: T-junction elimination + geometry optimization, validated byte-exact | yes |
| `src/collision.rs` | 966 | `UModel::LineCheck`/`PointCheck`, box sweep vs leaf hulls, `FindSpot`, `PointRegion` | yes |
| `src/mesh_read.rs` | 923 | `UMesh`/`ULodMesh` export-body decode (read path only) | yes, with package decode |
| `src/passes.rs` | 901 | `bspMergeCoplanars`, `bspRefresh`, `bsp_build_bounds` (the collision-hull builder) | yes |
| `src/permeating_lights.rs` | 811 | per-leaf permeating light lists, `Model.Lights` region 1 | yes, with lighting |
| `src/fpoly.rs` | 791 | `FPoly` + surf-link metadata; `SplitWithPlane` with the exact ±0.25/±0.01 thresholds | **yes, first of the BSP set** |
| `src/scout.rs` | 769 | pawn reachability probes (`walkMove`/`flyMove`/`jumpLanding`/`TwoWallAdjust`) | yes, with paths |
| `src/linecheck.rs` | 546 | segment-vs-BSP shadow ray used by the bake | yes |
| `src/csg.rs` | 534 | the default-path CSG leaf filter + four per-`CsgOper` leaf funcs | yes |
| `src/paths_py.rs` | 291 | **PyO3 surface for the path build** | **no — delete; it is the seam** |
| `src/model_read.rs` | 273 | parse a `UModel` serial body back into a `Model` | yes |
| `src/model_write.rs` | 252 | the runtime `UModel` body serializer, pinned byte-identical to the Python oracle | yes |
| `src/model.rs` | 248 | the built `UModel` as plain structs (`BspNode`, `BspSurf`, `Plane`, `Vec3`) | yes |
| `src/paths_golden.rs` | 245 | test-only golden replay of committed path builds | yes, as a test module |
| `src/f32.rs` | 21 | f32/SSE-faithful plane-distance helper (no FMA contraction) | yes |

**Entangled with the PyO3 boundary:** only `lib.rs` and `paths_py.rs`. Both are pure translation —
Python args in, pure-core structs; core out, `bytes`. `lib.rs`'s own doc comment says so: "THIN by
design (§8.2)… All compute lives in the pure-Rust modules (`cargo test`-able with no Python)."
Nothing else in `src/` mentions `pyo3` except one comment in `bspcsg.rs`. So the 32k figure is
**1,364 LOC glue (4.3%) / 30,574 LOC real logic (95.7%)**.

**What dropping the seam gains:** `lib.rs` registers 22 entry points (`build_geometry`,
`build_geometry_bspcsg`, `intersect_brushset`, `serialize_model`, `load_model`, `leaf_portals`,
`bake_lighting`, `bake_radiance`, `render_frame`, `parse_package_raw`, `read_property_tags_raw`,
`parse_mesh_raw`, `build_path_graph`, `place_path_nodes`, `resolve_class_json`,
`resolve_actor_props_json`, and the classes/exceptions) that exist only to marshal flat buffers. In
a pure-Rust tree they become ordinary calls, and the Python-side `.dx` codec (`old/uedcli/native/`,
6,885 LOC — `codec.py`, `umodel.py`, `actor_write.py`, `pkg_write.py`, `brush_marshal.py`) becomes
redundant with the Rust `model_read`/`model_write` it currently acts as a dev oracle for. That is a
one-time deletion of a dual implementation, not just a language change.

### 4. `resolve-core` and the wasm constraint

`resolve-core` is consumed twice: by PyO3 through `old/uedcli-native/src/lib.rs`
(`resolve_class_json`, `resolve_actor_props_json`), and by the browser through
`resolve-wasm`. `old/web/src/scene/classResolver.ts`, `old/web/src/resolveWasm.test.ts` and
`old/web/src/crossImplementationParity.test.ts` are the consumers; a golden fixture corpus
(`old/uedcli/tests/fixtures/resolve_golden/`) round-trips both implementations.

Verified: `resolve-core/src/*.rs` contains **zero** matches for `std::env`, `std::fs`,
`std::time`, `SystemTime`, `Instant::`, `thread::spawn`, `rayon`, or `File::open` (the one grep hit
on "thread" is the word "threaded" in a doc comment). Its only dependencies are `serde` and
`serde_json`. That is why it crosses to wasm unchanged.

`resolve-wasm/Cargo.toml` carries a long comment pinning `wasm-bindgen = "=0.2.100"` exactly,
because it must match the `wasm-bindgen-cli` version in `old/dev-container/Dockerfile`
byte-for-byte and the Dockerfile installs a floating `stable` toolchain. That pin is a real
operational hazard the new tree inherits if it keeps the same arrangement.

**The constraint this places on crate boundaries:** the package-decode and schema-resolution crates
must stay wasm-clean *permanently*.

- `wasm32-unknown-unknown` (Tier 2) — "`println!` does nothing, `std::fs` always return errors, and
  `std::thread::spawn` will panic… There is no means by which this can be overridden"
  (<https://doc.rust-lang.org/rustc/platform-support/wasm32-unknown-unknown.html>).
- Both `Instant::now()` and `SystemTime::now()` panic ("time not implemented on this platform") —
  std routes the target to its `unsupported` time impl. Drop-in fix: the `web-time` crate behind a
  `[target.'cfg(target_arch="wasm32")'.dependencies]` block, which is what `ruff` does.
- `getrandom`: the `RUSTFLAGS --cfg getrandom_backend="wasm_js"` dance is **no longer required** as
  of 0.3.4 (2025-10-14) — the `wasm_js` feature now selects that backend by default, cfg flag still
  available as an override; current line is 0.4.x. Its README warns a *library* against enabling
  `wasm_js` ("known to break non-Web WASM builds", bloats `Cargo.lock` on all targets). uedcli has
  no RNG need beyond `uuid7.py`'s ephemeral editor ids, which never reach the wasm side.
- Threads only via `wasm-bindgen-rayon`: pinned nightly, `rust-src`,
  `-Zbuild-std=panic_abort,std`, `+atomics,+bulk-memory`, shared-memory link args, and COOP/COEP
  headers on the host. Not worth it for schema resolution.

**The `ruff` pattern worth copying** (verified from its manifests): `wasm-bindgen`/`js-sys`/
`serde-wasm-bindgen` appear *only* in `crates/ruff_wasm` and `crates/ty_wasm` (both
`crate-type = ["cdylib", "rlib"]`, `test = false`); `ruff_db` puts every OS-only dependency behind
an `os = ["ignore", "dep:etcetera", "dep:same-file", "dep:which"]` feature which `ty_wasm` consumes
with `default-features = false`; the filesystem is injected through a `System` trait with
`OsSystem`/`MemoryFileSystem`/`InMemorySystem` impls; and CI runs
`cargo clippy -p ruff_wasm -p ty_wasm --target wasm32-unknown-unknown --all-features --locked`,
gating only the shim crates so the cores come in transitively.

### 5. The `std::env::var` defect in the CSG core

Roughly 30 `std::env::var` reads sit inside hot compute: `bspcsg.rs` (~20 — `UEDCLI_BSPCSG_*`,
`UEDCLI_REPART_*`), `visible_surfs.rs` (8), `zones.rs` (6), `permeating_lights.rs` (3),
`bspoptgeom.rs` (3), `light.rs` (2), `fpoly.rs` (1). This already cost something:
`old/uedcli-native/.cargo/config.toml` sets `RUST_TEST_THREADS = "1"` because "several `bspcsg`
tests set/remove process-global `UEDCLI_BSPCSG_*` env flags that `build_geometry_bspcsg` re-reads
at multiple gate sites, so a parallel test thread can observe a flag mid-flip and build a hybrid
pipeline (a real flake, hit 2026-09-02)".

Not a wasm blocker (`std::env::var` returns `NotPresent` rather than panicking), but it is a
behaviour-affecting hidden input read deep inside a library. A reintroduction PR is the natural
moment to make those an explicit options struct threaded from the caller — the one place where
"lift and review" probably wants to become "lift, review, and change".

### 6. External practice (2025–2026)

**Crate count and layout.** Flat `crates/` one level deep, virtual root manifest, crate name ==
directory name; automation in an `xtask` crate; `version = "0.0.0"` on unpublished crates; never
make the workspace root a package. matklad's rule of thumb: "until you hit a million lines of code,
the number of crates will probably fit on one screen"; flat beats nested because "tree structure
tends to deteriorate over time, while flat structure doesn't need maintenance"
(<https://matklad.github.io/2021/08/22/large-rust-workspaces.html>).

Graph *shape* matters more than count: "the most important property of a crate is which crates it
doesn't (transitively) depend on" — wide graphs give parallelism *and* incrementality, linear chains
give neither; *n* binaries × *m* libs multiplies linking work
(<https://matklad.github.io/2021/09/04/fast-rust-builds.html>). The recompile unit is the crate, not
the module, so **dependency hubs wreck incremental builds**; prefer breaking an edge with generics
or `Arc<dyn Trait>` before adding a crate
(<https://mmapped.blog/posts/03-rust-packages-crates-modules>). Timing: "splitting crates out
prematurely is probably not a good idea, but doing it too late risks that your code will depend on
and use private interfaces that you don't want it to use"
(<https://rustprojectprimer.com/organization/workspace.html>).

Compile-time data points: Feldera went 25 min → 2 min 10 s by splitting one generated crate into
1,106, because "the majority of time is spent in LLVM passes and codegen – which unfortunately are
single-threaded"
(<https://www.feldera.com/blog/cutting-down-rust-compile-times-from-30-to-2-minutes-with-one-thousand-crates>);
a 4× incremental-*test* speedup from more crates is measured at
<https://blog.waleedkhan.name/rust-incremental-test-times/#splitting-into-more-crates>.

**Prior-art layouts** (crate counts fetched 2026-10-03):

| project | crates | what it got right / wrong |
|---|---|---|
| `ruff` | 53 (~37 `ruff_*`, ~15 `ty_*`) | all lint rules in **one** crate (`ruff_linter`); the rest are layers (text_size → source_file → python_ast → parser → semantic → linter); CLI, server and wasm each a thin crate; `publish = false` on non-release crates |
| `oxc` | 42 in `crates/` + `apps/` + 8 napi pkgs | published 3-layer ARCHITECTURE.md (Foundation → Core processing → Applications); binaries live *outside* `crates/`, in `apps/` — a library/application split `ruff` does not make |
| `rust-analyzer` | 35 in `crates/` + 6 publishable in `lib/` | the best model for lib+CLI+server: `syntax` knows nothing of salsa or LSP; `hir` is the library façade; `ide` the feature boundary; the `rust-analyzer` crate is the *only* one aware of LSP/JSON; `base-db` "doesn't know about file system and file paths" (opaque `FileId`); `hir-def`/`hir-ty` declared *never* an API boundary |
| `nushell` | 48 in `crates/` | **the cautionary tale**: every command was in one `nu-command`, measured at 208 s cold vs 50 s for `nu-protocol`; the "Cratification" split (PR #8181) is still "a work in progress" years on; a `--features extra` compile gate was tried and *sunset* |
| `jj` | 6 members, at the repo root | `jj-lib` kept as a pure re-export **façade**; the lib must suit "a GUI or TUI, or in a server", so "all input/output is handled by the CLI crate" and the lib "cannot read configuration from the user's home directory". Open flaw: `WorkspaceCommandHelper` lives in `jj-cli`, so extensions must link the CLI — the exact trap |
| `uv` | 74, `members = ["crates/*"]` | `uv-types` exists "solely as shared traits… to avoid circular dependencies"; `uv-fs` isolates filesystem access; verb surface is `uv-cli` (clap), separate from `uv` (binary) and `uv-dispatch` |

**The jj crate-split RFC (<https://github.com/jj-vcs/jj/issues/6284>) is the closest published
discussion to this problem.** Transferable points: "it's better to just split up the crates slowly
in big chunky pieces and not break them down too far at the beginning"; the façade-crate pattern;
the biggest blocker being **test topology**, not code (a hardcoded backend enum in `testutils`,
fixed by extracting tests into their own crates); and the costs — topological publish order, and
needing intermediate crates purely to break cycles.

**Single core vs several domain crates.** The strongest argument *against* many crates is Tokio
collapsing its sub-crates into one feature-flagged crate for 0.2: "maintaining a large number of
crates comes with an increased maintainership burden… maintaining correct dependencies between
crates is complex", plus confusion over which sub-crate was public API, and release friction. **That
argument is publishing-shaped and does not transfer to an unpublished internal workspace** — an
asymmetry worth flagging rather than treating as consensus. What does transfer: no crate cycles,
and `pub(crate)` stops working as a boundary, so anything shared across a split becomes `pub` —
which is why the façade (`pub use` from one public crate over private internals) is the standard
repair. No authoritative post arguing "one unified core crate beats several domain crates" for a
CLI-sized project was found.

**Errors.** Unchanged consensus, from the author's own README: "Use Anyhow if you don't care what
error type your functions return… This is common in application code. Use thiserror if you are a
library that wants to design your own dedicated error type(s)"
(<https://github.com/dtolnay/anyhow>). `thiserror` 2.0 breaking changes: `{r#type}` rejected in
format strings, no mixing `{0}` positional access with extra positional args, derive users now need
a direct dependency on `thiserror`; new `no_std` via `default-features = false`
(<https://github.com/dtolnay/thiserror/releases/tag/2.0.0>). `eyre` is an `anyhow` fork with
pluggable report handlers; `color-eyre` is explicitly "not for libraries" and is reported
archived/folded into the eyre monorepo — **unverified**, third-party analysis only. `miette` adds
error codes, help text, severity and labelled source spans, with its `fancy` feature enabled only
in the top-level crate (<https://docs.rs/miette/latest/miette/>) — relevant if uedcli ever wants
spans on T3D or uscript parse errors.

**Features.** Normative: features must be additive, "enabling a feature should not disable
functionality"; model `std` (enables), never `no_std` (disables); mutually exclusive features
"should be avoided if at all possible". Unification: "Cargo will use the union of all features
enabled on that dependency", so one place's `default-features = false` "may not ensure the default
features are disabled" — check with `cargo tree --duplicates`
(<https://doc.rust-lang.org/cargo/reference/features.html>; canonical pitfall write-up
<https://nickb.dev/blog/cargo-workspace-and-the-feature-unification-pitfall/>). Resolver 2 (edition
2021) stops unification across target-specific, build- and dev-deps; resolver 3 (edition 2024,
Rust 1.84+) is an MSRV-resolution change, *not* a feature change; the resolver version is
workspace-global (<https://doc.rust-lang.org/cargo/reference/resolver.html>).
`resolver.feature-unification` is **still unstable** behind `-Z feature-unification`
(<https://doc.rust-lang.org/stable/cargo/reference/unstable.html>) — a search result claiming it
stabilized in 1.86 is wrong. CI: `cargo hack --each-feature` / `--feature-powerset`
(<https://github.com/taiki-e/cargo-hack>); `cargo-hakari` generates a `workspace-hack` crate for
cross-member feature churn (<https://docs.rs/cargo-hakari/latest/cargo_hakari/about/index.html>).

**Workspace inheritance.** `[workspace.dependencies]` + `dep.workspace = true` (MSRV 1.64).
Workspace entries may not set `optional`; a member may add only `optional`, `features` and
`default-features` alongside `workspace = true` — never `version` — and member `features` are
*additive*. A member's `default-features = false` overriding the workspace value is version-gated
and before that "may be ignored or rejected" — **confirm the exact gate before writing it into a
spec** (<https://doc.rust-lang.org/cargo/reference/specifying-dependencies.html>).
`[workspace.package]` inherits `edition`, `license`, `publish`, `rust-version`, `version` and more;
`license-file`/`readme` resolve relative to the workspace root, `include`/`exclude` to the package
root. `[workspace.lints.<tool>]` + `[lints] workspace = true` works since 1.74; a virtual workspace
must set `resolver` explicitly (<https://doc.rust-lang.org/cargo/reference/workspaces.html>).

## Options

| Option | Pros | Cons |
|---|---|---|
| **A. Stay one crate** (`uedcli`, modules only) until it hurts | zero workspace ceremony; `pub(crate)` keeps real boundaries; PR #2 lands with no restructuring; matches "don't split prematurely" | the unit of recompile becomes 60k+ LOC; nothing stops the server/CLI edge from re-forming; the wasm crate cannot exist, so the web GUI's schema resolver has no home; splitting later means un-picking `pub(crate)` uses that have already spread |
| **B. Two crates** (`uedcli-core` façade + `uedcli` bin), `jj`-style | simplest shape that still forbids the CLI→core back-edge; one façade to keep stable; proven at `jj`'s scale | the core is a 55k-LOC monolith whose every change rebuilds everything; the wasm target would pull CSG, `rayon` and the editor driver into the browser build unless feature-gated hard; `jj` itself has already moved past two crates |
| **C. ~11 layer crates, flat `crates/`**, `ruff`/`rust-analyzer`-style | the wasm-clean subset is a crate boundary, not a convention; wide graph → parallel + incremental builds; each `old/uedcli-native/` reintroduction has an obvious destination; CLI and server are peers over libraries, so the `serve`→`cli` edge is impossible | more manifests; needs `[workspace.dependencies]` discipline from day one; risk of inventing crates before their content exists; crate-level `pub` loses `pub(crate)` as a boundary inside the split |
| **D. Crate per verb family** (`uedcli-brush`, `uedcli-actor`, …) | each verb family compiles alone; maps 1:1 to the spec's PR sequence | no prior art does this; `nushell`'s measured compile-time pain and `ruff`'s decision to keep all rules in `ruff_linter` are both evidence against; every verb family needs the same model crate anyway, so the graph is a star, not a layering |

## Proposal (owner's call — not decided)

Option C, grown in order — but with the shape fixed up front and the crates created only when a PR
needs them, per the jj RFC's "big chunky pieces, not broken down too far at the beginning".

Names below are placeholders, not existing identifiers.

### Proposed crate graph

| crate | contents (from `old/`) | depends on | wasm-clean? |
|---|---|---|---|
| ued-error | the one error taxonomy + the `(status, message)` classification now split between `cli/errors.py` and `serve/errors.py`; `resolve-core/src/lib.rs`'s `BuildError` | — | yes |
| ued-pkg | `resolve-core/src/package_read.rs`, `upackage.py`, `dxpkg.py`, `umesh.py` + `mesh_read.rs`, `utexture.py`/`utexture_decode.py` | ued-error | **yes, enforced in CI** |
| ued-schema | `resolve-core/src/resolve.rs`, `uprops/`, `classindex.py`, `classdefaults.py` | ued-pkg | **yes, enforced in CI** |
| ued-model | SCC A (`model`, `emit`, `transform`, `rotation`, `geometry`, `writes`) + `normalize`, `typedprops`, `movers`, `clip`, `vertex`, `snap`, `query` | ued-error, ued-schema | yes |
| ued-brush | SCC B (`builders`, `surface`, `texframe`, `query` helpers) + `profile`, `polyalign`, `propedit/` | ued-model | yes |
| ued-tree | `t3dtree.py` (LexoRank, name allocator, sidecars), `trunk.py`, `stashlib`/`stash_register`, `folderlib`, `labellib` | ued-model | no (filesystem) |
| ued-project | `config.py`, project/level resolution (today's `cli/resources.py`, `cli/level_sources.py`), `build_cache`, catalogs, `userdocs` | ued-error, ued-tree | no |
| ued-bsp | `fpoly`, `model`, `model_read`/`model_write`, `csg`, `build`, `passes`, `bspcsg`, `bspoptgeom`, `zones`, `linecheck`, `light`, `visible_surfs`, `permeating_lights`, `f32` | ued-model | no (`rayon`) |
| ued-nav | `paths`, `scout`, `collision` — behind the existing `ReachWorld` trait seam | ued-bsp | no |
| ued-render | `render.rs` rasterizer + `preview_native.py`'s scene assembly, `meshrender`, `meshworld` | ued-bsp, ued-pkg | possible later |
| ued-editor | `driver`, `editor`, `xfer`, `apply`, `materialize`, `packages`, `verify`, `store_export`, `qualify` | ued-project, ued-tree, ued-bsp | no (docker) |
| ued-uscript | all of `uscript/`, `uscript_rewrite.py`, `stub*.py` | ued-pkg, ued-project | no |
| ued-survey | `actor_survey`, `relation`, `actorgraph`, `eventgraph` | ued-model, ued-brush | yes |
| uedcli (bin) | clap definitions, argv→call translation, exit-code mapping, the strangler proxy | every lib | n/a |
| ued-serve | axum routes (23 today), HTTP-status mapping, WS session state | every lib, **never the bin** | n/a |
| ued-wasm | `resolve-wasm/src/lib.rs`'s shim, nothing else | ued-pkg, ued-schema | **it is the wasm target** |
| xtask | build/codegen automation | — | n/a |

### ASCII dependency sketch

```
                                 ued-error
                                     |
                      +--------------+--------------+
                      |                             |
                   ued-pkg                      ued-project <--- ued-tree
                      |  \                          |               |
                      |   \                         |               |
                 ued-schema \                        \              |
                      |      \                        \             |
                   ued-model  |                         \           |
                   /   |   \  |                          \          |
                  /    |    \ |                           \         |
          ued-brush  ued-bsp  +-- ued-render               \        |
              |      /  |  \         |                      \       |
              |     /   |   ued-nav  |                       \      |
         ued-survey/    |      |     |                        \     |
              |        ued-editor <--+-------------------------+----+
              |             |
              |        ued-uscript
              |             |
     +--------+-------------+------------------+
     |                                         |
  uedcli (bin)                             ued-serve
     |
 old/bin/uedcli  (strangler proxy, deleted at the end)

  ued-wasm  ->  ued-schema -> ued-pkg -> ued-error     [wasm32-unknown-unknown]
```

The wasm path is the bottom line: a four-crate chain that must never acquire `rayon`, `std::fs`,
`std::time` or `std::env`. Everything heavier hangs off `ued-model` and above.

### Suggested order of coming into existence, against the spec's PR sequence

| spec step | crates created | why then |
|---|---|---|
| before PR #2 | convert root to a **virtual manifest** + `crates/`; move the proxy into `crates/uedcli` | cheapest moment; a 17-line `main.rs` and one test are all that move |
| PR #2 (first vertical slice — one brush builder) | ued-error, ued-model, ued-brush | a brush builder is exactly SCC A + SCC B and nothing else; this is the PR that proves the bottom of the graph |
| next 2 PRs | ued-pkg, then ued-schema | near-verbatim lift of `resolve-core`'s two modules; unlocks the `actor prop` and `class` verb families, and is the only pair that must stay wasm-clean |
| then | ued-tree | unlocks every trunk-reading verb at once (`actor find/show`, folders, labels) |
| then | ued-project | the `config`/project seam; must land before anything that resolves a search path |
| then | ued-survey, ued-uscript (independent, any order) | both are leaf consumers; `ued-uscript` is 11k LOC and wants its own PR series regardless |
| then | ued-bsp, in staged PRs: (1) `model`/`model_read`/`model_write`/`fpoly`/`f32`, (2) `csg`/`build`, (3) `passes`/`zones`, (4) `light`/`visible_surfs`/`permeating_lights`/`linecheck`, (5) `bspcsg`/`bspoptgeom` | the dual Python/Rust `UModel` codec collapses at stage 1, which is where the 6,885 LOC of `old/uedcli/native/` glue stops needing a port |
| then | ued-render, ued-nav | both sit on a built Model, so they need stage 1–3 of ued-bsp first |
| then | ued-editor | last of the libraries; it is the only one that needs docker, and the spec keeps `uned/` untouched until the end |
| then | ued-serve, ued-wasm | after enough core lands that most `/api/...` routes stop proxying; `ued-wasm` whenever the `web/` refactor reaches `classResolver.ts` |

### Conventions worth adopting with the first workspace PR

- Virtual root manifest; flat `crates/`; directory name == crate name, no stripped prefixes.
- `[workspace.package]` for `edition`, `rust-version`, `publish = false`; `version = "0.0.0"` on
  every unpublished crate.
- `[workspace.dependencies]` from the first shared dependency; `[workspace.lints]` + `[lints]
  workspace = true` in every member.
- `resolver` set explicitly (a virtual workspace has nothing to infer it from).
- One `thiserror` enum per library crate, `anyhow`-or-equivalent only in `uedcli` and `ued-serve`;
  the exit-code and HTTP-status mappings are *two* impls over one taxonomy, mirroring what
  `error_to_status` does today.
- A CI job that runs `cargo clippy -p ued-wasm --target wasm32-unknown-unknown --locked` — gating
  the shim pulls the wasm-clean chain in transitively, which is how `ruff` does it.
- `xtask` for anything that would otherwise be a shell script.

## Open questions / what to verify next

- Does the owner want the strangler proxy in `crates/uedcli` or kept as a separate crate so it can
  be deleted in one commit at the end?
- `ued-model` as a façade (`pub use` over private submodules) vs a flat `pub` surface — the jj RFC
  favours the façade; it costs a re-export file per crate.
- Is `query` in ued-model or ued-brush? It is in SCC B with `builders`/`surface`, but 8 modules
  import it including `serve/app.py`. Likely signals a split of `query` itself.
- `ued-nav` (`paths`/`scout`/`collision`, 3,246 LOC) could be a module tree inside ued-bsp instead
  of a crate. The `ReachWorld` trait is already the seam, so either works.
- Whether the 30 `std::env::var` debug flags in the CSG core become an options struct during
  reintroduction (behaviour-preserving) or stay as-is (imports a known test flake).
- `wasm-bindgen` version pinning: `resolve-wasm` pins `=0.2.100` against a floating `stable`
  toolchain in `old/dev-container/Dockerfile`. The new tree should pin the toolchain instead.
- Exact Cargo version gate for a member's `default-features = false` overriding
  `[workspace.dependencies]` — flagged unverified above.
- `color-eyre`'s maintenance status — the archive claim rests on a third-party analysis only.
- Test topology: 73,342 LOC of Python tests, and the jj RFC names test structure as the hardest
  part of a crate split. Worth its own research note — where do the extracted golden fixtures live
  so that no crate needs a dev-dependency on a sibling?

## Sources

Internal (read, not cited as external):
`old/dev/docs/board/to-plan/rewrite-uedcli-in-rust/spec.md`, `old/dev/docs/architecture.md`
(layer map at `:61-279`, native CSG core at `:1618-1794`),
`old/dev/docs/board/done/shared-rust-core-for-class-schema-resolution/overview.md`,
`old/dev/docs/board/inbox/architecture-md-stale-on-the-new-resolve-core/overview.md`,
`old/uedcli-native/Cargo.toml` + `resolve-core/Cargo.toml` + `resolve-wasm/Cargo.toml` +
`.cargo/config.toml` + `pyproject.toml`.

- <https://matklad.github.io/2021/08/22/large-rust-workspaces.html> — flat `crates/`, crate-count rule of thumb, no root package, `xtask`.
- <https://matklad.github.io/2021/09/04/fast-rust-builds.html> — graph shape over crate count; binaries × libs multiplies linking.
- <https://mmapped.blog/posts/03-rust-packages-crates-modules> — crate is the recompile unit; dependency hubs; break edges before adding crates.
- <https://rustprojectprimer.com/organization/workspace.html> — split timing; `pub(crate)` stops working as a boundary.
- <https://www.feldera.com/blog/cutting-down-rust-compile-times-from-30-to-2-minutes-with-one-thousand-crates> — 1,106 crates; single-threaded LLVM codegen is the bottleneck.
- <https://blog.waleedkhan.name/rust-incremental-test-times/#splitting-into-more-crates> — 4× incremental-test speedup from more crates.
- <https://github.com/astral-sh/ruff/blob/main/CONTRIBUTING.md#project-structure> — 53 crates, all lint rules in one, cites matklad.
- <https://github.com/astral-sh/ruff/blob/main/crates/ruff_db/Cargo.toml> — the `os` feature gating OS-only deps.
- <https://github.com/astral-sh/ruff/blob/main/crates/ruff_db/src/system.rs> — the injected-filesystem trait and its stated rationale.
- <https://github.com/astral-sh/ruff/blob/main/.github/workflows/ci.yaml> — the wasm-target clippy + `wasm-pack test` jobs.
- <https://github.com/oxc-project/oxc/blob/main/ARCHITECTURE.md> — 3-layer rationale; binaries in `apps/`, libraries in `crates/`.
- <https://github.com/rust-lang/rust-analyzer/blob/master/docs/book/src/contributing/architecture.md> — API Boundaries; only one crate knows the wire protocol.
- <https://github.com/nushell/nushell/blob/main/crates/nu-cmd-lang/README.md> and <https://github.com/nushell/nushell/issues/3609> — the one-giant-command-crate tale, with measured compile times.
- <https://github.com/jj-vcs/jj/issues/6284> — crate-split RFC: chunky pieces, façade crate, test topology as the real blocker.
- <https://docs.jj-vcs.dev/latest/technical/architecture/> — the lib must suit a GUI or server, so all I/O and user config live in the CLI crate.
- <https://github.com/astral-sh/uv/blob/main/Cargo.toml> and <https://github.com/astral-sh/uv/blob/main/crates/README.md> — 74 crates; `uv-types` breaks cycles; `uv-fs` isolates the filesystem.
- <https://tokio.rs/blog/2019-11-tokio-0-2> and <https://github.com/tokio-rs/tokio/issues/1318> — the argument against many crates (publishing-shaped).
- <https://github.com/dtolnay/anyhow> and <https://github.com/dtolnay/thiserror/releases/tag/2.0.0> — the error-type boundary; thiserror 2.0 breaking changes.
- <https://docs.rs/miette/latest/miette/> — error codes and source spans for a CLI; `fancy` only at the top crate.
- <https://doc.rust-lang.org/cargo/reference/features.html> and <https://nickb.dev/blog/cargo-workspace-and-the-feature-unification-pitfall/> — additive features, unification pitfall.
- <https://doc.rust-lang.org/cargo/reference/resolver.html> and <https://doc.rust-lang.org/stable/cargo/reference/unstable.html> — resolver 2 vs 3; `feature-unification` still unstable.
- <https://github.com/taiki-e/cargo-hack> and <https://docs.rs/cargo-hakari/latest/cargo_hakari/about/index.html> — feature-combination CI; `workspace-hack`.
- <https://doc.rust-lang.org/cargo/reference/workspaces.html> and <https://doc.rust-lang.org/cargo/reference/specifying-dependencies.html> — the inheritance rules.
- <https://doc.rust-lang.org/rustc/platform-support/wasm32-unknown-unknown.html> — `std::fs` errors, `thread::spawn` panics, cannot be overridden.
- <https://github.com/rust-random/getrandom/blob/master/CHANGELOG.md> and <https://github.com/rust-random/getrandom#webassembly-support> — RUSTFLAGS dance removed in 0.3.4; do not enable `wasm_js` in a library.
- <https://github.com/RReverser/wasm-bindgen-rayon#building-rust-code> — nightly, `-Zbuild-std`, `+atomics`, COOP/COEP cost of wasm threads.
- <https://rustwasm.github.io/docs/book/reference/which-crates-work-with-wasm.html> — parsers cross "so long as they just take input and don't perform their own I/O".
- <https://wasm-bindgen.netlify.app/> — the live wasm-bindgen book (the `rustwasm.github.io` path now 404s).

**Marked unverified:** the exact Rust/edition gate for a member overriding
`[workspace.dependencies]`'s `default-features`; `color-eyre`'s archived status (third-party
analysis only); a workspace-vs-single-crate compile benchmark seen quoted in search results but
not fetched from source; the claim that `feature-unification` stabilized in 1.86 (contradicted by
the stable unstable-features page).

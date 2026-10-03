# Differential-testing harness for the strangler migration

**Date:** 2026-10-03 · **Status:** research only — no decisions taken, nothing implemented.
**Question:** Concretely, how do we build the harness that proves a ported Rust verb matches `old/` — and how do we know when a verb is proven enough to retire from the proxy table?

## Summary

- **The oracle's cost is startup, not work.** Measured here: importing `old/uedcli`'s parser closure
  and building the parser costs **782 ms**; `brush build cube` then costs **1.7–2.5 ms**. A
  process-per-case harness runs ~1 case/s. Amortizing the import (a batch runner in `old/bin/`, which
  the frozen-`old/` rule explicitly permits for non-behavioral tooling) is a ~300× lever — the
  difference between a 20-case smoke test and property-based testing.
- **`old/`'s 73k LOC of tests are not CLI-level cases.** They call `dispatch()` with hand-built
  `argparse.Namespace` objects (or `build_parser().parse_args`) **in-process**, under two autouse
  monkeypatches that stub the class/texture gate. A subprocess harness can't monkeypatch. The argv →
  stdout → exit-code boundary the strangler proxies has exactly one 22-case corpus
  (`argv_corpus.json`), and even that stops at `parse_args`.
- **What *is* liftable is 4.5 MB of data fixtures** — `builder_parity.json` (21 cases),
  `fixtures/intersect/` (17 T3D goldens), `fixtures/csg_golden/` (6 BSP goldens),
  `fixtures/parser_baseline/` (900 KB), plus binary package/texture fixtures: the coverage that
  survives `old/`'s deletion.
- **No verb is pure at the CLI boundary.** `brush build` looks pure but always calls
  `ingest.validate_ingest_actors`, needing a project **and** the game packages. The escape is that
  `old/uned/UED22` is **git-tracked** (214 files, 34 packages), so a hermetic env (`UEDCLI_HOME` +
  `UEDCLI_PROJECT` in a tempdir, `[games.deusex].paths` → UED22) makes the whole class-and-texture
  tier differential-testable with no gitignored assets.
- **Four prior-art harnesses already exist here**, all one shape: a case registry, a documented
  comparator with explicit normalizations, committed goldens as the standing gate, an
  integration-gated re-bless path. Generalize it; don't invent one (`intersect_cases.py` +
  `merge_compare.py` + `editor_oracle.py` is the cleanest).
- **Diffing stdout is not enough.** Mutating verbs write a *directory tree*
  (`maps/<level>/actors/<name>/{actor.t3d, order_value[, folder]}`), and stderr carries success
  summaries and advisories by design. Four dimensions: exit code, stdout, stderr, output tree.
- **The numeric risk is `Decimal`, not `f64`.** `fmt_vertex`/`fmt_loc` emit fixed 6-dp
  (`+00128.000000`), neutralizing the shortest-roundtrip divergence. What remains: `emit.py` runs on
  `decimal.Decimal` with `ROUND_HALF_UP` and a 28-significant-digit context — `quantize6`'s error
  boundary (~1e22) *is* that context, and `rust_decimal`'s 96-bit mantissa would move it. Plus
  `fmt_coord` and five `:g` sites, for which Rust std has no equivalent.
- **Nobody retires an old path on "zero mismatches".** Every verified project used two gates: a
  corpus-wide quantitative one (Ruff >99.9% similarity; Biome >95% of Prettier's tests; uutils' GNU
  pass count) **plus** a time/exposure one (prereleases, distro adoption, alpha users). A solo-owner
  project has no exposure gate, so corpus breadth has to substitute.
- **Coverage-guided generation across the language boundary is not documented practice.** libFuzzer
  forbids `fork`/`exec` and wants <10 ms/exec; uutils — the closest analogue — gave up guidance for
  its GNU-differential targets and uses libFuzzer as a dumb loop with its own RNG. The defensible
  version is two-phase: cheap Rust-side generation, periodic batch replay against the oracle under
  `coverage combine` as an *adequacy report*, not a feedback loop.

## What we have today

| Thing | State |
|---|---|
| New root | `src/main.rs` (17 lines) `exec`s `old/bin/uedcli` for every verb; `tests/proxy.rs` (2 tests) proves `--help` and one exit-2 case are byte-identical. `Cargo.toml` has zero dependencies. |
| `old/uedcli` | 67,242 LOC production, 73,342 LOC tests across 262 test-package files (242 `test_*.py`). |
| `old/uedcli-native` | 31,938 LOC Rust, 209 `cargo test` tests, **all in-module `#[cfg(test)]`** — no `tests/` dir. |
| Verb surface | 154 `--help` screens / 136 at depth ≥ 3. Families: `brush` 34, `actor` 32, `class` 11, `texture` 11, `level` 10, `sound` 9, `music` 9, `stash` 8, `mover` 7, `prefab` 6, `docs` 4, `cache` 3, `event`/`project`/`substrate`/`uscript` 2 each, `serve` 1. |
| Offline suite speed | `bin/test` = pytest (`-n 4 --dist=loadfile`, private tmpfs `TMPDIR`) + containerized `cargo test`. `dev/docs/rules/tests.md`: "**cuts the suite from ~26 min to ~2 min**". |
| CI | `old/.github/workflows/build-standalone.yml` only (release tags). **No CI runs the test suite**, and the new root has no `.github/` at all. |
| Worktree bootstrap | `old/.venv` is absent in a fresh worktree; `old/bin/uedcli` fails fast until `old/bin/build` runs (needs Docker). |

## Findings

### 1. What `old/`'s suite pins, and the three tiers

Classifying all 242 `test_*.py` by whether they reference the git-tracked UED22 corpus, the
gitignored install, or `pytest.mark.integration`:

| Tier | Files | LOC | Needs | Usable by a subprocess harness? |
|---|---|---|---|---|
| A — no external dependency | 158 | 43,864 | nothing beyond the venv | Yes, but see §2 — these are in-process unit tests |
| B — git-tracked UED22 | ~60 | — | `old/uned/UED22` (214 files, committed) | **Yes** — fully hermetic |
| C — gitignored install | 15 | — | user-supplied Deus Ex / Unreal Gold assets | No (machine-dependent) |
| D — live editor | 28 | — | `dx-lum-uned` container (Docker + Wine) | No |

Biggest files and what they pin: `test_dispatch.py` (2208) in-process verb routing;
`test_serve_app.py` (2132) the GUI backend; `test_actor_survey.py` (1935) spatial relations;
`test_preview_native.py` (1787) / `test_preview.py` (1393) the renderers; `test_polyalign.py` (1394)
UV alignment; `test_engine_facts.py` (1384) decoded-substrate facts; `test_normalize.py` (1265) the
canonicalizer.

Liftable data fixtures (4.5 MB under `old/uedcli/tests/fixtures/`):

| Fixture | Size / count | What it is | Lift |
|---|---|---|---|
| `builder_parity.json` | 27 KB, 21 cases | editor-captured world-vertex sets + builder face counts | trivial |
| `intersect/*.t3d` | 17 files, 140 KB | editor `BRUSH FROM (DE)INTERSECTION` goldens | trivial |
| `csg_golden/*.json` | 6 files, 44 KB | editor BSP node/leaf/surf captures | trivial |
| `parser_baseline/help.json` | 282 KB, 154 screens | every `--help` at `COLUMNS=80` | **argparse-shaped** — see §2 |
| `parser_baseline/action_tree.json` | 612 KB | every action's dest/nargs/default/choices/metavar/mutex group | lift as a *spec*, not a golden |
| `parser_baseline/argv_corpus.json` | 17 KB, 22 cases | argv → outcome/exit/stdout/stderr/namespace | the only argv-level corpus |
| `resolve_golden/nyc_bar.json` | ~2 MB | package-resolution golden | trivial |
| `level_small.t3d` + 6 `.t3d` | 160 KB | real level and brush bodies | ready-made inputs |
| `*.utx`, `*.pcx`, `uscript/**/*.u` | ~1.2 MB | binary package/texture fixtures | trivial as bytes |
| `schema_golden_fire_v3.marshal` | 5.6 KB | **Python `marshal`** | re-serialize through `old/` first |
| 4 `*_golden*.png` | 31 KB | renderer goldens | needs an image comparator |

### 2. The CLI-boundary gap

`test_dispatch.py` builds `argparse.Namespace(...)` by hand and calls `dispatch(args)`; 36 files use
`build_parser()` and go argv → `parse_args` → `dispatch` with `capsys`. **All of it in-process**, and
`tests/conftest.py` has five autouse fixtures, two load-bearing for offline running:
`_stub_author_validation` (no-ops `ingest.validate_ingest_actors` and `_validate_texture_ref`) and
`_stub_mover_class_index` (hands every "is this a Mover?" query a `StubClassIndex`). A subprocess
harness gets neither. So the suite's 4,430 test functions give data fixtures, case registries and
documented comparators — not CLI-level differential cases.

Two corollaries:

- **`help.json` is a trap as a golden.** It is argparse's exact wrapping at `COLUMNS=80`; a
  clap-based parser will not reproduce it byte-for-byte, so `tests/proxy.rs`'s `--help` byte-identity
  assertion dies the moment parsing is ported. Whether to bug-compatibly reproduce argparse's help
  rendering is an owner decision, not a harness detail. `action_tree.json` is the more useful
  artifact: a machine-readable spec a Rust-side test can hold the clap tree to (same dests, nargs,
  defaults, choices, metavars, mutex groups) without claiming identical prose.
- **Parts of the suite are blind by construction** — per
  `board/inbox/weak-test-assertions-covariant-normal-abs-blind`: `abs()`-wrapped normal checks that
  can't see an inverted face, a "reference" that is the same formula as the code under test, exit-2
  tests that check only the return code. Differential testing strictly dominates lifting those,
  since it compares the whole output.

### 3. Which verbs are cheap to differential-test

By declared dependency (from `cli/dispatch.py` docstrings, each module's own docstring, and counting
`resources.`/`package_path_or_exit`/`validate_ingest` references per command module):

| Tier | Verbs | Needs | Count of `resources.` refs |
|---|---|---|---|
| 0 — nothing | `docs list\|show\|search` | nothing at all ("no project, no ambient level, no games config, no editor") | 0 |
| 0 — `$UEDCLI_HOME` only | `cache clear\|gc` | a writable cache dir | 0 |
| 0 — files in, files out | `uscript compile` | source dir (+ import packages); "fully offline, no editor and no docker" | 0 |
| 1 — project + packages | `brush build`, `actor build`, `class *`, `texture *`, `sound`/`music`, `substrate`, `event`, `project show` | `uedcli.toml` + `~/.uedcli/config.toml` + package path → **satisfiable from committed UED22** | 1–12 |
| 2 — tier 1 + a trunk | `actor edit/folder/label/prop/relation`, `brush edit/poly/vertex`, `mover`, `stash`, `prefab` | a `maps/<level>/` tree; output is a directory diff | 1–6 |
| 3 — editor / renderer | `level materialize/photo/preview`, `serve` | Docker + Wine, or the native renderer | 29 (`level.py`) |

The spec names a brush builder as PR #2's slice. The *function* is genuinely pure: `builders.py` is
763 LOC importing only `emit.clean`, `geometry`, `model`, `profile` — eight shapes (`cube`,
`cylinder`, `cone`, `sheet`, `staircase`, `spiral_staircase`, `extrude`, `revolve`) plus
`make_brush_actor`. The *verb* is tier 1: `cli/commands/brush/build.py`'s `run()` ends with
`ingest.validate_ingest_actors(actors, args)`, which goes through `resources.package_path_or_exit` →
`resolve_project` + `config.load_user_config` and then scans the game `.u` for `Engine.Brush` and the
`--texture` ref. With no project it is a clean exit 2, not a T3D snippet.

So PR #2's harness has to choose: differential-test the error path only (cheap, nearly worthless),
or stand up the hermetic tier-1 environment. The second is a one-time cost and unlocks ~50 verbs.

### 4. The oracle's cost model (measured here, 2026-10-03)

| Operation | Time |
|---|---|
| bare `python3 -c pass` | 74 ms |
| `from uedcli.cli.main import build_parser; build_parser()` — in-process, cold | 1438 ms |
| same, warm subprocess, min of 5 | 679 ms (median 914 ms) |
| import + parser build, second measurement | 782 ms |
| `dispatch()` for `brush build cube`, 20 reps | **min 1.68 ms, median 2.50 ms** (3551 bytes stdout) |

`old/bin/uedcli` adds a bash wrapper, `check_venv` and `check_native_ext` on top. So a
process-per-case harness pays ~0.8–1.0 s for ~2 ms of work: **>99% overhead**.

The frozen-`old/` rule says behavior is frozen but "Tooling and dev-infra additions that don't change
any verb's behavior … are fine to add directly to `old/`". A batch runner reading newline-delimited
argv from stdin, forking per case after the import, emitting one JSON result per line is exactly that
shape. Caveat to validate, not assume: fork-after-import is **not** identical to a fresh process
(warm `sys.modules`, module-level memos, inherited env), so the batch path needs cross-checking
against the per-process path on a sample — `parser_baseline.py`'s own `compute_import_closure` exists
because that distinction already mattered once.

Also measured: four `brush build` shapes gave byte-identical stdout across two runs in one process —
the pure-geometry path has no observable nondeterminism to filter.

### 5. Rust-side prior art already in this repo

`old/uedcli-native` is the model for fixture-driven Rust tests, with one stylistic note: **209 tests,
zero integration-test files** — everything is `#[cfg(test)] mod tests` inside the module, with
fixtures pulled in via `include_str!`/`include_bytes!` from `../fixtures/`.

`src/paths_golden.rs` (245 LOC) is the sharpest example: fixture loaders (`load_world`,
`load_expected`) parse a committed whitespace-delimited format generated by committed Python scripts
(`fixtures/paths/extract_world.py`, `extract_fixture.py`); `graph_diff` returns `Vec<String>` of
human-readable differences rather than asserting field by field, so a failure prints the whole diff;
**known divergences are pinned numerically, not allowlisted vaguely** (one test asserts
`diffs.len() == 3` for the undecoded `findPathToward` gap on three named nodes, another
`(g.specs.len(), shared) == (889, 889)` and `diffs.len() == 81` with the mechanism written out) — so
a new divergence fails and a fixed one also fails; and uncommittable fixtures go behind `#[ignore]` +
an env var (`UEDCLI_PATHS_FIXTURE_DIR`).

The Python side has four harnesses with the same architecture, differing only in oracle:

| Harness | Case registry | Comparator | Oracle | Standing gate |
|---|---|---|---|---|
| brush builders | `builder_parity_cases.py` `CASES` (21), `OFFLINE_ONLY` (6) | `worst_err` bidirectional nearest-neighbour, `PARITY_TOL = 1e-4`, + `builder_poly_count` structural guard | live editor via DEINTERSECTION | `test_builder_parity.py` vs `builder_parity.json` |
| brush (de)intersect | `intersect_cases.py` `CASES` | `merge_compare.py` — world-space rebasing, `brushcsg.POLY_FLAG_MASK`, ring rotated to its smallest vertex, `QUANT = 1000.0`, orientation significant | `editor_oracle.py` (integration-gated) | `test_brush_merge.py` vs `fixtures/intersect/*.t3d` |
| CSG/BSP | `native/csg_golden.py` `CORPUS` | `compare(…, thresh_normals=2e-5, thresh_points=0.002)`; counts exact, surfs by nearest oriented plane | ephemeral editor | `test_csg_golden.py` vs `fixtures/csg_golden/*.json` |
| parser | `parser_baseline.py` `ARGV_CORPUS` (22) | exact JSON equality after `_norm_value` (tagged `Decimal`, tuples→lists), `COLUMNS` pinned | the parser itself | `test_parser_baseline.py` |

Every one states what the comparison **cannot** catch — `builder_parity_cases.py` is explicit that a
vertex set is winding-invariant and reflection-invariant for centred shapes. That discipline, writing
the blind spots down next to the comparator, is what makes a retire criterion meaningful rather than
decorative.

### 6. Comparator design: four dimensions, not one

`tests/proxy.rs` compares `stdout`, `stderr`, `status.code()`. Right for proxying, insufficient for a
ported mutator:

- **Output tree.** `t3dtree.write_actor_tree` writes `<tree>/actors/<name>/{order_value, actor.t3d}`
  plus an optional `folder` sidecar, atomically. Ten command modules call `.save()`, so a mutating
  verb's real output is a tree and a tree-diff is mandatory. Minor hazard: the temp name embeds the
  PID (`.actor.t3d.tmp<pid>`), so a diff must ignore leftovers rather than read them as content.
- **stderr is contractual, with different semantics.** `test_cli_consistency.py` pins "mutator
  success-summaries go to STDERR (stdout stays pipe-clean)", and `brush build`'s
  `_advise_swept_brush` prints advisories there. uutils' published oracle contract deliberately
  **excludes** stderr from equality; here it carries behavior, so excluding it would hide real drift.
  Decide per channel, explicitly.
- **`canonical_actor_t3d` is an oracle-free invariant** — documented as idempotent, props sorted,
  geometry in declared order. So `canonical(parse(canonical(a))) == canonical(a)` holds the Rust side
  to a property with no Python running, the same move as Ruff's formatter stability check and Biome's
  idempotence invariant.

### 7. Nondeterminism and float formatting

The good news: T3D coordinates go out through `fmt_vertex` (`+00128.000000` — explicit sign,
5-digit zero-padded integer part, fixed 6 dp) and `fmt_loc` (`f"{d:.6f}"`). Fixed-precision output
sidesteps the whole Python-vs-Rust shortest-roundtrip divergence.

The specific divergence sites that remain:

| Site | Python behavior | Rust risk |
|---|---|---|
| `emit.clean`/`quantize6` | `Decimal`, `ROUND_HALF_UP`, 28-sig-digit context; the context *is* the error boundary ("6 decimal places within 28 significant digits", wall ≈ 1e22) | `rust_decimal` is a 96-bit mantissa (~28–29 digits) — close, not equal. The `CoordinateError` boundary would move. Verify empirically. |
| `emit.fmt_coord` | `Decimal.normalize()` then `format(…, "f")` — exact decimal, trailing zeros dropped, never E-notation | needs an explicit decimal formatter, not `{}`/`{:?}` |
| five `:g` sites in production messages (`cli/commands/brush/build.py:149`, `utexture.py:1292`, `utexture_decode.py:281`, `preview_shots.py:119,196`) | Python `%g`: 6 significant digits, trailing zeros stripped, two-digit signed exponent | Rust std has **no** `%g`; RFC 2729 (`{:g?}`) was never merged. Needs hand-rolling or `lexical-write-float` |
| any bare `{}` on an f64 | — | Rust `Display` never uses exponent form at any magnitude; `Debug` switches at 1e-4/1e16 since 1.58 but spells it `1e16`/`1e-5` vs Python's `1e+16`/`1e-05`. `-0.0` prints `-0` under `Display`, `-0.0` under `Debug`, `-0.0` in Python |
| `serde_json` output | `json.dumps` | `serde_json` 1.0.151 formats via `zmij` (Schubfach), which uses exponent form at the extremes — three different spellings for one f64 |

Mitigation, strongest first: pin an explicit output format in the Rust CLI rather than relying on
`{}`/`{:?}`/serde defaults; else normalize in the comparator (regex redactions). Also normalize or
pin on both sides: trailing newline at EOF, `NO_COLOR`/`TERM=dumb`, `LC_ALL=C` (uutils does this for
its GNU reference), and `COLUMNS` (already pinned to 80 by `parser_baseline.py`).

A cheap robustness trick from Twitter's Diffy that applies directly: **run the Python oracle twice**
on each input. Anything that differs between two oracle runs is noise by definition, auto-allowlisted
rather than hand-maintained. GitHub's Scientist recommends the same thing (a baseline experiment
where both arms run the control) to establish the expected mismatch floor.

### 8. External prior art: how real rewrites measured parity and retired the old path

| Project | Input corpus | Progress metric | Parity bar |
|---|---|---|---|
| Ruff formatter vs Black | 6 real repos (django 2752 files, transformers 2527, typeshed 3627, zulip 1424, warehouse 641, twine 32) | "similarity index" = unchanged / (unchanged + removed) lines in the Black↔Ruff diff | >99.9% on Black-formatted code + zero `not_yet_implemented` markers, then alpha users on 500k-LOC monorepos |
| Biome vs Prettier | Prettier's own test suite, converted to plain files | matching cases / total, per language | contractual >95% of Prettier's JS tests; achieved 96.10% from an 85% baseline |
| oxfmt (oxc) | Prettier conformance tests | pass % | 100% of JS+TS conformance tests at Beta (~95% at Alpha) |
| oxc parser | test262 / Babel / TypeScript upstream fixtures | counts **committed as `*.snap`** — the snapshot diff *is* the report and the gate | e.g. Babel 2093/2101 (99.62%) |
| uutils coreutils | GNU's own 630+ test scripts (25 kSLOC) + 4200 own tests | daily PASS/FAIL/ERROR/SKIP dashboard | no % gate; distro adoption (Ubuntu 25.10) was the bar; a bot checks whether a failure also fails on `main` |
| Deno Node compat | Node's own test suite via `config.jsonc` | pass % dashboard (76.22%, 3401/4462) | — |
| Copilot runtime TS→Rust | the pre-existing E2E suite, **frozen** | releases shipped, regressions per porting PR | 100 prereleases at 10.5% of downloads, 128 PRs / 135 releases over 14.5 weeks |
| GitHub Scientist | production traffic | mismatch counters | explicitly no published number — "reasonable confidence" |

Techniques that transfer directly:

- **The harness takes two binaries as argv and runs over a corpus.** Ruff's `ruff-ecosystem`
  (`ruff-ecosystem check ruff ./target/debug/ruff`) runs on every PR, pulls the baseline from the
  merge-base artifact, caches checkouts, has `--output-format json`, and posts a markdown diff as a
  PR comment — with explicit `ruff-then-ruff` and `black-and-ruff` modes, i.e. one harness for
  new-vs-old *and* new-vs-foreign-oracle. `mypy_primer` is the same pattern over 149 projects.
- **A diff is a review object, not a failure.** Ruff asks contributors to walk the ecosystem report
  in the PR body and harvest new test cases from it.
- **Freeze the old project's tests.** The Copilot migration's rule: tests validating the port "can't
  themselves be re-written during the porting, or else you lose your oracle".
- **Commit the counts.** oxc writes conformance results to version-controlled `*.snap`; uutils keeps
  an `ignore-intermittent.txt` allowlist and tags entries `_(new)_` vs `_(intermittent)_`. A
  checked-in per-verb parity snapshot is dashboard and gate at once: a new name fails, a vanished
  name is the win.
- **Intentional divergence needs an enumerable registry — a document, not a code comment.** Ruff's
  "Known deviations" page; uv's ~25-topic "Compatibility with pip"; oxfmt's divergence discussion,
  whose default policy is worth copying verbatim: *always assume a difference from the oracle is a
  bug, except for the cases already listed here.*
- **Grammar-guided argv generation beats byte fuzzing for CLIs.** uutils' `uufuzz` generates argv
  from each command's own synopsis so time isn't spent on invalid inputs; it found real GNU
  divergences. The grammar already exists here: `parser_baseline/action_tree.json` describes every
  flag's nargs, choices, converter and mutex group.
- **A bucket for the structurally unverifiable.** uutils separates `INCOMPATIBLE` tests that assert
  on the oracle's internals (`LD_PRELOAD`, `gdb`). The analogue here is every Python test that
  monkeypatches an internal seam — per §2, most of them.

The frozen-`old/` rule already handles "the oracle is wrong" better than most of these projects: a
confirmed `old/` bug becomes a `TODO` in the new Rust code, fixed when the verb is properly ported.
That is the "deliberately diverge and document" branch, pre-decided.

### 9. Input generation

| Tool | Version / status | Fit here |
|---|---|---|
| `proptest` | 1.11.0 (2026-03-24), active | **Best fit.** `Strategy` objects compose, `prop_assert_eq!` returns a failure (so shrinking works) instead of panicking, `proptest-regressions/` persists shrunken seeds next to the source. `fork` + `timeout` bound a hung oracle per case. The book's advice — build valid-by-construction via `prop_map` rather than `prop_filter` — is exactly right for brush flag tuples and T3D actors. Documented downside: richer shrinking makes generation slower than quickcheck. |
| `quickcheck` | 1.1.0, near-dormant (commits jump 2021→2026) | type-driven only; its own README points at proptest for shrinking. Skip. |
| `arbitrary` + `cargo-fuzz` | 1.4.2 / 0.13.2, active | Blocked by the oracle. libFuzzer forbids `fork`/`exec` and wants <10 ms/exec. uutils' GNU-differential targets take `|_data: &[u8]|` and ignore libFuzzer's bytes entirely, using their own `rand` — libFuzzer as a loop driver, no coverage guidance. Their pure-parser targets are the ones that stay in-process. |
| `bolero` | 0.13.7 (2026-10-03), very active | One test body across libFuzzer/AFL/honggfuzz/Kani/random. Attractive *later*: it avoids maintaining both a `Strategy` and an `Arbitrary` impl. Needs `binutils-dev`/`libunwind-dev`. |
| dedicated differential crates | — | None worth taking. `difftest` 0.2.0 exists with 29 total downloads. |

Measured reference points for the cost of a cross-language oracle: subprocess-per-exec on JVM/.NET
measured 2–3 s/exec ("eliminated real-time fuzzing viability"); a **persistent worker over shared
memory / a pipe** got 6–15 ms and is described as "trivial to implement and just works" for
interpreted languages. AFL's own persistent mode is "at least 10 times faster than the forkserver".
This is the same conclusion §4 reaches from local measurement, from an independent direction.

### 10. Comparator plumbing: which Rust crate

| Crate | Version | Spawn CLI | Binary bytes | Whole dir tree | Redaction | Accept diffs |
|---|---|---|---|---|---|---|
| `snapbox` | 1.2.2 | yes (`cmd::Command`, `OutputAssert`) | `Data::binary()`, `detect-encoding` | **yes** — `dir::PathDiff::{subset_eq_iter, write, overwrite}` | `Redactions`, `normalize_paths` on by default | `SNAPSHOTS=overwrite` |
| `trycmd` | 1.2.1 | yes (`$ cmd`, `? <status>`) | `binary = false` opt-out | **yes** — `*.in/` as CWD, `*.out/` as expected tree | `[EXE]`/`[ROOT]`/`[CWD]`/`[..]`/`...`, `insert_var` | `TRYCMD=overwrite`, `TRYCMD=dump` |
| `insta` (+ `insta-cmd`) | 1.49.0 / 0.7.0 | via `insta-cmd` | `assert_binary_snapshot!` is **experimental** | no (`glob!` iterates inputs only) | best-in-class: regex filters, serde redactions, `rounded_redaction`, `strip_ansi_escape_codes` | `cargo insta review` |
| `assert_cmd` + `predicates` | 2.2.2 / 3.1.4 | yes, canonical | not documented | no — docs punt to `dir-diff` | predicates only | none |
| `goldenfile` | 1.11.0 | no | yes (`binary_diff` by extension) | explicit per-file only | none | `UPDATE_GOLDENFILES=1` |
| `expect-test` | 1.5.1 (feature-complete) | no | no | one file per expectation | none | `UPDATE_EXPECT=1` |
| `dir-diff` | 0.3.3 (frozen) | no | byte compare | `is_different(a,b) -> bool` only — **no per-file report** | none | none |

The decisive property is that the migration has **two phases**: phase 1 the oracle *is* the
expectation (no stored value); phase 2 `old/` is gone and the expectation must be frozen. Only
`snapbox` is mode-agnostic: `assert_data_eq!` takes `impl IntoData`, implemented for `&str`,
`String`, `&[u8]`, `Vec<u8>`, `Data` and `Inline` — so the expected side can be the oracle's runtime
output in phase 1 and a `file!`/`str![]` snapshot in phase 2, with the same normalizers, redactions
and diff renderer. `PathDiff::subset_eq_iter` diffs two arbitrary directories (oracle out-dir vs Rust
out-dir) and `PathDiff::overwrite()` is the phase-2 accept path. (Inferred, not documented:
auto-update can only rewrite the `Inline`/`file!` forms, since a runtime `String` has no source
location.) No authoritative source documents using `insta` or `trycmd` for A/B oracle comparison; the
documented prior art for that is bespoke harnesses (`ruff-ecosystem`, `mypy_primer`, `uufuzz`).

### 11. Coverage

**Python oracle.** Supported, and the shape needed is the shape provided. `coverage.py` 7.16.2; since
7.10.0 `patch = subprocess` auto-instruments children created via `subprocess`, `os.system()` and the
`exec`/`spawn` families (older route: `COVERAGE_PROCESS_START` plus a `.pth` calling
`coverage.process_startup()`). With `parallel = True` each run drops a `.coverage.*` file and
`coverage combine` merges them — exactly "accumulated coverage over the whole corpus". Caveats for a
CLI oracle: data is written on normal exit only, so `[run] sigterm` and `patch = _exit` cover the
abnormal paths. `COVERAGE_CORE=sysmon` cuts overhead substantially (PyPI's suite went 58 s → 27 s on
that switch alone) but on 3.12/3.13 must be opted into and can't combine with branch coverage.
Per-run cost is then interpreter startup plus the `.coverage.*` write — a periodic batch job, not a
per-case cost.

**Rust side.** `cargo-llvm-cov` 0.9.1. A binary spawned *by* an integration test **is** covered: the
instrumented child writes its own `.profraw` (`default_%m_%p.profraw`, `%p` = PID) and
`llvm-profdata merge` folds them in. Accumulate with `cargo llvm-cov clean --workspace`, N×
`cargo llvm-cov --no-report`, then `cargo llvm-cov report --lcov`. Failure mode: a child SIGKILLed
before flushing writes a truncated `.profraw` that breaks the merge — reap children cleanly.

**Cross-language coverage-guided corpus generation: not documented practice.** Coverage-guided
*differential* testing is well established (NEZHA, IEEE S&P 2017, guides on δ-diversity —
asymmetries *between* implementations, not one program's coverage). The nearest paper to this exact
situation — tHinter (arXiv:2501.09475, auto-translated Python→C++, AFL++, a 90% line-coverage
stopping condition) — collects coverage on the **translated side only**. Nothing was found that
instruments a source-language oracle and feeds its coverage back as fuzzer fitness. Coverage
*saturation* as a stopping criterion is itself defensible (Green Fuzzing, ISSTA'23: stopping 24 h
campaigns 6–12 h early on saturation missed <0.5 bugs on average).

So: two-phase and offline. Grow the corpus cheaply Rust-side; periodically replay the whole corpus
against the instrumented oracle and report `coverage combine` output as a **corpus-adequacy gate**.

### 12. Mutation testing the Rust side

`cargo-mutants` 27.1.0 (2026-06-02), self-described as a "semi-actively-maintained spare time
project"; on the ThoughtWorks Technology Radar. `mutagen` is dead (last commit 2022-07-29). It copies
the tree to a scratch dir, applies one mutant at a time, checks viability with `cargo test --no-run`,
then runs the tests; outcomes caught / missed / unviable / timeout. Operators: function-body
replacement by guessed return value, binary-operator swaps, unary-operator deletion, match-arm
deletion, match guards → `true`/`false`, struct-field removal. Cost ≈ (viable mutants) ×
(incremental build + test run); `--shard K/N`, `--in-diff FILE`, `--baseline skip`, `--timeout`
(default 5× baseline, min 20 s). Limitations that bite here: it **ignores `.cargo/config.toml`**,
does **not understand `#[cfg(...)]`**, and draws wrong conclusions from non-hermetic tests.

The subtlety inverts the usual pitch: under a differential suite the oracle *defines* the
expectation, so every behavior-changing mutant in the ported verb **should** be caught by
construction. That makes a **surviving mutant a proof that the harness is blind** — a corpus gap (no
input reaches that path) or a missing comparison dimension (stdout diffed but not exit code, not the
written tree, or over-normalized). It is the cheapest available answer to "is my corpus actually
exercising this verb?" with no Python instrumentation at all.

Two mandatory exclusions: mutate only the ported verb, never the harness (mutating the comparator can
make both sides agree trivially and nothing fails); and tune `--timeout`, because a looping mutant
looks identical to a slow oracle.

### 13. Test-suite speed: the pain, current state

`speed-up-the-offline-test-suite` measured (2026-09-12) `bin/test` at **1594 s pytest + ~12 s
`cargo test`**, pytest ~99% of it, no single dominant test (top 20 slowest = 353 s / 22%; the other
78% across ~6000 tests). It also found a correctness bug while measuring — **1423 cascading
`FileNotFoundError`s** from a shared `TMPDIR`, mechanism still unconfirmed. Items 1–4 landed
(`-n 4 --dist=loadfile`, a private per-invocation tmpfs `TMPDIR` with a 7-day reaper,
`@pytest.mark.slow` gating the 173 s retail-map test); `dev/docs/rules/tests.md` now records "~26 min
to ~2 min". Item 5 (a memo-warm/disk-cache-off `schema_cache.py` mode) was descoped.

So the pytest suite is **not** the harness's pain. The three that are: (1) **per-worktree
bootstrap** — `old/.venv` is absent in a fresh worktree and `old/bin/uedcli` fails fast until
`old/bin/build` runs (needs Docker); `UEDCLI_VENV=<dir>` is a documented knob
(`bin/build-standalone` uses it) so a machine-shared path would amortize it, unverified whether
`ensure_venv`'s symlink rewriting tolerates concurrent worktrees. (2) **per-invocation startup** — the
782 ms import (§4). (3) **module-scoped UED22 decode** — three modules decode the real corpus in a
`scope="module"` fixture (why `--dist=loadfile` is needed); a harness re-resolving the class index
per case pays the same cost, so the committed-UED22 tier needs a warm-index strategy.

## Options

| Option | Pros | Cons |
|---|---|---|
| **A. Process-per-case, `snapbox` comparator, hand-curated corpus** (smallest thing that works) | No change to `old/`; nothing to validate about fork semantics; `snapbox` carries into phase 2 unchanged; `tests/proxy.rs` already has the skeleton | ~1 case/s caps the corpus at tens-to-hundreds; property-based testing is out of reach; coverage of `old/` stays unmeasured |
| **B. A + a batch oracle runner in `old/bin/`** | ~300× more cases for the same wall time; makes `proptest` viable; spec explicitly permits non-behavioral `old/` tooling | Fork-after-import is not identical to a fresh process and must be cross-validated; one more moving part in the frozen tree |
| **C. B + `proptest` strategies driven from `action_tree.json`** | The flag grammar already exists as data; valid-by-construction argv; shrinking gives minimal repro cases; `proptest-regressions/` persists them | Writing a `Strategy` per verb family is real work; `action_tree.json` describes argparse, so it needs a translation layer |
| **D. C + `cargo-fuzz`/`bolero` coverage-guided** | Best input discovery in principle | libFuzzer forbids `fork`/`exec`, wants <10 ms/exec; the closest real project (uutils) abandoned guidance for exactly this reason. Needs a persistent-worker oracle first |
| **E. Lift fixtures only; no live oracle** | Zero oracle infrastructure; fast; survives `old/`'s deletion by construction | Covers only what someone already thought to test — and §2 shows parts of that are blind by construction. The spec names this *complementary*, not primary |
| **F. Phase 2: freeze the oracle's answers into `trycmd` case files** | One artifact per case covering CWD tree + exit status + stdout/stderr; `TRYCMD=overwrite` re-blesses | Locks the fixture format early; its ability to drive a Python oracle is undocumented; a second comparator to maintain alongside phase 1's |

## Proposal (owner's call — not decided)

**Option B now, C when the second verb family lands.** Concretely:

```
tests/
  parity.rs                 # the one cargo-test entry point for differential cases
  parity/
    mod.rs                  # Oracle (batch or per-process), Observation, compare(), normalize()
    env.rs                  # hermetic fixture env: tmp UEDCLI_HOME + UEDCLI_PROJECT -> old/uned/UED22
    verbs/
      brush_build.rs        # per-verb: the case generator + the divergence registry
  fixtures/
    lifted/                 # phase-2 goldens lifted from old/uedcli/tests/fixtures (verbatim bytes)
    parity/
      brush_build.snap      # committed counts + the exact list of known-diff case ids
dev/research/               # this note
```

- **`Observation` is a small frozen struct**, not a tuple: `exit_code`, `stdout`, `stderr`,
  `tree: BTreeMap<RelPath, Vec<u8>>`. All four compared, each with its own normalizer, and the
  comparator's blind spots written down next to it — the discipline `builder_parity_cases.py` and
  `merge_compare.py` already use.
- **A verb declares its input generator** as one registry entry, mirroring `intersect_cases.py`
  (one registry, two consumers):

  ```rust
  parity_verb! {
      name: "brush build",
      env: Env::Tier1,                       // tmp project + committed UED22 package path
      cases: || CASES.iter().cloned(),       // the fixed corpus: ids + argv + optional stdin
      strategy: Some(brush_build_strategy()), // proptest Strategy -> argv, added at option C
      known_diffs: &["revolve_facet_message"], // ids expected to differ, with a reason each
      channels: Channels::ALL,
  }
  ```

  The fixed corpus runs on every `cargo test`; the `Strategy` runs under `PROPTEST_CASES` in a
  longer soak. `known_diffs` is the enumerable registry, with oxfmt's policy as the default:
  *assume any difference is a bug except the ids listed here.*
- **The oracle is batch-mode with a per-process cross-check.** A runner added to `old/bin/`
  (non-behavioral tooling, permitted by the spec) reads newline-delimited argv JSON and emits one
  result per line. `parity/mod.rs` keeps a `--per-process` mode and a job that re-runs a random
  sample of every verb's corpus through it asserting identical observations — so the amortization is
  proven, not assumed.
- **Oracle-run-twice noise baselining**, Diffy/Scientist style: any field differing between two
  oracle runs on the same input is recorded as noise rather than hand-allowlisted.
- **Oracle-free invariants per verb**: `canonical_actor_t3d` idempotence, parse→emit→parse
  round-trip, and `action_tree.json`-derived flag-surface assertions.
- **Retire criterion — four gates, all required, recorded in `fixtures/parity/<verb>.snap`:**

  | Gate | Bar |
  |---|---|
  | Corpus | The verb's fixed corpus is non-empty, covers every flag and every documented error path, and shows **zero** unregistered diffs across all four channels. |
  | Property soak | ≥100k generated cases (`PROPTEST_CASES`) with zero unregistered diffs, and the `proptest-regressions/` file for that verb empty or fully explained. |
  | Oracle coverage | A batch replay of the corpus under `coverage.py` + `coverage combine` covers ≥X% of the verb's own `old/` module lines, with every uncovered line named and justified. X is the owner's number — tHinter used 90% and said 100% is impractical. |
  | Harness adequacy | `cargo-mutants` over the ported verb's source (harness excluded) reports zero **missed** mutants. A survivor means the harness is blind, not that the port is fine. |

  Then: remove the verb from the dispatch table, and in the same PR convert its corpus to frozen
  fixtures so the gate survives `old/`'s deletion. The `.snap` diff is both the progress report and
  the regression gate — oxc's pattern.
- **`--help` is a separate decision, not a harness detail.** `tests/proxy.rs`'s `--help`
  byte-identity assertion cannot survive porting argument parsing to clap. Proposal: retire it then,
  replace with `action_tree.json`-derived structural assertions plus `test_help_completeness.py`'s
  rules reimplemented Rust-side, and record "argparse help prose is not reproduced" as the first
  entry in a repo-level known-divergences document.

## Open questions / what to verify next

1. **Is fork-after-import observationally identical to a fresh process** for the verb families being
   ported? Needs a measured answer on a sample before the batch oracle is trusted. (Warm
   `sys.modules`, module-level memos, `UEDCLI_SCHEMA_CACHE`.)
2. **Does `rust_decimal` (or `bigdecimal`) reproduce `emit.quantize6`'s error boundary** and
   `ROUND_HALF_UP` behavior at the edges? The 28-significant-digit Python context *is* the documented
   limit; a different mantissa moves a user-visible `CoordinateError`.
3. **Can `UEDCLI_VENV` point at a machine-shared venv** used from several worktrees at once, given
   that `ensure_venv` rewrites container-baked symlinks to a host path? If yes, per-worktree
   bootstrap drops to zero.
4. **What is the oracle-coverage bar X**, and is it measured per verb module or per touched line? The
   literature's only concrete number is tHinter's 90%.
5. **Is stderr contractual?** uutils explicitly excludes it; here it carries success summaries and
   advisories. Likely per-channel-per-verb rather than global.
6. **Does the harness need the gitignored assets at all**, or does committed UED22 cover every tier-1
   and tier-2 verb? If some verb needs the real install, it needs the `#[ignore]` + env-var treatment
   `paths_golden.rs` already uses for the retail map.
7. **`cargo-mutants` on a workspace with a Docker-containerized build step** — it ignores
   `.cargo/config.toml` and doesn't understand `#[cfg]`. Unverified whether the new root's build is
   simple enough for that not to matter.
8. **Nothing runs the test suite in CI today.** The retire criterion's four gates are only as real as
   whatever enforces them; worth deciding whether that is `bin/test`, a new root-level script, or CI.

## Sources

**Internal** (read directly in this worktree): the rewrite spec and the
`speed-up-the-offline-test-suite` / `weak-test-assertions-covariant-normal-abs-blind` board items ·
`old/dev/docs/rules/tests.md` · `old/pytest.ini` · `old/bin/{test,uedcli,_venv.sh}` ·
`old/uedcli/{emit.py,builders.py,trunk.py,t3dtree.py,normalize.py,config.py}` ·
`old/uedcli/cli/{dispatch.py,ingest.py,resources.py,level_sources.py,commands/brush/build.py}` ·
`old/uedcli/tests/{conftest.py,builder_parity_cases.py,parser_baseline.py,intersect_cases.py,merge_compare.py,editor_oracle.py}`
and the test modules named in §1/§5 · `old/uedcli/native/csg_golden.py` ·
`old/uedcli-native/src/paths_golden.rs` · `src/main.rs` · `tests/proxy.rs`. All timings and the
determinism check in §4 were measured here on 2026-10-03 (Python 3.12.13); `cargo`/`rustc` are not
installed in this worktree, so no Rust-side timing was taken.

**Crates / tooling.** §9–§12 and the §10 matrix: docs.rs for `proptest` (`test_runner::Config`,
`FileFailurePersistence`) + proptest-rs.github.io/proptest tutorial/filtering + the README's
`#differences-between-quickcheck-and-proptest`; api.github.com/repos/BurntSushi/quickcheck/commits;
docs.rs for `snapbox` (`dir`, `data::IntoData`, `assert::DEFAULT_ACTION_ENV`), `trycmd`, `insta` (+
insta.rs/docs/{cmd,filters}), `expect-test`, `assert_cmd`, `goldenfile::mint::Mint`, `dir-diff`;
llvm.org/docs/LibFuzzer.html; rust-fuzz.github.io/book (structure-aware fuzzing); docs.rs/arbitrary
`Unstructured`; github.com/camshaft/bolero;
r9295.github.io/posts/differential-fuzzing-accross-languages/;
lcamtuf.blogspot.com/2015/06/new-in-afl-persistent-mode.html;
coverage.readthedocs.io/en/latest/{subprocess,changes}.html;
blog.trailofbits.com/2025/05/01/making-pypis-test-suite-81-faster/;
github.com/taiki-e/cargo-llvm-cov; doc.rust-lang.org/stable/rustc/instrument-coverage.html;
mutants.rs/{,how-it-works,limitations}.html. §7 float formatting: rust-lang/rust#86479,
rust-lang/rust#24556, rust-lang/rfcs#2729, releases.rs/docs/1.53.0/,
docs.python.org/3/whatsnew/3.1.html.

**Rewrite/parity reports (§8).** astral.sh/blog/the-ruff-formatter · astral-sh/ruff#5828 ·
docs.astral.sh/ruff/{contributing,formatter}/ · ruff's `python/ruff-ecosystem/README.md` ·
biomejs.dev/blog/biome-wins-prettier-challenge/ · algora.io/challenges/prettier ·
oxc.rs/docs/learn/architecture/test · oxc.rs/blog/2026-02-24-oxfmt-beta · oxc-project/oxc#14669 ·
uutils/coreutils#14705 · uutils.github.io/coreutils/docs/test_coverage.html · uutils'
`fuzz/uufuzz/src/lib.rs` and `fuzz/fuzz_targets/fuzz_expr.rs` · arxiv.org/html/2608.07135v1 ·
github.blog "Migrating the GitHub Copilot runtime to Rust" · github/scientist (+ its github.blog
post) · OneSignal/thesis · opendiffy/diffy · github.com/hauntsaninja/mypy_primer ·
cs.columbia.edu/~suman/docs/nezha.pdf · arxiv.org/html/2501.09475v1 (tHinter) ·
mboehme.github.io/paper/ISSTA23.pdf (Green Fuzzing).

**Unverified / flagged.** `trycmd` driving a non-native (Python) oracle via
`TestCases::register_bin` is undocumented either way. `zmij`'s exponent threshold/spelling is
undocumented — confirm empirically if JSON output is ever compared. `cargo-mutants` adoption by named
large Rust projects could not be confirmed. §11's oracle-as-fitness-signal gap is an exhaustive
negative from search — "not found", not "does not exist". `rust_decimal` was not benchmarked here;
§7's claim rests on its documented design.

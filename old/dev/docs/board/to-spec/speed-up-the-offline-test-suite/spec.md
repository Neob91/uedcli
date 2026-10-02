# Speed up the offline test suite

Written for a reader with no prior context on `bin/test`. Reviewed once by an independent pass
(2026-09-12); this version folds in the fixes — corrections below are marked where the review
caught a real error, and where I re-verified and found the review itself wrong on a specific.

## Baseline (measured 2026-09-12, this host)

`bin/test` = `ensure_venv` + native-ext build (`maturin build --release`, cached by source hash) +
`pytest uedcli -q` + `cargo test`. Timed cold (native-ext cache marker stale, forcing a real
`--release` rebuild):

| Phase | Time |
|---|---|
| `ensure_venv` | cached, ~0s |
| native ext build | ~9–13s |
| `cargo test` (209 tests) | 12.1s total (0.61s actual run) |
| `pytest uedcli -q` (6163 collected, 4558 passed) | **1594s = 26.5 min** |

Rust is not the bottleneck (an earlier guess that the wheel gets built twice — once `--release` for
the wheel, once debug for `cargo test` — turned out to cost 12s total, not minutes). Pytest is ~99%
of wall time.

`--durations=20` on that run: **the top 20 slowest tests sum to 353s (22%)** — no single test
dominates. **The remaining 1241s (78%) is spread across ~6000 tests.**

**Caveat on this split (review finding, correct):** the run these numbers come from is the same run
that hit the correctness bug below — of 6163 collected, 1423 errored (mostly at setup/teardown, not
in the timed `call` phase pytest's own `--durations` measures) and 14 failed outright. So the
22%/78% ratio is computed over the ~4700 tests that ran cleanly, not the whole suite — directionally
right (no single test dominates; the tail is thousands of small tests), but not exact. Re-measure
cleanly once item 2/3 lands and the run doesn't crash.

### The long tail — per-test fixture overhead × ~6000, not fully attributed

`uedcli/tests/conftest.py` runs **5** `autouse` fixtures on every test (corrected — I missed
`_stub_mover_class_index` on the first pass): `_isolate_uedcli_home`, `_schema_cache_off`,
`_isolate_project_resolution` (does a real `tmp_path_factory.mktemp()` + `chdir()`),
`_stub_author_validation`, `_stub_mover_class_index`. That's real filesystem I/O × ~6000, on
`virtiofs0` (a network/overlay mount at **96% capacity**, not local disk) rather than tmpfs.

**What I have NOT shown**: that this fixture overhead actually accounts for the 1241s. One
`mktemp`+`chdir` per test, ×6000, is plausible as a meaningful chunk of 20 minutes on a loaded
network filesystem, but I have not profiled it — this is inference from shape, not a measurement. A
`--durations=0` histogram or per-fixture timing (`pytest --setup-show` / a manual `time.perf_counter`
wrapper on the autouse fixtures) would confirm or kill this before relying on it.

### A few real hot spots (353s / 22%)

- `test_mapimport_stale_class_package.py::test_retail_unreal_gold_maps_import_fully[*]` — **173s**
  (11% of the whole run). The gitignored Unreal Gold corpus is installed on this host, so this
  decodes 8 real retail `.unr` maps end to end (`[Dig]` 79s, `[Bluff]` 49s, `[Dark]` 21s, plus 4
  smaller) — real regression coverage for `mapimport._resolve_actor_class`'s stale-import-package
  fallback (board: `unreal1-ut99-map-import-stale-class-package`).
- `test_board_script.py` (3 tests) — 72s. `test_dispatch.py::test_actor_find_*` cluster (7 tests) —
  75s. Both do real, uncached class-schema resolution per test (see below).

### A correctness bug, found while measuring this (not a speed issue)

Running the full suite with `TMPDIR` pointed at a repo-local scratch dir (`_scratch/pttmp`, to dodge
the documented shared-`/tmp` problem) still produced **1423 cascading `FileNotFoundError`s** starting
~90% through the run — pytest's own capture/teardown failing because its `tmp_path` tree vanished
mid-run. This is a **live-multi-session hazard, not a performance one**: up to ~1400 spurious
failures, not just slowness.

**Mechanism is NOT confirmed — corrected after review.** My first draft blamed
`tmp_path_factory`'s retention GC (keeps only the last few numbered dirs, "keyed by path, not
liveness"). I read the actual source (`_pytest/pathlib.py`, pytest 8.4.2, this repo's pinned
version) to check that claim and it doesn't hold up: `cleanup_numbered_dir` only deletes a candidate
whose `.lock` file is older than `LOCK_TIMEOUT` (**3 days**, not the "<3h" the review guessed
either) — a concurrently-running session's own numbered dir has a fresh lock and is protected from
another session's cleanup regardless of the keep-count. So neither my original claim nor the
review's specific number survives reading the code. **The actual cause is still open.** Two
candidates, neither verified: (a) something else in this project's own tooling prunes `_scratch/`
during a run — `NATIVE-MATERIALIZE.md` documents `prune_ref_cache.py` doing exactly this kind of
sweep against `_scratch/` from other sessions; (b) `virtiofs0` (96% full, a network/passthrough
mount, not local disk) has a failure mode plain `ext4`/tmpfs wouldn't. Pin this down with a live
repro (strace or inotify-watch `_scratch/pttmp` during a run) before writing up a root cause as fact.
**The fix in items 2/3 below (a private, uniquely-named tmpfs dir per invocation) resolves the
symptom regardless of which of these is the real cause** — nothing else can touch a directory
another session doesn't know exists.

14 of the reported failures are pre-existing/unrelated (stale doc-link and board-shape assertions)
— out of scope here.

## Item-by-item feasibility

### 1. `pytest-xdist` (`-n <N> --dist=loadfile`) — feasible, no blocking hazard found

Scanned for the standard xdist hazards across the non-integration suite:

- **Docker**: 26 files reference `docker`, but every one in the default (`not integration`) run
  fakes it — `test_driver.py` asserts against a recorded call list (`cmd[:3] == ["docker", "exec",
  ...]`), it never shells out. The files that actually drive a container
  (`test_driver_integration.py`, `test_*_integration.py`) are marked `integration` and already
  deselected. No shared container/port contention to worry about.
- **Fixed ports**: none found (`grep` for `bind((`/`localhost:<port>` — empty).
- **Shared mutable disk state**: files referencing `dev/docs/board` from tests (`test_board.py`,
  `test_board_script.py`, `test_doc_links.py`, `test_mapimport_*`, `test_reimport_*`,
  `test_utexture.py`, `test_preview_grid.py`) all *read* it to assert structure/content — none
  writes into the repo tree. Per-test isolation already runs through `tmp_path` /
  `monkeypatch.chdir()`, which is process-local, so xdist workers (separate processes) don't
  collide on it.
- **Real hazard found (review caught this, verified): use `--dist=loadfile`, not the default
  `--dist=load`.** Three files have `scope="module"` fixtures that decode the real UED22 corpus via
  `ClassIndex.from_files(...)`: `test_texture_enum.py:23`, `test_texture_cli.py:68`,
  `test_proceduraltex.py:33`. A module-scoped fixture is per-*process*, not per-suite — under plain
  `--dist=load` (which schedules individual tests to whichever worker is free, with no file
  affinity), tests from one of these modules can land on many different workers, and each worker
  that gets one re-runs that module's corpus decode from scratch. Worst case that's the decode
  running once per worker instead of once, total, which could erase most of the parallelism gain for
  exactly the tests worth parallelizing. `--dist=loadfile` keeps all tests from one file on one
  worker, so each module-scoped fixture still runs exactly once — and it also closes the intra-file
  ordering risk below for free, since a file's tests execute in their original order on a single
  worker.
- **Order-dependency scan**: found no intra-file shared mutable state (module-level test globals)
  that depends on run order, but I didn't exhaustively read all 220 files. `--dist=loadfile` above
  makes this moot for anything at file granularity; anything depending on cross-*file* order would
  already be fragile under plain `pytest -p xdist` too. Close the remaining gap empirically: run once
  under `-n auto --dist=loadfile` and diff pass/fail against a serial baseline before trusting it.
- **Worker count**: don't default to bare `-n auto` unqualified. This host runs multiple concurrent
  agent sessions (see the correctness bug above) — `auto` (one worker per core) competing with
  other sessions' own builds/tests for CPU and the `ClassIndex`/ScreenShot memory each worker holds
  is asserted, not measured, as safe here. Start with a capped count (e.g. `-n 4`, or an env-var
  knob) and raise it only after checking it doesn't regress wall time or memory on a busy host.
- Mechanical cost: add `pytest-xdist` to `_DEPS_SPEC` in `bin/_venv.sh`; `-n <N> --dist=loadfile` in
  `bin/test` (skippable via existing arg passthrough for `-k` debugging, where serial is usually
  preferable anyway).

### 2 & 3. Unique per-invocation temp root, on tmpfs — feasible, folding into one change

These are the same fix. The multi-session collision (above) needs `TMPDIR` to be **unique per
invocation** (not a fixed path, whether that's `/tmp` or a repo-relative dir). The virtiofs-vs-tmpfs
cost (fixture overhead) needs it to be **on tmpfs**. Both are satisfied by one line in `bin/test`:
`export TMPDIR="$(mktemp -d -p /tmp uedcli-test-XXXXXX)"` (`/tmp` is tmpfs on this host, 8G — the
512 MB figure `NATIVE-MATERIALIZE.md` cites for shared `/tmp` is stale or a different mount; `df`
here shows 8.0G, 3% used) with a `trap ... EXIT` to clean it up. No test currently hardcodes a path
that would break under a moved `TMPDIR` (tests passing a *literal* `"/tmp/..."` string, e.g.
`test_cli.py:261`, `test_editor.py:58`, only assert argparse behavior — they never touch the real
filesystem at that path).

**Risks the review raised, both real, neither fatal:**

- `trap ... EXIT` doesn't fire on `SIGKILL` — a hard-killed `bin/test` (or one run via
  `run_in_background` and later force-stopped) leaks its tmpfs dir. Acceptable if bounded: 8G of
  tmpfs fills slowly from leaked runs, but this needs either a periodic reaper (e.g. delete
  `uedcli-test-*` dirs older than a day at the top of `bin/test`) or an accepted manual cleanup step
  — pick one before shipping this, don't leave it silently accumulating.
- **Scope this to the offline (`not integration`) run only.** `-m integration` tests drive the live
  editor container and bind-mount host paths into it; a `TMPDIR` under this environment's own tmpfs
  may not be the same path the Docker daemon sees, breaking any test that constructs a bind-mount
  from `tmp_path`. Don't extend the new `TMPDIR` scheme to `-m integration` runs without checking
  that separately — the default `bin/test` (`-m "not integration"`) is what this spec is about.

### 4. Gate the retail-map corpus tests behind an opt-in marker — DECIDED

Owner ruling (2026-09-12): gate it. Implemented — `@pytest.mark.slow` on
`test_retail_unreal_gold_maps_import_fully`, `addopts = -m "not integration and not slow"` in
`pytest.ini`. Saves 173s (11%) of every default `bin/test` run; the coverage still runs via
`pytest -m slow`. `dev/docs/rules/tests.md` describes "the offline suite" and should be updated to
say `-m slow` tests are excluded by default — that edit needs its own owner yes
(`dev/docs/rules/` is not agent-editable) and is NOT done as part of this item; flagged separately.

### 5. Reduce redundant class-schema resolution in `actor find --prop` / board-scan tests — original framing was wrong; real fix is bigger than a test tweak

**My first draft misdiagnosed this — corrected after review, verified against the code.** I claimed
the cost was the `_schema_cache_off` autouse fixture *clearing* `schema_cache`'s in-process memo
(`_DISC_MEMO`/`_PROP_MEMO`) every test. Reading `schema_cache.load_package_schema`
(`uedcli/schema_cache.py:319-324`) shows that's backwards: when the cache is disabled
(`UEDCLI_SCHEMA_CACHE=off`, which `_schema_cache_off` sets), the function returns *before* it ever
touches either memo dict. The `.clear()` calls in the fixture are no-ops under the fixture's own
setting — there is nothing to clear. The actual cost is simpler and worse: with the cache off, every
call fully re-decodes the package from bytes, every time, by design (that's what "off" means) — not
a caching bug, the literal documented behavior of the escape hatch.

So the real question isn't "stop clearing a memo" — it's "would it be safe for the offline suite to
run with the cache *on*". Two things stand in the way, one merely inconvenient and one that needs
actual verification:

- `_isolate_uedcli_home` repoints `$UEDCLI_HOME` (and so the on-disk persistent cache directory,
  `user_cache_home()` in `config.py`) at a fresh per-test `tmp_path`. Turning the cache on as-is
  would still get zero cross-test reuse from the *disk* cache — each test starts with an empty
  cache dir regardless. Only the in-process memo (keyed by the real source package path, independent
  of `$UEDCLI_HOME`) could actually warm up across tests in one `pytest` process.
- `_schema_cache_off`'s docstring says the cache is forced off suite-wide "so a stale dev-written
  entry must not poison unrelated tests while the `uprops`/`upackage` decoder is being refactored by
  a concurrent session" — but that concern is about the *persistent disk cache* format drifting
  under a live refactor, which the memo isn't exposed to (it's in-process, per-run, never touches
  disk unless the disk cache is also on). Whether that concern still applies to the memo specifically
  was never actually load-bearing for it — but I have not confirmed the referenced refactor's status
  either way (most recent related commit: `fef9a72c`, "Unify UE1 package-read primitives into one
  Rust core" — looks plausible as the refactor landing, not confirmed).

**This makes item 5 bigger than "a test-suite change": `schema_cache.py` currently has one `_enabled()`
switch gating both the disk cache and the in-process memo together. Getting a safe speed win here
needs a new mode — memo warm, disk cache still off — which is a change to production code, not test
fixtures.** That's real scope creep against the rest of this spec. Recommend splitting it into its
own board item rather than building it as part of this one; see the open question below.

## Open questions (owner)

1. ~~Gate the retail-map corpus test?~~ **Answered 2026-09-12: yes, gate it.** Implemented (item 4).
2. Item 5 needs a `schema_cache.py` change (a new memo-only mode), not a test-only tweak — worth
   doing as part of this effort, or split into its own board item? Owner raised a sharp follow-up:
   would warming the memo across tests invalidate any test that writes a package file and re-reads
   it expecting fresh content? Answer: the memo is keyed by realpath and would go stale exactly in
   that scenario — this needs a check (do any tests write then re-read a `.u`/`.utx` at the same
   path?) before item 5 is safe to build at all, regardless of where it lives. Still open, filed in
   `questions/`.

## Proposed order of work

1. `-n auto --dist=loadfile`, capped worker count (item 1) — biggest lever on the long tail; forces
   the empirical parallel-safety check this spec couldn't fully close by reading alone.
2. Unique tmpfs `TMPDIR`, scoped to the offline run, with a leak-cleanup plan (items 2+3) — fixes the
   correctness bug found while measuring; independent of item 1.
3. Item 4 waits on the owner's answer above.
4. Item 5 is descoped pending the owner's answer on whether it belongs in this item at all.

# Implementation plan — BSP-issue detector (near-term: the parser spike, D0 capture, the verb, D0-b)

**Status:** plan (ephemeral — sequencing scratch; folds into durable docs as steps land).
**Spec:** `specs/2026-06-24-uedcli-offline-bsp-engine-design.md` (§6 box). **Decision:** `decisions.md`
2026-06-24 12:40 UTC (D0+D1 the detector; D2 deferred). Reviewed: 2 rounds.

## Scope (and what's OUT)

**In scope, in this order (reordered per review — value gate first):**
1. **The P0-a/P0-b1 `UModel`-parser feasibility spike** — *first and alone*. It is the project's
   value gate: D1 (located issues) is the real value; D0 is "just" a tripwire. One session;
   decides whether the rest of the plan builds one tier or two.
2. **D0 capture + parser promotion** — promote the validated parser and capture the `BuildLog` as a
   **byproduct of the rebuild that already happens** (in `level apply`'s materialize), not a new
   editor run.
3. **The `level doctor --rebuilt` read-only verb** (the apply-free health check), shaped by step 1.
4. **D0-b** — the measurement.

**OUT (deferred design in the spec; do NOT build here):** D1-b's located analyses
(`report.analyze_built`); the binary `UModel` parser beyond step-1's *feasibility* probe; **every D2
module** (`fpoly`/`f32`/`csg`/`build`/`passes`/`portal`/`rebuild`). D1-b and D2 are their own plans,
gated on step 1 / an owner judgment call.

---

## Step 1 — P0-a/P0-b1 `UModel`-parser feasibility spike (FIRST, ALONE; the value gate)

Run this before committing effort to steps 2–3: its go/no-go decides whether D1 (`--built`) is real.

- **P0-a:** parse the built `Model` out of a saved built `.dx`. **Use a BUILT `.dx`** — one that was
  `MAP REBUILD`+`MAP SAVE`d so its `Surfs`/`Nodes`/`Leaves` arrays are populated (a tracked
  `Maps/*.dx` if it's a real built map; else save one from the editor first). A non-built `.dx` has
  empty arrays → a false no-go (R3-I4). **Disassemble
  `UModel::Serialize`** (Engine.dll, exported `?Serialize@UModel@@...`, RVA ~0x170e60) with the
  `pefile`/`capstone` harness + a `.dx` hexdump. **Note (R2): `FBspNode<<`/`FBspSurf<<` are NOT
  exported** — they're inlined into `UModel::Serialize`'s `TArray` element loops; read the array
  layouts out of that one function's body. **Go = parse `Surfs` (incl. `PolyFlags`) + `Vectors` +
  `Points` + the `Vert`/`iVertPool` array AND `Nodes` + `Leaves`.** Mind the version-61 wrinkle.
- **P0-b1 (together):** test whether a located T-junction is reconstructable from
  `Nodes[].iVertPool`→`Vert`→`Point`/`Vector`. **Expected negative for located-HoM** (optimizer
  linked it → gone, or left it unlinked → already a D0 T-points count). Confirm. **Invisible walls**
  (near-zero-area nodes) and **fall-through** (built floor surf with `PF_NotSolid/Semisolid/Portal`)
  need only P0-a — those are D1's viable rows.
- **Output:** `spikes/2026-06-24-…-d1-umodel-feasibility.md` (go/no-go, the layout if go, the viable
  rows) + a `decisions.md` entry. **Acceptance:** a recorded go/no-go + viable-row list. **Time box:
  1 session.**

## Step 2 — D0: promote the parser + the capture/severity/report helpers (offline, pure, safe)

Offline-only, zero editor, zero risk to shared code — the schema-stable foundation. **No
`materialize()` change here** (that's step 3's wiring).

- **Promote** `_scratch/bspspike/bsp_editorlog.py` → `uedcli/bsp/editorlog.py` (`__init__.py` too):
  `parse_build_log(text)->BuildLog`, `BuildLog` (frozen kw-only, counts only — no identity). Add:
  - **`flush_and_parse_since(driver, offset) -> BuildLog`** — the load-bearing flush discipline
    lifted from the spike (R2-C1): settle → `dismiss_blocking_dialog` → `OBJ LIST CLASS=Class`
    (force the 4 KB flush) → sleep → `read_log_since(offset)` → `parse_build_log`. (The spike's
    `capture_build_log` becomes `rebuild()` + this helper, so both share one flush path.)
  - **`build_log_severity(BuildLog) -> Severity | None`** (R2-I3; `Severity` from `doctor`): `ERROR`
    if `has_drops`; else `WARN` if `unlinked_tpoints or infinitesimal_nodes`; else `None`.
  - **`format_build_report(BuildLog) -> str`** rendering per-channel `[ERROR]/[WARN]` (mirrors
    `doctor.format_report`'s counts line for consistency).
  - **`assert_flushed(BuildLog)`** — the no-flush guard (R2-I3, R3): a clean `BuildLog` is
    indistinguishable from an under-flushed one, so if **BOTH** `final_nodes` and `leaves` are
    `None` (neither `Nodes:` nor `Portalized:` appeared) the log didn't flush → return an error
    value (caller exits non-zero); **never** treat it as "clean."
- **Tests** (offline golden, no editor): `uedcli/tests/test_bsp_editorlog.py` —
  `test_it_parses_every_drop_channel`, `test_it_ignores_clean_linked_6_of_6`,
  `test_it_severity_is_error_on_drops`, `test_it_flags_missing_nodes_and_portalized_as_unflushed`
  (assert the **OR**: neither line present). Fixtures from the snippets in
  `spikes/…-d0-editorlog.md`. Suite green (no previously-passing test regresses; don't pin a count).
- **Acceptance:** module + helpers land; offline tests pass; suite green; **no editor / shared-code
  touched.** **Commit.**

## Step 3 — `level doctor --rebuilt`: the apply-free rebuild-health check (the MVP)

**This is the guaranteed-value deliverable.** Named use case (R2-C2): check `main/`'s rebuild health
**without** a terminal `level apply` (which writes/swaps the map). It is **self-contained — it does
NOT modify the shared `materialize()`/`apply` path** (R3 blocker): capture happens by wrapping the
**injected `rebuild` callable**, not by changing `materialize() -> None` or its callers.

- **`level doctor --rebuilt`** — reuse `_level_preview`'s seam (`editor_lock` → `ensure_editor` →
  `_materialize(...)`) MINUS preview's `LIGHT APPLY`/`JUMPTO`/`rmode` tail. **Capture mechanism
  (R3):** `materialize()` takes `rebuild` as an *injected callable* and `rebuild()` is its last step;
  inject a wrapper — `off = driver.log_size(); driver.rebuild(); holder.log = flush_and_parse_since(
  driver, off)` — so the slice is the rebuild only (the `MAP NEW`+paste churn is before `off`,
  R2-C2) and `materialize()`'s signature stays `-> None`. Read the `BuildLog` from `holder`;
  `assert_flushed` → exit 2 if unflushed; else report via `format_build_report`; exit `1 if
  build_log_severity is ERROR else 0`. Guards like `_level_preview`: `EditorBusyError`→exit 2,
  `(TimeoutError, DriverError)`→exit 2. Editor discipline per `parallel-editors.md`.
- **Flag semantics (R2-I4/R3-I2):** `--rebuilt` supports `--json`; **rejects `--category`** (it
  validates against `doctor.CATEGORIES`, which D0 has none of) with a clear error; **`--severity` is
  NOT supported on `--rebuilt`** (a `BuildLog` has one overall severity, not a filterable
  `list[Finding]` — don't fake a filter target). State all this in `help=`.
- **`--built --dx <path>`** — added **only if step 1 is go**; wires the verb, routes to the
  **deferred D1-b** analysis (OUT of this plan). On no-go, not added. (`--dx` arbitrary-map
  load+rebuild has no seam; `_materialize` is session-`main/`-shaped — deferred regardless.)
- **Never let an exception reach the CLI**: dead editor / bad input → clean error naming the value,
  exit 2.
- **Tests:** dispatch tests modeled on **`test_materialize.py`** (mock the `Driver`/seam with
  `autospec=True`) — NOT `test_doctor.py` (which mocks nothing). Names `test_it_<verb>_<scenario>`;
  exit-code, reject-`--category`, and unflushed→exit-2 tests. Suite green.
- **Docs (arm-aware):** update `architecture.md` + `usage.md`; **repoint `doctor.py`'s stale
  `_FOOTER`/docstring** (drop "Phase 2"; fix the `09:07`→`12:40` ref + the stale "spec §7" ref). On
  a **no-go**, docs describe only `--rebuilt`; `--built`/`--deep` framed as deferred.
- **Acceptance:** `--rebuilt` runs end-to-end (and `--built` if go); the injected-rebuild capture +
  flag semantics + guards implemented; tests + suite green; docs current. **Commit.**

## Step 3b (OPTIONAL, smaller, AFTER step 3 is proven) — surface the BuildLog on `level apply`

A nice-to-have (rebuild-health on every apply, free), but it touches the **critical write path**, so
it's a separate, later, small commit — never bundled into the MVP, and **never by changing
`materialize()`'s return type** (R3). Mechanism: wrap the injected `rebuild` at `apply._materialize`
(same wrapper as step 3), add a `build_log` field to `ApplyResult`, and surface it in the apply
output. **Success-path only — a lagged/unflushed log on an otherwise-successful apply WARNS, it does
NOT abort the write** (the map built fine; only the log read lagged — R3-I1). Skip if step 4's
measurement is better served by `--rebuilt` alone.

## Step 4 — D0-b: the measurement (gates D1's value; informs the D2 judgment)

- Over **real semisolid/portal maps** (gitignored install content; one or two suffice). Run
  `level doctor --rebuilt` (step 3) on each — it already captures the `BuildLog` — and compare D0's
  drop counts to the static `doctor`'s predicted `degenerate`/`watertight` ERROR count. The
  **excess** = a fuzzy upper bound on build-emergent drops the static tier misses → tells us whether
  D1's located detection is worth building. **Does NOT gate D2** (silent-absence is unmeasurable
  offline; D2 is a judgment call — state it).
- **Content-blocked fallback:** if the install content is absent here, step 4 is a tracked TODO;
  steps 1–3 stand alone. Don't fake it.
- **Output:** a findings doc + a `decisions.md` note. **Acceptance:** measurement recorded, OR noted
  content-blocked with a TODO.

---

## Cross-cutting

- **Editor crash discipline:** every live step uses fresh ephemeral editors, teardown-in-`finally`,
  hard timeouts, GC-dialog dismissal, EDIT PASTE for brushes; never touch standing containers; a
  non-flushed log (no `Nodes:` line) is a hard failure, never a pass (step 2).
- **Dependencies:** **Step 1 first (the gate).** Steps 2 and 3 follow; step 3's `--built` arm exists
  only if step 1 is go. Step 4 needs step 2 + real-map content.
- **Citations:** cite `decisions.md` by UTC timestamp (durable), not ephemeral spec sections (R2-I2)
  — the spec folds into durable docs and is deleted.

## Done — near-term effort
**DONE =** step 1 go/no-go recorded (`spikes/`+`decisions.md`); step 2 landed (`bsp/editorlog.py` +
the materialize capture + no-flush hard-fail + tests, suite green); step 3 shipped per the spike
answer (`--rebuilt` always; `+--built` iff go; docs current, arm-aware); step 4 measurement recorded
OR content-blocked TODO. **Branches:** spike no-go → `--rebuilt` only, D1-b/`--built` deferred;
content absent → steps 1–3 still complete, step 4 a TODO. **D1-b proceeds only on a green spike, as
its own plan.** Each step commits independently with its tests.

# Spec — on-demand v68→v69 stubbing: finalize the remnants

## Goal

The stubbing pipeline shipped and was live-validated end-to-end (`DeusExItems`, 2026-06-22). This
spec closes out the three remnants so nothing is left half-wired: the unbuilt `--deps` flag, the
dropped cross-package asset flags, and — found during this spec — the **lazy auto-trigger is not
wired to any resolution site**, so the "automatic and lazy" stubbing `direction/containers.md`
promises does not happen.

## Current state

The pipeline (all in `uedcli/`):

- `stub_closure.py` — one-hop dep classification (ready-v69 / must-stub-v68 / content). Deliberately
  not transitive; a must-stub dep that itself needs an only-v68 dep raises `StubClosureError` (the
  "M1 boundary", `stub_closure.py:99-111`).
- `stub.py` — `build_stub` (container UCC/umodel legs) + `ensure_stub` (cache-keyed build,
  `stub.py:412`) + `stub_missing_packages` (the lazy auto-trigger core, `stub.py:322`).
- `cli/commands/substrate.py` — the explicit `substrate stub <pkg>` escape hatch (`--force`,
  `--list`). Its docstring says "the lazy auto-trigger is the resolution hook" (`substrate.py:13`).
- `packages.py:111` `unloadable_v68_packages` + `:128` `unstubbed_v68_message` — the current
  editor-load guard: called at `packages.py:261`, it **refuses** a level that references an unstubbed
  v68 `.u` with a named error telling the user to run `substrate stub` first.

Three remnants:

1. **`--deps` recursive-stub flag — never built, and rejected by direction.** No `--deps` exists in
   `cli/parsers/substrate.py`. The overview lists it as "remaining", but `direction/containers.md`
   Rejected explicitly kills "a deep transitive stub engine — over-built for a closure that bottoms
   out on the committed substrate one hop down", and `stub_closure` already surfaces the deep case as
   the M1 named error. **Resolved by direction: do not build `--deps`.** Record it and drop the
   remnant; no owner question.

2. **Cross-package asset refs are flagged then dropped.** `assemble_stub_source` collects
   `CrossPackageRef`s (`stub.py:99-113`, via `uscript_rewrite.flag_cross_package_refs`) into
   `AssembledStub.cross_package_refs`, "flagged (deferred), build proceeds" (`stub.py:73,89`). But
   **nothing consumes that field** — grep shows no reader. The build silently proceeds; a stub whose
   mesh/texture ref points into another package may render/behave wrong with no notice, which sits
   against the no-silent-halfanswer convention. See `questions/surface-cross-package-asset-refs.md`.

3. **The lazy auto-trigger is unwired (found while speccing).** `stub_missing_packages` has **no
   production caller** — grep finds only its definition, its own docstring, and `test_stub.py`.
   `apply.py`/`qualify.py`/`materialize.py` never call it. So today `level materialize`/`level
   preview` do not auto-stub: they hit `unloadable_v68_packages` and **refuse** with the "build the
   stub(s) first" message. That contradicts `direction/containers.md` "What we want": *"Stubbing is
   automatic and lazy, triggered at package resolution rather than by a verb the user must
   remember."* This is a direction-vs-architecture gap. See
   `questions/wire-lazy-auto-stub-or-keep-refuse.md`.

## Design

- **Remnant 1:** close it. Update the overview/board to note `--deps` is not-to-build per
  `direction/containers.md`; keep the M1 `StubClosureError`. Record the rationale in
  `dev/docs/rationale/` (agent-owned) rather than direction.

- **Remnant 2 (pending the question):** if surfacing is chosen, emit each `CrossPackageRef` (package,
  ref, where) to **stderr** at build time — matching the producer/stderr-for-human-summaries
  convention — while the built stub still goes to stdout / cache. Full cross-package resolution stays
  a separate future board item, not this one. `ensure_stub`/`build_stub` already thread the
  `AssembledStub`; the change is to log its `cross_package_refs` rather than discard them.

- **Remnant 3 (pending the question):** two coherent end states, and the owner picks:
  - **Wire the auto-trigger** — at the materialize/preview resolution pre-pass, feed the
    unstubbed-v68 set (`unloadable_v68_packages`, or the missing set) to `stub_missing_packages`
    before the refuse check, so a referenced v68 code package is stubbed on demand and the build
    proceeds. Delivers the promised "automatic and lazy" behavior. Cost: a materialize can now
    trigger a multi-second container build it didn't before.
  - **Keep refuse-and-tell and revise the direction doc** — the explicit `substrate stub` verb plus
    the named refusal is the intended UX; `direction/containers.md` "automatic and lazy" is then
    stale and must be revised (owner's yes required — a `direction/` edit).

  Recommendation: **wire it.** The refusal makes every first materialize of a level with a new v68
  dep a two-step chore, which is exactly what "no verb the user must remember" exists to avoid; the
  machinery is already built and tested, only the call site is missing.

## Edge cases & errors

- Auto-stub of a package whose closure hits the M1 boundary: the existing `StubClosureError` /
  `StubBuildError` must reach the user as a clean exit-2 message (the materialize/preview guards
  already convert `RuntimeError`/`ValueError`), never a bare traceback.
- A missing package with no v68 `.u` on the search path is a genuine absent asset, not a stub
  candidate (`_is_stub_candidate`, `stub.py:314`) — must stay a normal missing-asset error, not an
  attempted stub.
- Content packages (`.utx/.uax/.umx`) are never stubbed — the classifier already excludes them.

## Tests

- Remnant 2: a unit test that `build_stub`/`assemble_stub_source` over a fixture class with a
  cross-package ref emits the flag to stderr (offline — `assemble_stub_source` is pure).
- Remnant 3 (if wired): a test at the resolution seam that a level referencing an unstubbed v68 code
  package invokes `stub_missing_packages` (mocked build) and then proceeds rather than exiting 2;
  keep a test that a genuinely absent (non-code) package still refuses. The live end-to-end path
  stays integration-only (needs the container + gitignored install), as today.

## Open questions

- `questions/wire-lazy-auto-stub-or-keep-refuse.md` — the direction-vs-architecture gap (biggest).
- `questions/surface-cross-package-asset-refs.md` — warn vs stay silent on dropped cross-package refs.

# Spec — code-stripped LUM maps still block live materialize

## Goal

Let the code-stripped maps materialize (live editor build, `level materialize`) that currently can't:
the LUM mission maps and a handful of retail maps (`20_Lenz` + 5 cinematics). Base-content maps
already build (done 2026-06-20); these stay blocked because the editor cannot load the code their
actors reference, and uedcli's stubber deliberately does not cover it.

This item is **investigation-first**: the two blockers are independent, and neither has a
characterized reproduction in the tree yet. The spec's job is to split them cleanly, state what is
known, and route each to the right resolution — likely `to-spike/` before `to-plan/`. It also surfaces
two scope decisions that are the owner's, not an implementer's.

## Current state

Materialize refuses code it cannot load, loudly and early (this is correct today — the item is about
*extending coverage*, not fixing a silent failure):

- `packages.unloadable_v68_packages` / `unstubbed_v68_message` (`uedcli/packages.py:111,128`): a level
  referencing a v68 `.u` code package with no v69 stub is refused before any editor command — "build
  the stub(s) first". The v69 editor GPFs on a raw v68 `.u`.
- `stub.ensure_stub` / `build_stub` (`uedcli/stub.py:412,130`) build a v69 stub from the game's real
  v68 `.u` by decompiling it. A decompile/make failure raises `StubBuildError` — "a broken stub is
  never emitted" (`architecture.md` "Scope").
- `stub_closure.resolve` (`uedcli/stub_closure.py`) refuses deep recursion: a must-stub dep whose own
  deps include another only-v68 code package raises `StubClosureError` ("deep recursion is out of
  scope").
- `architecture.md` "Scope" (`:1948`) states outright: "First-party `LUM_Core.u` (compiled from repo
  source) and cinematics' stripped engine symbols are out of scope." That is exactly this item's
  target — the two out-of-scope cases, made in-scope.

## The two independent blockers

### Blocker A — first-party `LUM_Core.u` (the LUM mission maps)

LUM mission maps reference classes in `LUM_Core.u`, the mod's **own** code package. uedcli's stubber
decompiles a shipped v68 `.u` into a v69 stub; `LUM_Core.u` is different in kind:

- It is compiled from **repo source** (the LUM project's own UnrealScript), not a shipped binary to
  decompile. A stub of a compiled artifact may be available, but the honest source is the repo.
- So the fix is likely a **real UCC compile of `LUM_Core` from source into a v69-loadable package**
  (a build step, not a decompile-stub), or treating a compiled `LUM_Core.u` as a substrate/overlay
  package the editor loads directly.

Open design point: does uedcli grow a "compile this project's own code package" capability, or does it
consume a `LUM_Core.u` the project builds by its own toolchain and places on the search path? This is
a scope question (below), and it interacts with `direction/scope.md` (generic UE1 tool) and
`direction/containers.md` (uedcli drives a UCC build container already, for stubs).

### Blocker B — stripped engine/game symbols (`20_Lenz` + 5 retail cinematics)

These maps reference `Engine.CameraPoint` and `DeusEx.DeusExDecoration.BeginPlay` — symbols the
committed **code-stripped** DeusEx substrate does not carry in decompilable form. The stubber's
decompile fails loudly (the `PostRenderFlash` class of failure named in `architecture.md:1949`).

The fix is about **sourcing an un-stripped definition** of exactly these symbols so a stub can be
built (or a minimal hand-authored stub that satisfies the load without the real body). This is
narrower than Blocker A — a small fixed set of named symbols — but touches copyright/substrate
policy (`direction/containers.md`: the substrate is committed, stubs are derived-per-user and never
committed; an un-stripped engine symbol source has the same copyright shape as the game code stubs
are already built from).

## Design — sequencing, not implementation

Because neither blocker has a committed reproduction, the first deliverable is a **spike** that, for
each map class, drives `level materialize` and records the exact failure point (which `OBJ LOAD` /
which `StubBuildError`/`StubClosureError`), against the real install. That pins:

- For A: whether the maps need only `LUM_Core` or a deeper first-party closure; whether a compiled
  `LUM_Core.u` already exists in the LUM repo build output that could just be placed on the path.
- For B: the complete set of stripped symbols actually referenced (the item names two; the spike
  confirms it is only those), and whether a minimal stub can satisfy the editor load without the real
  behavior (materialize needs the class to *load and import*, not to *run* — a body-less stub of the
  right class shape may suffice, the same premise the existing stubber rests on).

Then split into two build items (A and B are independent — either can land without the other), each
planned from the spike findings. Do **not** try to design the fix in this spec ahead of the spike;
the failure specifics decide the shape.

Guard rails that must hold in any fix (from the direction docs, non-negotiable):
- Never emit a broken stub / never a silent load — keep the fail-loud contract (`packages.md`,
  `containers.md` "fails loudly").
- Never commit derived copyrighted code — a compiled `LUM_Core.u` or an un-stripped-symbol stub is
  per-user/derived, cached like the other stubs, never committed (`containers.md`).
- Model-side reads stay on the game's real packages, never a stub (`containers.md`).

## Edge cases & errors

Current behavior is already correct (fail-loud); the item extends coverage, so the edge cases are
about *not regressing* that:

| Case | Must stay |
|---------------------------------------|--------------------------------------------------|
| A map still referencing a symbol we cannot source | fail loud, named — never a broken stub or silent drop |
| `LUM_Core` compile fails | `StubBuildError`-class named failure, nothing emitted |
| A base-content map (already works) | unaffected — the new paths are additive |
| Deep first-party closure beyond scope | the existing `StubClosureError` refusal, named |

## Tests

- Spike harness committed to `dev/docs/spikes/<slug>/` (per `rules/spikes.md`), recording each map
  class's failure point as a checkable finding.
- Once a fix lands: an integration case per blocker that materializes one representative map end-to-end
  (LUM mission map for A; `20_Lenz` or a cinematic for B), gated behind the real-install marker the
  other integration tests use (`tests/conftest.py` install pointers).
- A regression that the fail-loud contract still holds for a genuinely unsourceable symbol.

## Open questions

- **Blocker A scope:** does uedcli compile a project's own code package (`LUM_Core`) from source, or
  consume one the project builds itself and places on the search path?
  `questions/lum-core-compile-scope.md`.
- **Blocker B scope:** are we willing/able to source un-stripped definitions of the specific engine/
  game symbols (`Engine.CameraPoint`, `DeusEx.DeusExDecoration.BeginPlay`), and under what
  copyright/substrate handling? `questions/stripped-symbol-sourcing.md`.
- **Should this go to `to-spike/` before planning?** Recommend yes — the failure specifics are not yet
  characterized in the tree. (Not an owner fork; noted for whoever triages the item next.)

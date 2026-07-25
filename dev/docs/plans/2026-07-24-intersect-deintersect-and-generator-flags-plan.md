# Plan — generator-flag cleanup + native `intersect`/`deintersect` (built together)

**Status:** PLAN. Ephemeral per-feature scratch. Sequences two coupled specs into one build.
**Date:** 2026-07-24.

**Specs (spec-review gate PASSED — two cold reviews each, findings resolved, commit `e436423ca`):**
- Part A: [`../specs/2026-07-24-generator-flag-cleanup.md`](../specs/2026-07-24-generator-flag-cleanup.md)
  (the prerequisite).
- Part B: [`../specs/2026-07-24-intersect-deintersect-native-brushset.md`](../specs/2026-07-24-intersect-deintersect-native-brushset.md)
  (depends on A's shared flags + emit locus).
- Ground truth: [`../spikes/2026-07-15-native-materialize/re-raw-zones/bspbrushcsg-intersect-deintersect-decode.md`](../spikes/2026-07-15-native-materialize/re-raw-zones/bspbrushcsg-intersect-deintersect-decode.md).
- Decisions: `decisions.md` 2026-07-24 16:32 / 17:04 / 17:56 / 18:12 / 18:33.

**Why together, A first.** B's verbs share `brush build`'s flag set AND emit their carriers through the same
`emit_actor_t3d` locus that A builds — so A must land first (or in the same branch, before B's verb code).
The shared seam is **`emit.emit_actor_t3d`** (generator stdout emitter): A adds carrier emission there; B's
verbs emit through it and inherit carriers for free.

---

## Part A — generator-flag cleanup (prerequisite)

**A1 — carrier emission at `emit_actor_t3d` (the shared seam).**
- Extract a **folder-carrier helper** (none exists; `query.py:310` hand-formats it) beside
  `labellib.format_labels_carrier`; use it in BOTH `query.actor_show_block` and the new emit.
- In `emit.emit_actor_t3d` (`emit.py:155`) emit `// uedctl-folder:` / `// uedctl-labels:` carriers **gated on
  the actor having `folder`/`labels` set**.
- **DO NOT** touch `emit.emit_actor` / `emit.emit_map` / `normalize.canonical_actor_t3d` — the latter writes
  the stored trunk body whose invariant is carrier-free (`model.py:38-43`, `t3dtree.py:126`); carriers there
  corrupt the store and double-emit in `actor show`.
- **Gate A1:** unit — `emit_actor_t3d` of an actor with folder/labels contains the carriers; `canonical_actor_t3d`
  of the same actor does NOT; `actor show` still emits exactly one carrier set (no double).

**A2 — `--folder`/`--label` on the generators.**
- Add repeatable `--folder <path>` / `--label <l>` to `_common_build_opts` (`cli.py:737`) and `actor build`
  (`cli.py:455`); set `actor.folder`/`actor.labels` on the constructed Actor (`make_brush_actor` gains the
  params; `actor build`'s Actor construction sets them). Emit is A1's `emit_actor_t3d`.
- **Gate A2:** `brush build cube --folder a.b --label x --label y | actor add -` → trunk actor has folder
  `a.b`, labels `{x,y}`; same for `actor build`.

**A3 — remove `--folder`/`--label` from `actor add`.**
- Drop the two args (`cli.py:478`); `actor add` keeps parsing incoming carriers and keeps `--order`.
- **Delete / convert to rejection tests** the override-precedence tests (`test_folders.py:294`,
  `test_labels_verbs.py:212`) — they test removed behavior. Remove dead `dispatch.py:3660`
  `labels_override`.
- **Gate A3:** argparse rejects `actor add --folder/--label`; `stash show | actor add -` still persists a
  carrier the T3D already had.

**A4 — ditch `--group` from `brush build`.**
- Remove `--group` from `_common_build_opts` → `--prop Group=`. Targeted migration of `build(... --group`
  ONLY (zero test usages; do NOT touch `actor find`/`stash apply`/`prefab apply --group`).
- **Gate A4:** argparse rejects `brush build --group`; `--prop Group=club` yields `Group=club`
  (byte-identical to the old `--group`, `emit_actor:131` `quote_group`).

**A5 — docs.** `usage.md` (flags moved), `architecture.md:379/382/386` + labels block (carrier mechanism +
`actor add` role), check `docs/leveldesign/`.

**Gate A (Part-A acceptance):** full offline suite (`bin/test`) green; `actor duplicate`/`apply` untouched
(exception holds).

---

## Part B — native `intersect`/`deintersect`

**B0 — regenerate goldens (the oracle).** Via the editor path (`_stash_*_impl`, `-m integration`), build
fresh goldens for cases (a)-(h) (§5) and commit under `tests/fixtures/`. (The `_scratch` experiment `.t3d`
are NOT fixtures.) Emit them with `--origin keep` (Location=0, world verts) for a direct compare, OR record
that the compare reduces both sides to world space.

**B1 — Rust: fill the `bspcsg.rs:1845` stub with the decoded tail.**
- Port the tail driver (decode §1) + the **four leaf callbacks** (`0x339e0`/`0x32390` phase-1,
  `0x33ab0`/`0x32460` phase-2, decode §2). Phase-1 filters builder faces ↓ world (append inside/outside);
  Phase-2 filters world faces ↓ the builder temp BSP and **appends to an OUTPUT polylist** (deintersect-P2
  `Reverse`s) — a NEW leaf reusing FWTB's straddle recursion, **no world-tree mutation / no rollback** (do
  NOT reuse the world-mutating `wtb_leaf`). Finalize = iLink surf-share renumber (decode §1).
- Expose `intersect_brushset(tuples, builder, deintersect) -> faces` via `lib.rs`. Stay at
  `root_outside=false`.
- **Gate B1:** `cargo test` — new unit tests over tiny fixtures (a solid box ∩ / − a box) produce the
  expected face set; the existing suite stays green.

**B2 — Python: the dispatch verbs.**
- Parse the T3D brush set from stdin (`-`); guards: ≥1 additive (intersect) / ≥1 subtractive (deintersect)
  else exit-2; non-brush/`Mover` → warn+skip; empty → exit 0. **Preserve stdin order** as CSG order (NO
  sort).
- Synthesize wrap-subtract + builder at the **editor-exact offsets** (`(cx−32,…)` / centered, both `bbox+64`;
  §4). Call `intersect_brushset`. Apply `--solidity` post-step. **Re-center** per §6b exact construction
  (`Location=P`, `PrePivot=P−anchor`, verts AND texture `Base` rebased by `−anchor`).
- Emit ONE actor via `emit_actor_t3d` (inherits A1 carriers), class `Engine.Brush` or `--mover-class`.
- Disjoint result → one actor + stderr component-count warning.
- **Gate B2:** native output vs B0 goldens, **world-position compare** (poly count, world verts, normal,
  texture, pan, PolyFlags) — cases (a)-(h) match.

**B3 — flags.** Wire the shared `brush build` flags with the **verb-specific defaults**: `--at` default
`None` (keep carved position), `--solidity` default faithful-per-face; plus `--origin` and `--pivot` (§6b).
`--mover-class` rejects `--csg`/`--solidity`; `--origin keep` rejects `--at`.
- **Gate B3:** flag matrix tests — `--solidity solid` (case d), `--mover-class` (g), `--pivot min` produces
  the §6b `Location`/`PrePivot` and the door swings about the hinge (re-center construction test), `--folder`/
  `--label` carriers ride through.

**B4 — retire the editor path from shipping.** Remove `stash intersect`/`stash deintersect` verbs +
`driver.brush_from_*` from the shipping surface; keep an `--editor`/test-only entry as the golden regenerator
(§5). Migrate `test_integration_stash_intersect.py`.
- **Gate B4:** `stash show s | brush intersect -` works; no `stash intersect` verb remains.

**B5 — docs.** `usage.md` (the two verbs, shared flags, `--origin`/`--pivot`, scale/disjoint caveats),
`docs/leveldesign/` door-mover workflow (`subtract doorway → deintersect --mover-class --pivot → add`).

**Gate B (Part-B acceptance):** native-vs-golden green (a)-(h); full `bin/test` + `cargo test` green; the
door-mover flow runs end-to-end (`… | brush deintersect - --mover-class Engine.Mover --pivot min --at … |
actor add -` → materialize → in-game/preview).

---

## Cross-cutting / risks

- **Scale:** v1 REJECTS scaled source brushes (inherited bspcsg-core gap); the port is a separate prioritized
  board item (`inbox.md`). Not in this plan.
- **Leading-additive `deintersect`** may hit the untested convex-seed path (`bspcsg.rs:1874`) — case (h) is
  the tripwire; if it diverges, seed with a subtract-first reorder (decide against the oracle in B2).
- **FP determinism** rides the already-characterized bspcsg core (SSE-scalar, bit-exact reachable); no new
  FP surface beyond the ported leaves.

## Review gate (after build, before done)

Run the **build review** at the headcount `CLAUDE.md` **Review gates** specifies (never a count restated
here — that is how this line went stale once already). Split the surface: the Rust tail/leaf port vs the
decode, and the Python verbs + flag matrix + the generator-flag migration. Resolve findings, then close out.

## Board

The two `to-plan.md` items (`intersect/deintersect`, `generator-flag cleanup`) advance to `to-build.md`
referencing this plan; Part A is the head of the build queue (B depends on it).

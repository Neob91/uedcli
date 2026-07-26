# Ready to build

The **on-deck queue**: plans that are reviewed and ready to execute *now*. Each entry links its
full plan in `../plans/` (ephemeral detail) — this file is the stable "build this next" index.

How this relates to the other board docs (see [`README.md`](README.md) for the full flow):
- The upstream queues — **[inbox.md](inbox.md)** (raw capture) → **[to-spec.md](to-spec.md)** →
  **[to-spike.md](to-spike.md)** → **[to-plan.md](to-plan.md)** — hold the broader, noisier backlog.
- **to-build.md** (this) — the short list of *reviewed, ready-to-go* work, pointing at the plan.
- **[inbox.md](inbox.md)** — the capture pool: ideas/gaps/bugs/chores + anything flagged for Andrzej.

When a plan here is built, delete its entry ([`done.md`](done.md) keeps a short recently-done tail).

---

## Per-surface texture verbs, STEP 1 of 5 (spec + plan reviewed, 2026-07-26)

- [ ] `p1` **Split `pan` out of `brush poly set`; add `brush poly rotate` and `brush poly scale --by`.**
  Plan: [`../plans/2026-07-26-poly-surface-step1-plan.md`](../plans/2026-07-26-poly-surface-step1-plan.md).
  Spec: [`../specs/2026-07-26-poly-surface-verbs.md`](../specs/2026-07-26-poly-surface-verbs.md)
  §2.0–§2.2, §2.5, §3.1 — **those sections only**.

  **Read the PLAN first; it is self-contained for this step.** It carries the re-anchor formulas
  (including the 2×2 Gram solve `scale` needs — the obvious implementation is wrong on a skewed
  frame and was caught only by review), the settled out-of-plane tolerance with its measurement, the
  `BRUSH:idx` stdout mechanism, the full list of tests that go red, and the docs to update by anchor
  text rather than line number.

  **Scope discipline: this step touches NO part of `brush poly align`.** The align half — the
  subcommand restructure, `wall`/`floor`'s world-space rewrite, `run`, `one-tile`,
  `--fit-perimeter`, the texture-catalog plumbing — is steps 2–5 and is NOT ready; those wait on
  `to-plan.md`. `polyalign.py` is not touched by this step at all.

  **Gate status:** spec gate passed (2 rounds); plan gate passed (2 rounds, both rounds' findings
  resolved). Four verbs, pure model-side, no editor and no catalog dependency.

  **Known residual, already logged:** `rotate`'s turn direction follows the *polygon* normal, so on a
  subtractive brush (a room interior — most of a map) it turns opposite to what the author sees. Kept
  deliberately rather than made solidity-dependent; see the plan §9.

## Native texture decode for any UE1 package (spec + plan self-contained, 2026-07-25)

- [ ] `p1` **Decode every UE1 texture layout natively; layout read off the DATA, not a format table.**
  Plan: [`../plans/2026-07-25-native-texture-formats-plan.md`](../plans/2026-07-25-native-texture-formats-plan.md).
  Spec: [`../specs/2026-07-25-native-texture-formats.md`](../specs/2026-07-25-native-texture-formats.md).

  **These two files are SELF-CONTAINED — read them and build. No other document needs opening.**
  They inline the binding decisions with their rejected alternatives, the on-disk `UTexture`/
  `FMipmap` byte layout, the house rules (test command, commit conventions, no-back-compat,
  no-silent-half-answers), every corpus path with its committed/not status, and every measured
  number with the root it was measured against. Provenance pointers are for the record only.

  **Why it matters here and now:** `utexture.py` decodes one layout (`fmt==0`), so a `UTexture`'s
  second mip array (`CompMips`) makes the body parse overrun — **30 textures in the project's own
  `LUM/Textures/LUM_CoreTex.utx` are invisible to uedcli today** and render as a checkerboard.
  This is a live bug on this substrate, not generic-UE1 hygiene.

  **STATUS 2026-07-26: BUILDABLE.** Both escalations from the plan reviews are resolved — the
  `repo_texture_root()` propagation (that directory left this repo when uedcli split out; the offline
  criterion is now a committed synthesized fixture and the live `LUM_CoreTex.utx` 30 → 0 count is
  integration-tier), and the decode oracle (spike
  [`../spikes/2026-07-26-ucc-texture-fixture/`](../spikes/2026-07-26-ucc-texture-fixture/findings.md)
  builds the fixture's P8 half with the game's own `ucc make` — byte-exact — and its DXT1 half with
  Pillow, so the cross-check stays independent with no copyrighted content). That spike also **refuted
  the plan's own ≤8/255 discrimination claim**: an index bit-offset bug scores 4.801 and PASSES, so
  S4 now carries a second byte-exact pin.

  **SCOPE WIDENED 2026-07-26 (owner ruling)** — a new slice `S2b` adds the two accessors
  `actor preview --faces textured` needs (a mip pyramid, and `bMasked` carried on S2's typed result — **not** a `texture_has_bMasked` predicate, which `conventions.md`'s predicate rule forbids), so the texture
  API changes once rather than twice. **The plan therefore re-enters the plan-review round
  before building.** See `../specs/2026-07-26-actor-preview-textured-faces.md` §12.

  **Nine slices:** `S1` CompMips + fixture builder → `S2` typed error results → `S3` layout
  detection → `S4` BC1 → `S5` BC2/BC3 → `S6` integration sweep + engine-fact pins → `S7` docs/board.

  **Gates** slice `S8a` of the asset-catalog plan below. Land it **before any texture is
  classified**: catalog shards are named `sha256(w,h,RGB)`, a frozen identity, so a later decode
  change silently re-keys and orphans them.

  **Two items were builder-decided under delegation ("do whatever it takes") and are reversible:**
  a data-vs-`Format` disagreement is a named `format-disagreement` error rather than a note
  (measured to fire on 0 of 18,176 exports today), and decode emits the mask the data carries
  without consulting `bMasked`/`bAlphaTexture` (which `Engine.Texture` defaults to `False`, so
  gating on them would silently switch block alpha off corpus-wide).

---

## Unified asset catalog — one engine, four kinds (NOT ON DECK — spec re-gating, 2026-07-26)

> **DO NOT START THIS.** It is **not** a reviewed on-deck item despite sitting on this queue. A
> 3-reviewer spec round on 2026-07-26 returned structural findings; the owner's rulings were folded and
> the spec re-entered the gate at round 1, which is where it is now. The plan is **stale and needs
> re-cutting** (it carries its own `RE-CUT REQUIRED` banner listing what no slice covers yet). Two
> `[OWNER — confirm]` items are still open on `inbox.md`. This item returns to on-deck only when the
> spec passes a round and the plan is re-cut and reviewed — `inbox.md` tracks it.

- [ ] `p2` **The unified asset catalog: texture / class / sound / music.** Plan:
  [`../plans/2026-07-25-unified-asset-catalog-plan.md`](../plans/2026-07-25-unified-asset-catalog-plan.md).
  Spec: SPLIT 2026-07-26 into [`engine`](../specs/2026-07-26-asset-catalog-engine.md) + [`class`](../specs/2026-07-26-asset-catalog-class-arm.md) + [`texture`](../specs/2026-07-26-asset-catalog-texture-arm.md) + [`audio`](../specs/2026-07-26-asset-catalog-audio-arm.md).
  Decisions: [`../direction/asset-catalog.md`](../direction/asset-catalog.md) (the owner's) and
  `../rationale/` (the agent's) — **not** `decisions.md`, which is FROZEN.

  **Governing principle:** the tool **lists, reports file facts, produces pictures, and stores the
  classification it is handed — it never infers meaning.** The LLM works out what an asset is and
  where it is used, and hands the answer back. The one deliberate exception is texture colours,
  pre-filled from that texture's own pixels and ordered by importance, so colour search works before
  any classification exists. *(This reframe, Andrzej 2026-07-25, deleted a tool-computed stock-map
  usage index, a class placement histogram, derived `placeable`, AND a whole build prerequisite.)*

  **Sequencing** (value-first; each slice a commit, `usage.md` updated in the same commit, no new
  test skips versus baseline):
  `P0` schema_cache v2 (raw default tags — gates S2 onward) → `S1` engine core →
  `S2` adapters → `S3` list/show (class, sound, music) → `S4` object-ref validation *(fixes a live
  bug that silently ships broken levels)* → `S5` classification store → `S6` search + ranking →
  `S7` class arm (mesh decoder → `uedcli/`, `class preview`, size facts) → `S8a` texture adapter
  (library-level) → `S8b` repoint the noun + delete the legacy subsystem → `S9` `.umx` title sniffer
  → `S10` lifecycle → `S11` doc sweep.

  **Blocking prerequisite NOT yet on the board:** `P1` **native non-P8 texture decoders** is still an
  untriaged `inbox` item (`[spike/implement] p2`) and **gates `S8a` only** — triage it through
  `to-spec`/`to-plan` before scheduling the texture slices. Everything else proceeds without it.

  **Two things the builder must NOT decide alone:** (1) `S7` measures whether the existing Rust
  rasterizer can render meshes — if it can, the ~300 ms/render figure underpinning decisions 7
  (never render in `list`/`search`) and 11 (single `iso` angle) is a Python artifact, and any change
  goes back to Andrzej as a **superseding `decisions.md` entry**, not a mid-slice judgement call;
  (2) the texture identity function `sha256(w,h,RGB)` is **frozen** and pinned by a committed golden
  in `S8a` — it is every tracked shard's filename, so any decode change silently re-keys and orphans
  authored classifications.

## Unattended build queue (curated 2026-07-18) — ✅ ALL 12 ITEMS DONE (see `done.md`)

The 2026-07-18 Andrzej-picked queue (bugs → small features → geometry → analysis → CLI audit) is
**fully drained**: builds #1-#5 shipped items 1-11, and the item-12 CLI consistency audit was
delivered as `../reviews/2026-07-19-cli-consistency-audit.md` (report-only). Its accepted-worthy
fixes are new `inbox.md` items awaiting Andrzej's triage. Entries live in `done.md`.

---

## 7. BSP-issue detector (D0 + the P0 spike + `level doctor --rebuilt` + D0-b)

**Status:** PARKED mid-spike (2026-06-25). Spec reviewed (6 rounds), plan reviewed (3 rounds).
**Plan (full detail):** [`../plans/2026-06-24-uedcli-bsp-detector-plan.md`](../plans/2026-06-24-uedcli-bsp-detector-plan.md)
**Spec:** [`../specs/2026-06-24-uedcli-offline-bsp-engine-design.md`](../specs/2026-06-24-uedcli-offline-bsp-engine-design.md) ·
**Decision:** `../decisions.md` 2026-06-24 12:40 UTC

**What it is.** Catch the *build-emergent* BSP problems (slivers, hall-of-mirrors, invisible walls,
fall-through) that the already-shipped static `level doctor` structurally can't.

**Build order (the near-term scope — D1-b and all D2 engine slices are OUT/deferred):**
1. **`UModel`-parser feasibility spike (first, alone)** — the value gate: decides whether the
   located-issue tier (`--built`) is even buildable. One session, on a *built* `.dx`.
2. **Promote D0** — the validated drop-warning parser → a new `uedcli/bsp/editorlog.py` + helpers +
   offline golden tests. (Offline, pure, touches no shared code.)
3. **`level doctor --rebuilt`** — the MVP: rebuild the level in an ephemeral editor, read the
   drop-warnings, report (a CI tripwire). Self-contained — wraps the injected `rebuild` callable, so
   it does **not** modify the shared `materialize()`/`level apply` path. `--built` added only if
   step 1 is go.
4. **D0-b measurement** — run over real maps to decide whether D1 is worth building (needs the
   gitignored install content; content-blocked → tracked TODO).

**Footprint (mostly additive):** a new `uedcli/bsp/` module + an opt-in `level doctor --rebuilt`
flag. The static `level doctor` and `level apply` are left as-is; `doctor.py` gets only a cosmetic
stale-string fix. The one change that would touch a load-bearing feature (surfacing build-health on
`level apply`, step 3b) is **deferred, optional, warn-only, and never alters `apply`/`materialize`
behavior**.

**Where the spike is parked:** See
[`../spikes/2026-06-25-umodel-serialize-format.md`](../spikes/2026-06-25-umodel-serialize-format.md)
for findings and next steps. The working harness is `_scratch/bspspike/umodel_parser.py`.
The parser handles everything up through the zone data. The next blocker is `_skip_array_0xa8`:
`0x1010c160` reads 3 × 4 raw bytes (not 1 ci) — fix is one line; downstream arrays may need
further verification.

**Done when:** step 1 go/no-go recorded; step 2 landed (suite green); step 3 shipped per the spike
answer (docs current); step 4 measurement recorded or content-blocked TODO. D1-b proceeds only on a
green spike, as its own plan.

---

---

## CLI usability-probe fixes (2026-07-19, `dev/docs/reviews/2026-07-19-cli-usability-probe.md`)

Mechanical fixes triaged from the usability probe (design-y ones went to `to-spec.md`). Small, self-contained; no plan needed.


---

## Promoted from F/H triage (2026-07-19)

Andrzej-approved ready items promoted from `inbox.md` into the build queue. Each is stage-less
(a chore/debug or a self-contained implement) or, for `usage.md`, a chosen DO-SOON doc rewrite.

---

## 8. `level import` — native (editor-less) `.dx`/`.unr` → T3D-tree ingestion

**Status:** Spec + plan written, **two cold-review rounds passed** (findings resolved inline).
**Plan (full detail):** [`../plans/2026-07-24-level-import.md`](../plans/2026-07-24-level-import.md)
**Spec:** [`../specs/2026-07-24-level-import.md`](../specs/2026-07-24-level-import.md) (v3) ·
**Decisions:** `../decisions.md` 2026-07-24 16:48 / 16:59 / 17:19 / 18:49 UTC

**What it is.** The inverse of `level materialize`: natively decode a compiled map file (no editor, no
UCC in the shipping path) into a queryable/diffable/remixable T3D trunk or stash. Decode REUSES the
production value decoder (`uprops.render_default_tag`); new code is `mapimport.py` + a StateFrame/FPoly
promotion + dynamic-array schema plumbing + the verb. UCC-fidelity lives at DECODE time (member-stripped
structs + 6dp floats), so the schema-free hash path is untouched; strict `qualify_and_validate` on
import.

**Build gate — Slice 0 DONE (2026-07-24), build unblocked.** The actor-ORDER spike resolved the
`Engine.Level` Actors layout (`[i32 Num][i32 Max]` + `Num` compact refs, `0`=null, `Actors[0]==LevelInfo`;
export-table order does NOT match, so decode the array). Verified on 3 retail maps; pinned by
`test_engine_facts.test_level_actors_array_is_int_num_max_then_compact_refs`; folded into spec §5.1.
Remaining slices: decode primitives (promote + pin) → UCC-exact render → `import_map` → verb/write path
→ goldens+integration → docs. Now buildable end-to-end.

---

## Promoted from the cheap-item board review (2026-07-24)

Andrzej triaged the ten-item cheap shortlist in chat; his calls are recorded in `../decisions.md`
2026-07-24 21:58 UTC. Three items changed shape rather than just queue (class-show, the ditched
stash-`CalledProcessError` item, and `--png`). Two items did NOT come here: the `ensure_editor`
`CalledProcessError` leak was **ditched** (native intersect/deintersect deletes that code path), and
nothing was sent to `to-spec.md`.

---

## 11. `docs` command — serve the user-facing docs from the CLI (self-documenting binary)

Add `uedcli docs list|show|search` serving `docs/` minus `dev/docs/**`, so a shipped Claude skill
routes to the docs by **querying the tool** — the skill/plugin ships zero doc copies. **The spec
doubles as the plan** (implementation-detailed; review gate passed 2026-07-24, two cold reviewers,
findings folded): `specs/2026-07-24-docs-command.md`. Key points baked in: `show` resolves via the
enumerated served-set (kills path-traversal + dev-tree leak structurally, no raw path-join); resolver
= `UEDCLI_DOCS_DIR` → source tree → packaged `uedcli/_docs` (**source-first** so a stale local build
can't shadow live dev docs); a `README.md` folds to its directory topic (root → `index`); errors reuse
`_SelectionExit` (clean exit 2, no new type). **Deferred, NOT this item:** the Nuitka/wheel `_docs`
generation + `.gitignore` + `--include-data-dir=uedcli/_docs=uedcli/_docs` + drift-CI — added only when
packaging exists, with no command-code change. **Docs to update on landing:** `docs/usage.md` gains a
`docs` section (the reference file the command serves); `architecture.md`. (Andrzej, 2026-07-24.)

---

## Docs restructure — `direction/` + `rationale/`, no ledger (spec + plan reviewed, 2026-07-26)

- [ ] `p1` **Retire the append-only decisions ledger; replace it and `direction.md` with two
  revised-in-place per-topic trees.** Plan:
  [`../plans/2026-07-26-docs-restructure-plan.md`](../plans/2026-07-26-docs-restructure-plan.md).
  Spec: [`../specs/2026-07-25-docs-restructure.md`](../specs/2026-07-25-docs-restructure.md).
  Five review rounds total — three on the spec (two of which returned structural findings and were
  resolved by Andrzej's rulings), two on the plan; all findings folded or logged to `inbox.md`.

  **The split is by WHO DECIDED, not by subject.** `direction/<topic>.md` holds what Andrzej
  decided — product intent *and* process rulings — and an agent may **never** write it without his
  explicit yes on the exact wording. `rationale/<topic>.md` holds what an agent decided (a
  tolerance, a scope limit, a format choice), keyed by module, and agents maintain it freely. Both
  are revised in place: no supersession, no dated history, git keeps the past. Every entry in both
  trees carries `Rejected` (so nobody re-proposes a killed design) and `Refs`.

  **This has no `decisions.md` entry, deliberately** — it is the change that abolishes that file.
  Its own rulings land in `direction/process.md` at Task 4, before anything is deleted.

  **Scale:** 227 ledger entries dispositioned, ~173 files' citations retargeted, 13 topic docs each
  gated on a separate confirmation from Andrzej, `CLAUDE.md` 671 → ~644, resident context 1,063 →
  ~653. Ten tasks, a gate after each of 3–10.

  **Three things a builder must not get wrong.** (1) The `@` import swap happens at the **end of
  Task 6**, not in Part A — swapping early leaves every session without the compiled target for the
  whole 13-confirmation stretch. (2) **Task 3 writes the link checker**; there is none in the repo,
  so until it exists every "verify" in the plan is prose. (3) The inventory numbers are
  measurements-at-a-sha and have already drifted once (citers 171→173, 45→46) — **Task 2 re-measures
  and its numbers govern.**

  **Blocked on:** `profile-generator-fixes` (6 unmerged commits touching five `uedcli/*.py` files
  and `inbox.md`, all in Task 8's scope) merging first, or those files being treated as manual-merge
  points.

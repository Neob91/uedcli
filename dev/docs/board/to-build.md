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

## `actor preview --faces {wire,flat,textured}` (spec + plan reviewed, 2026-07-27)

- [ ] `p1` **Solid and textured brush faces in `actor preview`.**
  Plan: [`../plans/2026-07-27-actor-preview-faces-plan.md`](../plans/2026-07-27-actor-preview-faces-plan.md).
  Spec: [`../specs/2026-07-26-actor-preview-textured-faces.md`](../specs/2026-07-26-actor-preview-textured-faces.md).

  **Read the PLAN first; it and the spec are self-contained.** The plan carries the slicing, the file
  map, the Done-whens and the two mechanisms that are cheap to re-break; the spec carries the owner's
  decisions with their rejected alternatives.

  **Why it matters.** `actor preview` is a wireframe schematic today. **Every** texture-frame defect
  in `../spikes/levelbuild-friction/agent-reports.md` — mirrored lettering, the half-shifted sheet,
  the wrapped door trim, a cut-out texture on a solid face — was invisible in it and cost a full
  materialize + render cycle to find. `flat` also makes a subtracted room show its interior instead
  of the outside of a box.

  **BUILD ORDER — this builds SECOND.** Slice `S4` consumes the mip-pyramid accessor and the
  `bMasked` flag that **Native texture decode**'s slice `S2b` delivers. Owner decision 2.11 orders
  the whole feature after that item; the plan implements that as ruled. *(Only S4 has a technical
  dependency — S1–S3 touch no texture code. That observation is parked on `inbox.md` as the owner's
  call, not the builder's.)*

  **Five slices:** `S1` `texframe.py` extraction (pure refactor) → `S2` the seam + `--faces` +
  `flat` complete → `S3` `--focus` over filled modes → `S4` `textured` → `S5` docs, rationale, board,
  spec deletion.

  **Gate status:** spec gate passed (multiple rounds, no structural finding in any); plan gate passed
  (2 rounds, both rounds' findings resolved and each fix verified by grep rather than declared).

  **Two things a builder must not get wrong**, both found by review rather than by writing: the
  mirror predicate needs a `None` guard, because `rotation.actor_linear` returns `None` for identity;
  and `getattr(args, "brush_colors", "csg")` does **not** fire for an existing-but-`None` attribute,
  so `default=None` needs an explicit `or "csg"` at each of three call sites — and no picture test
  can catch its absence, which is why the plan asserts it at the seam.

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

## Promoted from the cheap-item board review (2026-07-24)

Andrzej triaged the ten-item cheap shortlist in chat; his calls are recorded in `../decisions.md`
2026-07-24 21:58 UTC. Three items changed shape rather than just queue (class-show, the ditched
stash-`CalledProcessError` item, and `--png`). Two items did NOT come here: the `ensure_editor`
`CalledProcessError` leak was **ditched** (native intersect/deintersect deletes that code path), and
nothing was sent to `to-spec.md`.

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

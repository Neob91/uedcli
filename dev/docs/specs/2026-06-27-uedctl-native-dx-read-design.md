# Native `.dx` read & qualification — replace `export_and_qualify` (design)

**Ephemeral spec.** Phase A (items 3+4) of the de-containerization roadmap. Q0-INDEPENDENT
(read side). **Revised after two cold reviews** that corrected two real errors: (1) H3
verify does NOT route through `export_and_qualify` (it has its own live-qualify path), and
(2) per-poly **texture** qualification is NOT intrinsic to the import table — only **class**
qualification is. Grounded in spikes 3/4/7/8. Written for a reader with no prior context.

## Problem (the seam being removed)

`qualify.export_and_qualify(dx_path, container, session_id)` reads a `.dx` into the `Level`
model (used by `session start <dx>` and `level apply` THEIRS). Two container/editor legs:
1. **Offline UCC** — `UCC.exe batchexport <dx> Level T3D` → parse T3D → `Level` with **bare**
   texture + class names.
2. **Live editor** — fresh per-session editor, `MAP LOAD`, then `OBJ DEPENDENCIES` (per-poly
   texture *packages*, matched **positionally** to poly index by `qualify_level_textures`) +
   `OBJ LIST CLASS=Class` (bare→package, `qualify_level_classes`).

So a `.dx` read needs Docker + wine + UCC + a crash-prone editor + the GC-dialog/log-flush
dances. **H3 post-verify is a SEPARATE seam** (`verify.verify_dx_matches(qualify_driver=ed)`
→ `export_dx_level` + `qualify_live_level` + `qualify_level_classes` + `_read_loaded_classes`)
that reuses the editor that just materialized+saved (no `MAP LOAD`); see "H3" below — it is
NOT `export_and_qualify` and must be handled on its own.

## What is intrinsic to a native read — and what is NOT

The binary `.dx` stores object refs as indices into its import table (qualified
`Package.Class.Name`). But the import table is a **flat set** of refs, not a poly→object map.
So:
- **Class qualification IS intrinsic & proven.** Each actor export's class ref resolves
  through the import table to `Package.Class`, per-record, no positional matching, no
  collisions (Spike 8: 1837 actors of `00_Intro.dx`, classes resolved, 0 errors; Spike 4:
  112 classes, 0 collisions). This strictly dominates the live `OBJ LIST CLASS` +
  `qualify_level_classes` path and preserves the WHY of the 2026-06-21 decision (no reliable
  per-actor live read-back; collisions must error not guess) — here there's no ambiguity at all.
- **Per-poly TEXTURE qualification is in the `FPoly`, not the flat import set** (review
  correction) — and the `FPoly` is **now decoded** (Spike 10): each `FPoly.Texture` is an
  object ref that qualifies via the import table. So per-poly texture qualification IS
  natively recoverable, via the `UPolys`/`FPoly` decode (NOT via the built `Model` surfs that
  Spike 9 used — that indirection is rejected). See "the prerequisite" below.

## The prerequisite (NOW DECODED — Spike 10): `UPolys`/`FPoly`

Brush actors are the majority of a real level (920/1837 on `00_Intro`), and their authored
geometry + per-poly textures live in the brush's `Brush=Model'…'` → `UModel.Polys`
(a `UPolys` = array of `FPoly`: verts + texture object-ref + `Base`/`Normal`/`TextureU`/`V`
+ flags + `Pan` + `ItemName`). **This is now DECODED** (`spikes/…/10-native-upolys-fpoly.md`):
`UPolys` = `None` + INT Num + INT Max + Num×FPoly; `FPoly` = `ci NumVertices` + 4 FVectors +
NumVertices FVectors + INT PolyFlags + ci Actor + **ci Texture** + ci ItemName + ci iLink +
ci iBrushPoly + u16 PanU + u16 PanV. Validated to EOF on **6566/6587 (99%)** real `UPolys`
across 8 maps (4 maps 100%). `FPoly.Texture` is an object ref → **qualifies via the import
table** — so per-poly texture qualification IS recoverable natively (this resolves the
review's "texture not intrinsic" point: it's intrinsic to the `FPoly`, which we now read).
- Residual ~1% (21/6587) don't hit EOF exactly — a minor `FPoly` edge variant to chase
  before production (the EOF check pins which exports diverge); 4 whole maps are clean.
- Rejected (heavier, indirect): reconstruct authored polys from the **built** `Model` surfs
  via `FBspSurf.iActor`/`iBrushPoly` — the built model is a CSG product (Deus Ex loads
  pre-built BSP), so authored verts/pan/U-V/texture would be lossily re-derived from the
  build rather than read. Read the authored `UPolys` directly.

## Texture edge cases the positional path handles (native must too)
- **myLevel / local-export textures.** A poly's texture can be a **local export** of the
  `.dx` (an embedded `myLevel` texture), not an import — the import-table walk cannot qualify
  it. Resolve a non-negative (export) ref against the `.dx`'s own export table and emit the
  canonical self-ref form (the same `MyLevel.Name` shape `canonicalize_self_refs` expects).
- **Null / `Engine.DefaultTexture` polys.** Today `OBJ DEPENDENCIES` lines a poly *only* if
  its texture is non-null, so untextured polys stay `Polygon.texture=None` and can't collide.
  A native `FPoly` carries a texture index even for the null/default case — the reader MUST
  map a null/default index to the SAME `None` / `Engine.DefaultTexture` the current path
  yields, or `canonical_level_hash` parity (below) fails.

## Change

`uedctl/dxread.py` parses a `.dx` → fully-qualified `Level`: point actors (`StateFrame` +
props, Spike 7; class via import table), brush actors (props + authored `UPolys`/`FPoly`
geometry with per-poly texture refs qualified via import/export table), assembled as the
model expects (actors keyed by `Name`, `order`, `packages` from the import-table package
set), **fed through the SAME `normalize`/`canonical_actor_t3d` pipeline** so canonical forms
match. `export_and_qualify` becomes: temp-copy the `.dx` → `dxread` → qualified `Level`;
`container`/`session_id` params drop.

### Authored side (build-from-scratch / T3D) — manifest index
No source `.dx` ⇒ no import table; qualify bare names via the manifest `name→{packages}`
index (Spike 4 Case B). **Collision tie-break (pinned, since the hash depends on it):** prefer
the package earliest in the level's `packages` manifest order; if still ambiguous, ERROR
naming all candidates (the editor's contract). Reading a `.dx` never needs this search.

## H3 verify — its own seam (do NOT delete its live legs blindly)

`verify.verify_dx_matches` reads the editor-written `.dx` via `export_dx_level` and qualifies
BOTH sides with `qualify_live_level`/`qualify_level_classes`/`_read_loaded_classes` against the
**same live editor that just saved it** (D-Q3, no `MAP LOAD`, no second container). Options:
- **(preferred) swap H3's reader to native `dxread`** of the editor-written `.dx` — removes
  H3's live-qualify too, fully offline. Asymmetry to verify: `dxread` must faithfully read an
  **editor-produced** `.dx` (rebuilt BSP, editor-derived texture vectors, computed `Link`,
  any `myLevel` exports `MAP SAVE` created), not just retail input maps — so the parity corpus
  MUST include a `MAP SAVE`-output `.dx`, not only retail inputs.
- (fallback) keep the live-qualify functions for H3 only — then the "delete the live legs"
  claim is scoped to `export_and_qualify`, not H3. State which path is taken.
Either way, the deletion list is NOT "all of qualify.py's live legs" until H3 is converted.

## Validation, sequencing, backward-compat (lessons from prior reviews)
- **Acceptance gate = `canonical_level_hash` parity** over a corpus (integration-gated): native
  `dxread` of a `.dx` must hash-equal today's `export_and_qualify` of the same `.dx`, AND a
  `MAP SAVE`-output `.dx` for the H3 case. **Highest-risk axis: coordinate / texture-vector
  float formatting** — the old path parses UCC's ASCII (`-00479.999969`); native reads raw
  float32 and must format byte-identically through `clean`/6-dp. Assert **per-field**, not just
  whole-hash, so a divergence is diagnosable. `Link` (never emitted) and self-ref
  canonicalization (`<stem>.X`→`MyLevel.X`) must match via the shared `normalize` pass.
- **Sequencing (the live path is the oracle):** land `dxread` + parity tests **against the
  still-present live legs**, bless on the corpus, **then** delete the live legs in a follow-up
  commit. The acceptance test needs the live oracle to exist.
- **Backward-compat:** already-recorded sessions are SAFE — `base/`/`main/` blobs are stored
  canonical T3D, read by `read_state_dir`/`read_state_tree` and re-hashed by
  `integrity.verify_store` from those blobs; none touch the swapped reader. Risk is only on
  NEW ingests + `apply` THEIRS re-reads of an on-disk map.
- **Mover canonicalization:** the native reader applies `canonicalize_movers_in_level` where
  `export_and_qualify` does; the OTHER funnel `session.read_state_dir` (T3D-tree seed/apply)
  has its own mover hook and is untouched (it reads stored blobs, not a `.dx`).
  > **STALE (2026-07-25):** none of this describes the code any more. `canonicalize_movers_in_level`
  > was DELETED as a zero-caller helper, `qualify.export_and_qualify` never canonicalized movers at
  > all, and the session store is gone. The fold now runs at exactly one funnel — capture
  > (`dispatch._capture_from_t3d` → `movers.canonicalize_mover` per actor). See `architecture.md`
  > "Ingest canonicalization". *(This spec is ephemeral scratch per `CLAUDE.md`; the note is here
  > because the paragraph reads as shipped behaviour.)*
- **Error contract:** a `dxread` parse failure (truncated/unknown tag/EOF mismatch) raises a
  clear named error; `session start <dx>`/`apply` turn it into a clean CLI error + non-zero,
  never a traceback (uedctl house rule). `dxread` never returns a partial `Level`.

## What this removes / stays
- **Removes (after the oracle-blessed cutover):** `UCC batchexport Level T3D`
  (`store_export.export_dx_t3d`), the per-session editor for reads, `OBJ DEPENDENCIES`/
  `OBJ LIST` + their GC/flush handling, and (if H3 is converted) the live-qualify functions.
- **Stays:** the editor on the WRITE/materialize side (D2-gated) + optional final-bake.

## Doc updates on landing
`architecture.md` (`export_and_qualify` bullet, session start, materialize THEIRS, AND the
"Mover support" funnel note), `direction.md` (reconcile the superseded positional/OBJ-LIST
approach per the doc-upkeep rule), `unrealed/commands.md` + `t3d.md`/`quirks.md` (`OBJ
DEPENDENCIES`/`OBJ LIST` stay as editor facts; note uedctl reads natively), `decisions.md`
(new entry: native read replaces `export_and_qualify`, superseding the 2026-06-21 positional
concern; consistent with 2026-06-26 "parse the real `.u`, never the stub"), and promote the
`UPolys`/`FPoly` format into a durable topic doc once decoded.

## Refs
spikes `04-native-qualification.md` (import-table class qualification + manifest index),
`07-native-actor-bodies.md`, `08-native-dx-read.md`, `03-native-package-write.md`;
`uedctl/qualify.py` + `uedctl/verify.py` (the legs removed/converted), `uedctl/store_export.py`,
`uedctl/normalize.py` (`canonical_level_hash`, `canonicalize_self_refs`), `architecture.md`
(`export_and_qualify` funnel, mover/class canonicalization); `decisions.md` 2026-06-21
(class-qualification-via-OBJ-LIST, now superseded for the read path).

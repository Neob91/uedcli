# uedctl de-containerization — roadmap & target architecture (design)

**Ephemeral spec.** Synthesizes the 2026-06-27 spike series
(`dev/docs/spikes/2026-06-27-decontainerize-uedctl/`) into a sequenced plan to remove
uedctl's Docker/wine/`.exe` dependency stack. Decisions land in `decisions.md`; durable
mechanism in `architecture.md` as pieces ship. Written for a reader with no prior
context.

> **Reconciled 2026-06-28 — the geometry gate's load-bearing premise is now confirmed
> game-side.** This spec (2026-06-27) flagged "the game loads pre-built BSP and never
> rebuilds" as the **required early gate**, "not yet probed game-side." The
> `2026-06-26-deusex-game-playtest-driver` spike then loaded real `.dx` maps in the retail
> game and proved it (🔬 2026-06-28): a 0-BSP-node solid world crashes at
> `MatchViewportsToActors` → "Failed to spawn player actor"; the same map with a built BSP
> (68 nodes) spawns the player AND walks collision-bound — so the game uses the pre-built
> BSP for **both** render and collision and never re-runs CSG. A v69 UED22-authored `.dx`
> loads in the v68 game (version is a red herring, `unrealed/package-format.md`). **That one
> sub-fact — a `Model` written *natively by uedctl* (not by the editor's `EDIT PASTE`) loads
> in the game — is now ALSO PROVEN (🔬 2026-06-29, `spikes/2026-06-28-native-model-game-load/`):**
> a `.dx` whose level `Model` body was re-serialized from structure by `umodel_serialize` AND
> a separately NATIVELY-MODIFIED Model (a rigid BSP translation — geometry no editor wrote)
> both load and spawn + possess the player on a fully functional level; a native 0-node Model
> reproduces the `Failed to spawn player actor` crash (discrimination proven). So every
> serialization / container / load-acceptance risk in front of D2 is retired game-side; the
> SOLE remaining geometry unknown is D2's array *generation* from authored brushes. The inline
> caveats below (Phase B "Open risk", "Irreducible minimum", Q0) are updated to match. See
> `decisions.md` 2026-06-28 and 2026-06-29.

## Goal

Stop needing Docker/containers in uedctl by replacing every editor/`UCC`/`umodel`/
ImageMagick operation with native pure-Python code. Driving directive (Andrzej,
2026-06-27): "stop needing Docker overall"; "reverse-engineer texture + mesh extraction
to minimize `.exe` dependency"; and the hypothesis (now confirmed) that stubs exist for
mesh-format + `Engine.u`/`Core.u` divergence, **not** package version v68-vs-v69.

## What the spikes proved (feasibility is established, not assumed)

| # | Result | Evidence |
|---|---|---|
| 1 | **Native texture decode** pixel-EXACT vs `UCC batchexport`, whole install (v61/68/69), 100% P8 | `01-native-texture-decode.md` + `harness/utexture_decode.py` |
| 2 | **DeusEx mesh format confirmed different**: `FMeshVert` = 8-byte int16 (vs Unreal 4-byte packed); 178/178 meshes | `02-native-mesh-format.md` + `umesh_probe.py` |
| 3 | **Native package write** byte-identical on real `.dx` maps (4.7 MB) + `DeusEx.u`/`Engine.u` | `03-native-package-write.md` + `package_rw.py` |
| 4 | **Native qualification**: `.dx` import table = free qualification; manifest index for authored (1.8% global collisions) | `04-native-qualification.md` + `qualify_native.py` |
| 5 | **Lighting/paths** are post-BSP build output; native lighting is the 2nd long pole | `05-lighting-and-paths.md` |
| 6 | **Native write eliminates the entire stub pipeline** + UCC `make`/`batchexport class` + umodel | `06-stub-elimination.md` |

**Net:** `UCC.exe`, `umodel.exe`, ImageMagick are eliminable now; `unrealed.exe` reduces
to an optional final-bake (lighting+paths) until those are native. **The dominant
engineering project is the offline BSP/CSG `Model` *build* (D2) — a single long pole.**
(The `Model` serial format, once feared a coupled second port, is now decoded + validated
byte-exact on 12/12 real maps, so reading/writing the built model is mechanical — see the
honesty section.) Everything else (texture, qualify, container write, actor bodies, stub
deletion) is proven or low-risk.

### Honesty: what is proven vs asserted (post-review correction)

Two cold reviews flagged real overstatements; corrected here and in the spikes:

- **Container write is proven; body *synthesis* is not.** `package_rw.write_full`
  reproduces a real `.dx` **byte-identical** by copying the object-data region verbatim
  and reusing the original GUID/generations — this proves the header/table/offset
  encoders, NOT the synthesis of any object body, GUID, or generation. A from-scratch
  writer that emits *new, differently-sized* bodies and back-patches offsets is untested.
- **`Model` (de)serialization: both READ and WRITE are now built and validated
  byte-exact** (updated 2026-06-28) — read parses the level `Model` byte-exact to EOF on
  **12/12 real maps** (`2026-06-25-umodel-serialize-format.md`); the **WRITE is no longer
  merely "mechanical" by assertion — it is built and measured byte-exact**: a native
  serializer re-emits the `Model` body from its parsed structure identically to the
  original on **72419/72419 `Model` exports across all 82 v68 retail install maps** (the
  serializer is version-agnostic on the shared 68/69 code path — `unrealed/package-format.md`)
  (`2026-06-28-umodel-serialize-byte-exact.md`). Geometry arrays
  (Vectors/Points/Nodes/Surfs/Verts/Zones/Leaves) are re-encoded from structure; the
  lightmap/aux arrays splice through as raw spans (none carries an internal absolute
  offset). **This shrinks the long pole to D2 alone — the CSG/BSP *build* that GENERATES
  the Model — not its (de)serialization, which is now PROVEN, not just asserted.** Two
  caveats surfaced: a second UPrimitive-prefix length (42 vs 57 bytes; the serializer
  auto-detects, the read parser's fixed-42 mis-reads 243 models — a flagged parser
  follow-up); and the `FBspVert.iVertex`-larger-than-`Points` pool (an interpretation
  detail for the issue-detector, not for I/O).
- **Texture pixel-exactness IS reproducible** — the comparison harness
  (`harness/tex_compare.py`) is now committed (was out-of-band); re-verified 175/175 +
  17/17 EXACT vs UCC PCX.
- **Actor-body writing is now characterized + validated (Spike 7).** Body = optional
  `StateFrame` (when `RF_HasStack`) + tagged property list + class trailing; the reader
  parses 3736/3736 real `.dx` objects with 0 errors and the property writer round-trips
  all common types. Remaining: the empty-`StateFrame`-vs-populated question and the
  brush-actor `Engine.Model` shape body.
- **Corpus pinning:** all spike numbers are against the RETAIL install
  (`uned/DeusExAssets/{System,Textures}`, v61/v68), NOT `uned/UED22/` (v69 stubs, which
  give contradictory counts). Harnesses/docs now name the path+version beside each figure.

## Target architecture (native pipeline)

```
authored level (session store, model-side — already native today)
  │
  ├─ read THEIRS / session-start: parse .dx natively (dxpkg + export reader)   [S3/S4 read]
  │     → import table gives qualified textures/classes for free               [S4]
  ├─ textures: native UTexture/UPalette decode → catalog/PNG                    [S1]
  ├─ (optional) meshes: native LodMesh decode → mesh catalog / preview          [S2]
  │
  ├─ MATERIALIZE (native):
  │     CSG/BSP build  ───────────────────────────────────────────────  D2 (the long pole)
  │     → built Model (nodes/surfs/verts/zones/leaves)
  │     serialize package: header+names+imports+exports + actor bodies + Model  [S3]
  │     → a real .dx, no editor
  │
  ├─ lighting + paths:  baseline (iterate) | OPTIONAL editor bake (ship) | native (goal)  [S5]
  └─ preview: native wireframe (today) / native textured renderer (later)
```
No Docker in the authoring loop. Stubbing deleted entirely (S6).

## Roadmap (sequenced; each item is its own spec/plan/build)

**Phase A — native reads (low risk, high immediate payoff; mostly proven):**
1. Promote `utexture_decode` → a `utexture.py` module; rewire `texture sync` to native
   decode (drop `texture.py`'s `docker exec UCC batchexport` + PCX + Pillow-PCX). Keep
   the catalog/hash/color layer. *Removes the texture container seam.*
2. Promote the export-table reader (`load_package`) into `dxpkg` (or a sibling) as the
   shared native package model; fold in the `2026-06-26-uproperty-typed-decode` work.
3. Native qualification: replace `qualify.dump_obj_dependencies` (read path → import
   table) and `qualify_level_classes` (authored → manifest index, with a deterministic
   load-order collision policy). *Removes the fresh-editor + `OBJ DEPENDENCIES` leg.*
4. Native `.dx`→model read replacing `store_export.export_dx_t3d`'s `UCC batchexport
   Level T3D` (parse the package's actors/Model natively).

**Phase B — native write container (low risk, proven):**
5. `package_writer.py`: from-scratch package serializer (header/tables/offsets — proven
   byte-exact) + GUID/generation synthesis + a `FPropertyTag` writer for actor bodies
   (inverse of the S1 reader) + the `ULevel` body (its ordered actor array, `Model` ref,
   `URL`, etc.). Acceptance: write a small level and load it. **Open risk — RESOLVED
   2026-06-28: the GAME does not accept a `Level` with a null/empty `Model`.** A 0-node
   solid world loads in the editor (wireframe) but crashes the retail game at player spawn
   (the same `Failed to spawn player actor` proof). So Phase B's writer **can** be validated
   standalone in the **editor** (container/tables/bodies all exercised), but a **game**-level
   acceptance needs a minimal hand-built BSP — confirmed (not suspected) to pull a D2 slice
   forward. Validate the container/bodies in the editor; gate game-acceptance on the
   minimal-`Model` spike (Q0).

**Phase C — the long pole (high effort). NOTE: this *promotes* D2 from optional to
required — a real decision for Andrzej, not a given (see Q0).**
The offline BSP/CSG engine is already designed in
`specs/2026-06-24-uedctl-offline-bsp-engine-design.md` ("D2"), but `decisions.md`
2026-06-24 12:40 **deliberately deferred D2 as an optional, measurement-gated upgrade**
— the *planned* BSP ground-truth path is **D0 (editor drop-warnings) + D1 (parse the
saved built model)**. Crucially, **D0 and D1 both require the editor**, so they do NOT
help de-containerization: the only editor-free way to build geometry is D2. So
de-containerization is precisely the justification that flips the 12:40 gate and makes
D2 *required*. This roadmap **references** that spec; it does not re-spec D2.
6. Build D2 — partition heuristic gate CLEARED (`decisions.md` 2026-06-26, fuzz-verified
   0/200k); remaining `SplitPolyList`/coplanar-merge/leaf-zone build is the multi-week
   faithful port. Residual unknown from that entry: **node-plane parity** (needs a binary
   `UModel` parser; the ship bar is count-exact faces/leaves, not bit-identical trees).
   Differential-verify against the editor as a **build-time/CI oracle** (see Phase E).
7. Invert the `Model` serial format so D2's built model writes into the `.dx` — **DONE +
   validated byte-exact** (`2026-06-28-umodel-serialize-byte-exact.md`,
   `bspspike/umodel_serialize.py`): 72419/72419 `Model` exports re-serialize identically to
   the original. So this step is no longer a risk — the inverse exists and is proven. What
   remains for the acceptance below is feeding it a `Model` D2 *generated* (not re-parsed).
   Acceptance: a brush level builds + writes + **loads + plays in the actual game** with
   correct geometry/collision, no editor.

**Geometry fallback (if D2 stalls) — the value-first rung.** Mirroring the repo's own
12:40 instinct (don't bury all value behind the multi-week port): an intermediate where
the **editor builds only the `Model`** (one `MAP REBUILD` in a throwaway editor) while
uedctl writes everything else natively. This captures most container reduction (texture,
qualify, read, container write, stub deletion) and removes the editor from every step
*except* the geometry bake — exactly parallel to the Phase E lighting `--final-bake`. It
keeps the editor as an opt-in geometry step rather than the per-operation editor of today.

**Phase D — stub deletion (free, gated on A–C):**
8. Delete `stub.py`/`uscript_rewrite.py`/`stub_cache.py`/`stub_closure.py` +
   `ephemeral_build_container`; drop the v68→v69 path. Schema/asset reads already use the
   real `.u`.

**Phase E — full editor elimination (downstream of D2):**
9. Native lighting bake (2nd long pole); native pathnode reachspec build (moderate).
   Until then, an opt-in `--final-bake` editor pass does lighting+paths only.
10. Retire the **runtime** `uned/` Docker path from the authoring loop (the per-operation
    editor: `editor.py`, `driver.py`, `materialize.py`'s editor legs, `xfer.py`).

**Runtime Docker vs build-time/CI oracle — keep them distinct.** "Stop needing Docker"
targets the **authoring loop**, not the test harness. The editor/Docker stack must
SURVIVE as a **build-time differential-verify oracle** for D2 and the native writer
(`decisions.md` 2026-06-24 09:07: "the editor is retained as the test-time oracle, not a
runtime path"; the parallel-editors harness). So Phase E deletes the runtime editor
dependency while a CI/dev-only editor image remains to validate native output against
ground truth. A thin opt-in editor adapter (`--final-bake`, geometry fallback) is the
only editor an end user might invoke until native lighting/paths land.

## What a from-scratch writer must synthesize (beyond the proven container)

The byte-exact round-trip proves the container; a writer emitting NEW content also needs
(none of these are in the spikes yet — enumerated so they aren't forgotten):
- **The `ULevel` body** — its ordered actor array, `Model` reference, `Reachspecs`,
  `URL`/`TimeSeconds`, etc. (writing actors as exports ≠ serializing the Level object).
- **In-package ("myLevel") resources** — a level can hold *internal* texture/Model
  exports (decals, screenshots; lightmaps live in the Model). Qualification (S4) covers
  *external* refs via the import table; in-package exports on write are unaddressed.
- **Package version policy on write** — retail maps are v68, the substrate is v69; a NEW
  level has no source version. Pick and justify the emitted version (likely v69).
- **GUID + generations synthesis** — `write_full` reuses the parsed ones; a new package
  must mint a GUID and build the generations table.
- **Sounds/music (`.uax`/`.umx`)** — referenced externally (S4 sees 24 Sounds/1 Music as
  qualified imports), so no decode needed *if* always external; confirm and state so.
- **Collision vs render** — in UE1 the BSP itself serves collision; D2 must produce a
  Model that is correct for *both* (a count-exact but geometrically-wrong Model can crash
  or HoM), and reachspec tracing depends on it.

## Irreducible minimum / honest caveats

- **Until D2 lands, no native playable `.dx`** — UE1 has no runtime CSG (`MAP REBUILD` is
  editor-only), so geometry must be built offline. *Premise — CONFIRMED game-side 2026-06-28
  (was lore):* the game loads the pre-built BSP and never re-runs CSG, and uses that BSP for
  **both** render and collision (a 0-node world fails player spawn; a 68-node world spawns +
  walks collision-bound). So the worry that "the game may re-derive collision/bounds at load"
  is closed — a correct pre-built `Model` suffices. *Residual gate — now CLOSED (🔬 2026-06-29,
  `spikes/2026-06-28-native-model-game-load/`):* a `.dx` whose level `Model` body was
  re-serialized from structure AND one that was NATIVELY MODIFIED (a rigid BSP translation —
  geometry no editor wrote) both load and spawn + possess the player on a fully functional
  level, while a native 0-node `Model` reproduces the spawn crash (discrimination proven). So
  no serialization/container/load-acceptance risk remains in front of D2; the sole remaining
  geometry unknown is D2's array *generation* from authored brushes. (Offline node-count tell:
  `umodel_parser.parse_model_serial(...).nodes` non-empty.) Phases A/B deliver real value
  (native texture/qualify/read, container-free reads) *before* D2.
- **Until native lighting (Phase E), a usable map needs one editor bake** (renders black
  otherwise). This is the last editor dependency to fall; it's an opt-in final step, not
  the per-operation editor of today.
- **v61 packages** are read-only content (textures) — native decode works (S1); native
  *write* of v61 would need `Heritage`-table handling, but maps are v68/v69 so N/A.
- Non-P8 texture formats (`RGBA7`/`DXT`/…) unimplemented — none in DeusEx content; add per
  target substrate (e.g. UT).

## Risks
- **D2 fidelity** — a wrong BSP build = holes/HoM/bad collision. Mitigation: the existing
  differential harness (editor as CI oracle), the cleared partition gate, count-exact
  ship bar (decisions.md 2026-06-24 12:40).
- **Native lighting fidelity/effort** — large; can stay an editor final-bake indefinitely
  without blocking the rest.
- **Package-write completeness** — actor/`Level`/`Model` bodies must be valid for the
  game loader; acceptance tests load real output in editor+game (not just editor).
- **Model serial format — RESOLVED, both directions** (was a flagged risk): read is decoded
  + validated byte-exact on 12/12 maps; **write is now built + validated byte-exact on
  72419/72419 `Model` exports across 82 v68 install maps** (`2026-06-28-umodel-serialize-byte-exact.md`)
  — no longer "the mechanical inverse" by assertion. Residual: the `FBspVert.iVertex`
  pool semantic (interpretation, not I/O); D2's node-plane parity (count-exact, not
  bit-identical — decisions.md 2026-06-26); and the read parser's fixed-42 UPrimitive-prefix
  assumption that mis-reads 243 models (the serializer auto-detects 42-vs-57; folding
  `detect_prefix` back into `umodel_parser` is a flagged follow-up).

## Portability interaction (generic-UE1 / `.unr`)

`architecture.md` states uedctl aims to be a generic UE1 tool. De-containerization *helps*
that goal: native readers (texture/mesh/package) generalize across UE1 games where a
DeusEx-stubbed editor does not. Caveats: the decoders are validated only on DeusEx content
(P8 textures, 8-byte DeusEx verts, v61/68/69) — a UT/Unreal substrate may use packed
4-byte verts and non-P8 formats, so per-substrate decode paths are needed; and D2's
float32-faithful build is tuned to the UED22/DeusEx engine constants. Treat the native
work as *advancing* portability, not completing it.

## Open questions for Andrzej (candidates for `inbox.md` — not auto-added)
0. **The pivotal one — geometry strategy:** commit to building **D2** (promoting it from
   the 12:40 "optional, measurement-gated" status to *required*, since the editor-based
   D0/D1 path can't serve an editor-free pipeline), OR adopt the **editor-`MAP
   REBUILD`-only-geometry intermediate** (editor builds just the `Model`, uedctl writes
   the rest natively)? This single choice decides whether this is a multi-week project or
   a few-weeks one. *Update 2026-06-28:* the **premise** sub-facts this fork rode on are now
   settled — no runtime CSG, pre-built BSP serves collision, v69 is game-compatible — so Q0
   is purely the **effort/strategy** fork, not a feasibility unknown. The single fact that
   would most de-risk the D2 branch — that a **natively-written `Model`** (not an
   editor-built one) loads in the game — is now cheaply probeable; the **minimal native
   `Model` → game** spike (see "Irreducible minimum") is the gate to run before committing.
1. Acceptable end state: **fully native incl. lighting** (Phase E, big), or **native loop
   + optional editor final-bake** (stop at Phase D)? This sets the scope.
2. Priority order: chase the texture/qualify/read wins (Phase A, weeks) first for
   immediate container reduction, or invest straight into D2 (the long pole)?
5. Two distinct "keep an editor" questions, don't conflate: (a) retain the editor/Docker
   image as a **build-time/CI differential-verify oracle** (almost certainly yes — D2
   needs it)? (b) ship a **runtime opt-in editor adapter** (`--final-bake`/geometry
   fallback) to end users, or commit to 100% runtime elimination?
3. Native lighting: bake to full editor parity, or a "good enough" approximate baker?
4. Keep a thin optional editor adapter long-term (final-bake/preview), or commit to 100%
   elimination?

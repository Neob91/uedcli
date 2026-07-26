# UE1 / Deus Ex level-design knowledge base — `kb/`

The **comprehensive DEV reference**: ALL the UnrealEngine-1 / Deus Ex level-design knowledge gathered
while building uedctl — the distilled output of a multi-pass crawl of the community tutorial corpus,
reconciled against the shipped game binaries and uedctl's own offline decoders. This `kb/` directory is
the *internal* superset (it lives under `dev/docs/`); it deliberately keeps **everything collected**,
including asset-creation, modding-adjacent, and editor-GUI depth that a uedctl user never needs. Nothing
here is compressed for brevity — this is the durable, exhaustive record.

> **The curated user cut is elsewhere.** The reader-facing subset — the level-design craft scoped to what
> someone *authoring a level with uedctl* actually needs — lives outside `dev/` at
> [`docs/leveldesign/`](../../../../../docs/leveldesign/). This `kb/` tree is the superset it is drawn from; when
> the two disagree, `kb/` is the record of what was found and the user doc is the editorial cut.

> **What the user cut EXCLUDES (editorial scope — keep this in mind when editing `docs/leveldesign/`).**
> The user cut documents only what a uedctl *author* can actually **set or observe**: placeable classes,
> their **editor-editable (`var()`) properties**, the verbs, and the craft. It deliberately **omits**
> anything a mapper can't author or run — **engine-internal / non-editable (plain `var`) properties**
> (e.g. a `ScriptedPawn`'s `Restlessness`/`SightPercentage`, the agitation/fear sustain-decay constants,
> `bCanConverse`), decompiled internals and byte/offset detail, the **`🔬` live-probe marker**,
> asset-creation / modding depth, and editor-GUI trivia. Those live **only here in `kb/`**.
> **Rule of thumb: if a property has no editor category (it's a plain `var`, not `var(Category)`), it does
> NOT belong in `docs/leveldesign/`** — name it here in `kb/`, not there. (uedctl distinguishes the two:
> a property whose decoded schema `category` is `None` is non-editable — see `uprops`.)

uedctl authors the git-tracked T3D trunk with composing verbs (`brush build … | actor add -`, `brush poly
set`, `actor prop set`, `mover key …`, `actor order --first|--last`); the editor is touched only to `level
materialize` / `level preview`. Read craft here as **"which verb achieves this"**, with the UnrealEd GUI
action kept as an annotation.

## Confidence markers (repo convention)

- ✅ uedctl-used / live-verified · 🔬 live-probed against the real binary/editor · 📖 extracted from
  community tutorials (vocabulary real, semantics to confirm).
- Facts grounded in the disassembly spike
  [`../../../spikes/2026-06-24-bsp-csg-hole-mechanism-from-binary.md`](../../../spikes/2026-06-24-bsp-csg-hole-mechanism-from-binary.md)
  are **decompiled facts** — a tier *stronger* than 📖 (we read the compiled instructions and constants,
  not just string literals).

## Scope tags

- **[ENGINE]** = generic UnrealEngine 1 (applies to Unreal/UT/Deus Ex alike).
- **[DX]** = Deus-Ex-specific. Keeping these apart is load-bearing: DX subclasses and presets differ from
  stock UE1, and UT-only content/gametypes do **not** transfer.

## The files

| File | Scope | What it covers |
|---|---|---|
| **[README.md](./README.md)** | — | this index |
| **[csg-bsp.md](./csg-bsp.md)** | [ENGINE] | **the core file.** CSG subtractive workflow, the builder brush, brush order / last-op-wins, Intersect vs Deintersect, the full solidity table, and the DEEP BSP-problems catalog with the true (disassembly-reconciled) hole mechanism, tiered prevention, the repair table, source contradictions, and myths to reject |
| **[zones-performance.md](./zones-performance.md)** | [ENGINE] | zones, zone-portal sheets vs solid boundaries, the occlusion model (no antiportals), hard limits (≤~64 zones, see-through depth 3, poly budget ≤150, node:poly ~2:1, 65536-node crash), STAT/rmode commands, build order, brush-vs-mesh, finishing/optimization workflow |
| **[geometry-builders.md](./geometry-builders.md)** | [ENGINE] | native brush builders (Cube/Cylinder/Cone/Tetrahedron/Sheet/Volumetric/three stair builders/Terrain) with full params, Tarquin extended builders, brush clipping, curved geometry (Revolve/Bézier/iris doorway), UE1 terrain (no heightmap TerrainInfo), MeshMaker — mapped onto the uedctl `brush build` verbs |
| **[lighting.md](./lighting.md)** | [ENGINE] (DX enums 🔬) | lightmaps vs runtime actor lighting, the bake pipeline, `Light` properties, the `LightType` (temporal) vs `LightEffect` (spatial) split, the `LE_Negative`-absent correction, lighting craft |
| **[textures.md](./textures.md)** | [ENGINE] + [DX] | per-surface texturing, the full surface-flag catalog with hex, alignment/scrolling, `MyLevel`, water/fog/fire/skybox recipes, the DX `CoreTex*` catalog, procedural (`Fire.u`) and scripted textures |
| **[movers.md](./movers.md)** | [ENGINE] + [DX] | the mover family (engine subclasses vs the DX `DeusExMover` family), keyframes and the inverted-record trap, `MoverEncroachType`, the self-lighting "black door" fix, triggering |
| **[actors-collision-pathing.md](./actors-collision-pathing.md)** | [ENGINE] (DX flagged) | the non-geometry actor layer: cylinder collision + flag families, the `Physics` enum, decorations, `PlayerStart`, the KeyPoint family, `NavigationPoint`/pathing and reachspecs |
| **[dx-classes.md](./dx-classes.md)** | [DX] 🔬 | the Deus Ex class catalog an author reaches for: movers/doors, zones, hackable devices, pickups/keys, `DeusExLevelInfo`, the DX particle/effects family, and the gameplay-wiring actors (flags/goals/logic/sequence/laser triggers, security-camera→console) |
| **[dx-npcs.md](./dx-npcs.md)** | [DX] 🔬 | populating levels with `ScriptedPawn`s: `Orders` states, the three stimulus blocks (Reactions/Stimuli-Hate/Fears), combat tuning, the class roster, binding/alliances, the authoring workflow, and the UT names that do NOT exist in DX |
| **[dx-conversations-computers.md](./dx-conversations-computers.md)** | [DX] 📖 | ConEdit conversation authoring, computers (`ComputerPersonal/Public/Security`), info devices / DataCubes / DataVault images, and `ScriptedTexture` draw-on surfaces |
| **[asset-pipeline.md](./asset-pipeline.md)** | [DX] 📖 | the custom-content pipeline: packages + `ucc make`, meshes, textures, sounds, music, pickups/augmentations, credits |
| **[editor-ui.md](./editor-ui.md)** | [ENGINE] | editor UI & console reference — hotkeys, brush colours, browsers, the prefab `.T3D` import/export split (GUI trivia; uedctl drives verbs, not this) |
| **[human-scale.md](./human-scale.md)** | [ENGINE] + [DX] 🔬 | the human-scale numbers table (unit scale, player cylinder, jump/speed/step, stairs, doorways, ceilings, grid, poly/zone limits, path spacing) with source + how each was measured |
| **[design-craft.md](./design-craft.md)** | [ENGINE] + [DX] | the craft of a good level — composition, flow & pacing, and the Deus Ex immersive-sim design philosophy ("problems, not puzzles", multiple keyed routes, systemic consistency, legibility by architecture) |
| **[sources.md](./sources.md)** | — | provenance: every source crawled with its scope, the binary verifications done, access notes, and the residual gaps |

## How this KB was built

Sources: Steve Tack's Deus Ex Lab (DX), Wolf's Tutorials (**Unreal 1998, engine-generic — not DX**), the
tactical-ops.eu UT99 editor archive, lodev's lighting page, the BeyondUnreal/OldUnreal Legacy wikis, the
official Deus Ex SDK "Level Design" manual, the DeusEx `.uc` source, the Spector/Smith immersive-sim design
talks, and 🔬 direct greps + uedctl decodes of `DX/System/{Engine,DeusEx,Fire}.u` and `DX/Textures/*.utx`.
Full provenance, per-source scope, and the binary-verification log are in [`sources.md`](./sources.md).

New UnrealEd findings go here (and get back-referenced from code comments); durable engine facts that are
checkable get a committed regression per the spikes rule.

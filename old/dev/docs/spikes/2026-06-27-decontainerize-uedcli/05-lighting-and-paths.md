# Spike 5 — lighting & pathnodes: the second long pole (disposition)

**Status: RESOLVED (analysis). Both are build output, not authored state — they don't
block the native authoring/geometry loop. But a *good* shippable map needs them, and
native lighting is the second-biggest effort after the BSP engine. Recommended:
optional editor final-bake now, native bake later.**

## What they are

- **Lighting (`LIGHT APPLY`)** — bakes per-surface **lightmaps** into the built
  `Model` from the `Light` actors (brightness/radius/hue/saturation) with BSP-traced
  shadowing. The game renders with these prebuilt lightmaps. **Without them the map
  "renders black by default"** (`architecture.md`: `MAP REBUILD` wipes lighting, so
  `LIGHT APPLY` must run every materialize or the result is black). So lighting is
  NOT skippable for a usable DeusEx map.
- **Pathnodes (`PATHS DEFINE`)** — builds **reachspecs** (the AI navigation graph:
  `nextNavigationPoint`/`visitedWeight`/`VisNoReachPaths`) between `NavigationPoint`
  actors via collision reachability. Without them the map loads and plays for the
  human, but **AI can't navigate**.

Both are **regenerable build output** — not authored, never in `canonical_level_hash`
(direction/materialize.md 2026-06-23; `t3d.md` "What T3D cannot carry"). Losing/rebuilding them is
explicitly a non-concern for the model. They are *final-bake* concerns, not part of
the edit loop.

## Dependency ordering

Both consume the **built BSP**: lightmaps attach to built surfaces; reachspecs trace
against built collision. So they necessarily come **after** the offline BSP engine
(D2) in any native pipeline — they can't be the first thing tackled.

## Concrete lightmap storage (measured 2026-06-27)

Inspecting `00_Intro.dx`'s built level `Model` natively (`bspspike/umodel_parser.py`):
- **4211 `FLightMesh` descriptors** (`UModel+0xa8`) — one per lit surface region (surf
  count 4573); each carries a base position + lumel-grid extents.
- **~1.7 MB of raw lumel bytes** (`UModel+0xb4`, count 1 739 082) — the precomputed
  per-surface light intensities.
- **All 4573 surfs reference a lightmap** (`FBspSurf` field `iLightMap`).

So native lighting must, for every surface: lay out a lumel grid, and for each lumel
trace visibility/attenuation to every `Light` actor through the built BSP (shadow rays),
producing that 1.7 MB. That is a **lightmapper** (per-lumel raytrace + the engine's
attenuation/`LightSaturation` model), inherently **downstream of D2** (needs the built
surfaces to lay out lumels and the BSP to trace shadows). It is genuinely the second
major project — concretely sized here, not hand-waved.

## Options

| Option | Lighting | Paths | Verdict |
|---|---|---|---|
| **A. Native bake** | port the engine lighting build (per-surface lightmap from lights + BSP shadow rays) — **substantial; the 2nd long pole** | port reachspec build (graph + collision raycasts) — **moderate** | the end goal; large |
| **B. Baseline / defer** | flat ambient/fullbright so it's not black — playable, ugly | none — no AI nav | OK for iteration, not ship |
| **C. Optional editor final-bake** | one `LIGHT APPLY` in a throwaway editor, opt-in, only before ship | one `PATHS DEFINE` likewise | pragmatic: keeps the *whole* edit/geometry/texture/write loop native+offline; the editor is invoked ONLY as a final polish, not in the day-to-day loop |

## Recommendation

Sequence: **B for the iteration loop, C as the ship step, A as the long-term goal.**
This means **the editor is not eliminated on day one** — it survives as an *optional,
opt-in final-bake* (lighting + paths) — but it leaves the core authoring path
(edit → geometry build → texture/qualify → native `.dx` write → preview) fully
container-free. Native lighting (Option A) is the second major engineering project
after the BSP engine; native paths is a smaller follow-on. Both should be specced as
their own roadmap items, explicitly downstream of D2.

## Honest bottom line on "stop needing Docker overall"

- **Day-to-day editing loop: fully container-free** is reachable with Spikes 1–4 +
  D2 + the native writer (no editor, no UCC, no umodel, no ImageMagick).
- **100% editor elimination (incl. final lighting/paths bake)** additionally needs
  native lighting (big) + native paths (moderate). Until those land, a single optional
  editor pass remains for final-bake — which is a world apart from today's
  editor-in-every-operation model.

## Deferred / next
- Empirically confirm the "renders black without lightmaps" severity in the *game*
  (vs editor) and whether a minimal ambient avoids it — cheap-ish editor/game probe.
- Investigate whether the lightmap data format (the `Model` 0xb4 array, per the
  umodel-serialize-format spike) is writable so a native baker can emit it.
- Spec native lighting + native paths as downstream roadmap items.

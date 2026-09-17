// The "lights up" highlight for a selected SURFACE (single texture/polygon) -- `SurfaceSelectionHighlight`
// below. Renders an overlay mesh restricted to just the selected triangles, sharing the base
// geometry's `position`/`uv` attributes directly (an indexed subset -- no vertex data duplicated, one
// small index buffer per draw group), drawn with additive-white blending: a pure brightness boost on
// top of the actor's own material/texture. Shared by both Viewport3D and OrthoViewport. Only meaningful
// when the base mesh itself is drawn (not in 'wireframe' mode) -- callers gate on `mode !== 'wireframe'`.
// (A WHOLE-brush selection no longer uses any face overlay -- it recolors the brush's outline ring,
// `BrushOutlines`; the old `selectedNames`-driven overlay was removed, owner ruling.)
//
// Split by draw GROUP (2026-09-15, mesh-actor "oversized head" fix): a flat, mapless white overlay
// over every selected triangle silently ignored each triangle's own MASKED cutout
// (`sceneResources.ts`'s `resolveMaterialState` -- `alphaTest` against the base texture's alpha
// channel, which is how a fence hole/rotor blade/NPC hair-card silhouette is cut from its quad).
// Real evidence (`_scratch/probe_npc_mesh.py`, decoding stock `DeusExCharacters` meshes): every
// probed NPC body mesh carries a masked, two-sided head/hair material (`PolyFlags` `0x102`) with a
// bounding box a large fraction of the whole body's -- so revealing its untested quad on selection
// reads exactly like "the head renders oversized." Non-NPC meshes with no masked material (a plain
// crate) never showed it, matching the original bug report's "non-NPC selects fine." A masked deco
// prop (a ceiling fan's blades) has the SAME latent bug; the fix is general, not NPC-specific.
//
// Fix: group the selected triangles by the base mesh's own `THREE.BufferGeometry.groups` (one
// overlay sub-mesh per group with a selected triangle) and give a MASKED group's overlay material
// the same `map`/`alphaTest`/`side` its real base material uses, so the highlight is clipped to the
// actual visible (alpha-tested) shape -- never wider than what the un-highlighted mesh already
// shows. An unmasked group keeps the original flat, mapless white overlay unchanged. Cosmetic
// tradeoff, deliberate: a masked group's highlight shows through the real base texture (tinted by
// the additive white, not painted a flat color) rather than a perfectly flat white shape -- getting
// a flat-white-but-alpha-tested overlay needs a custom shader (an `alphaMap` samples a texture's
// GREEN channel, not its real alpha, so it can't reuse the base texture's actual mask); not worth
// the complexity for a low-opacity (0.25) additive overlay that already reads as "brighter," not "a
// new color." No live UnrealEd capture of how it renders a SELECTED mesh actor exists to compare
// against (checked `unrealed/quirks.md`/`rendering.md` -- nothing citable, same gap
// `selectedTriangles.ts`'s original doc comment already noted for brush surfaces); this is the most
// defensible fix from static analysis of this bug's actual mechanism, not a guess at UED22's own
// technique.
import { useEffect, useMemo } from 'react'
import * as THREE from 'three'

import { SELECTED_SPRITE_TINT } from './selectionColor'
import {
  selectedActorTriangleGroups,
  selectedSurfaceTriangleGroups,
  type SelectedTriangleGroup,
  type TriangleGroupRange,
} from './selectedTriangles'

// `polygonOffsetUnits` magnitude for both highlight variants below (bumped from 1, 2026-09-17,
// `poly-highlight-not-visible-for-brush116-0`, NOT live-screenshot-confirmed -- an untested guess,
// not a measured fix): a poly's overlay shares its exact triangle position with the base mesh, so it
// always needs SOME offset to win the depth-test tie -- but the slope-scaled `polygonOffsetFactor`
// term contributes ~0 for a surface viewed near HEAD-ON (`Brush116`'s counter-top viewed from above,
// `Brush111`'s wall sign read face-on -- both verified real, non-degenerate polys, identical in
// every other data/render-tree respect to a working control poly), leaving only the constant
// `polygonOffsetUnits` term to separate it. `Viewport3D.tsx`'s camera spans `near: 1, far: 131072`,
// which compresses depth-buffer precision at distance -- plausibly enough to lose a magnitude-1 tie.
// Only `polygonOffsetUnits` is raised here, since it's the one term the theory implicates;
// `polygonOffsetFactor` is left at its original magnitude to avoid changing behavior for
// steep-angle surfaces this bug never touched.
const POLYGON_OFFSET_UNITS_MAGNITUDE = 4
const POLYGON_OFFSET_FACTOR_MAGNITUDE = 1

// Additive white, not a new hue -- a brightness boost that reads correctly over any base texture/CSG
// color. Moderate opacity so it reads as "lit up," not a blown-out white silhouette.
const HIGHLIGHT_COLOR = 0xffffff
const HIGHLIGHT_OPACITY = 0.25

/** The surface (single-polygon) selection highlight (GUI.md "Selection & the Inspector"): a texture
 * selection highlights only the ONE clicked polygon's triangles. (A WHOLE-brush selection no longer
 * lights up faces at all -- it recolors the brush's outline ring instead, `BrushOutlines`; the old
 * whole-brush additive-white overlay was removed, owner ruling.) Additive-white overlay technique
 * (see the module doc comment above), driven from `selectedSurfaces` (`selectionSet.ts`'s
 * `surfaceKey` strings). */
export interface SurfaceSelectionHighlightProps {
  bufferGeometry: THREE.BufferGeometry
  triangleOwners: (string | null)[]
  trianglePolyIndex: (number | null)[]
  selectedSurfaces: ReadonlySet<string>
  materials: readonly THREE.Material[]
}

export function SurfaceSelectionHighlight({
  bufferGeometry,
  triangleOwners,
  trianglePolyIndex,
  selectedSurfaces,
  materials,
}: SurfaceSelectionHighlightProps) {
  const groups = useMemo(
    () =>
      selectedSurfaceTriangleGroups(
        triangleOwners,
        trianglePolyIndex,
        selectedSurfaces,
        bufferGeometry.groups as TriangleGroupRange[],
      ),
    [triangleOwners, trianglePolyIndex, selectedSurfaces, bufferGeometry],
  )
  return <HighlightGroups groups={groups} bufferGeometry={bufferGeometry} materials={materials} />
}

/** The WHOLE-ACTOR (mesh actor) selection highlight (GUI-PARITY.md "Selection highlight
 * rendering"): every triangle owned by a selected non-brush actor lights up, using the SAME
 * multiplicative tint as a selected point-actor sprite (`SELECTED_SPRITE_TINT`,
 * `selectionColor.ts`) -- an opaque redraw, not a translucent wash, so the base texture/shading
 * stays fully visible underneath the tint (see `selectionColor.ts`'s doc comment for why this
 * replaced the earlier UED22-formula alpha-blend approximation). Never reached for a brush -- brush
 * whole-actor selection recolors its outline ring (`BrushOutlines`) instead. */
export interface ActorSelectionHighlightProps {
  bufferGeometry: THREE.BufferGeometry
  triangleOwners: (string | null)[]
  selectedActorNames: ReadonlySet<string>
  materials: readonly THREE.Material[]
}

export function ActorSelectionHighlight({
  bufferGeometry,
  triangleOwners,
  selectedActorNames,
  materials,
}: ActorSelectionHighlightProps) {
  const groups = useMemo(
    () => selectedActorTriangleGroups(triangleOwners, selectedActorNames, bufferGeometry.groups as TriangleGroupRange[]),
    [triangleOwners, selectedActorNames, bufferGeometry],
  )
  return <HighlightGroups groups={groups} bufferGeometry={bufferGeometry} materials={materials} color={SELECTED_SPRITE_TINT} opaque />
}

function HighlightGroups({
  groups,
  bufferGeometry,
  materials,
  color = HIGHLIGHT_COLOR,
  opacity = HIGHLIGHT_OPACITY,
  blending = THREE.AdditiveBlending,
  opaque = false,
}: {
  groups: SelectedTriangleGroup[]
  bufferGeometry: THREE.BufferGeometry
  materials: readonly THREE.Material[]
  color?: THREE.ColorRepresentation
  opacity?: number
  blending?: THREE.Blending
  // The actor-tint variant: a fully opaque redraw (never translucent), and it ALWAYS samples the
  // base material's own map/alphaTest (even for an "unmasked" group) so the multiply preserves the
  // real texture/shading instead of painting a flat silhouette -- the surface-pick (additive-white)
  // variant keeps its existing masked-only map usage, since a flat brightness boost never needed the
  // texture for an unmasked group.
  opaque?: boolean
}) {
  // `opaque` groups whose BASE material is itself translucent/modulated (`sceneResources.ts`'s
  // `resolveMaterialState`: NPC glasses-lens/-frame slots, additive/multiply blend, `transparent:
  // true`) must draw NOTHING here. These slots default to deliberately near-invisible placeholder
  // textures (`BlackMaskTex` under real additive blend, `GrayMaskTex` under real 2x-multiply -- both
  // blend to "no visible change," the "sunglasses" bug this file's sibling doc comment already
  // covers) -- our opaque tint has no equivalent blend-mode reproduction, so sampling that same
  // placeholder texture and drawing it OPAQUE turns "invisible" into "a solid tinted shape" (bug:
  // "something in place of eyeglasses"). Filtered out HERE (before a `SelectionHighlightGroup`
  // mounts at all), not as an early return inside it -- that component's hooks (two `useMemo`s) must
  // run unconditionally every render, so skipping mid-component would violate the Rules of Hooks.
  const visibleGroups = opaque ? groups.filter(({ materialIndex }) => !(materials[materialIndex] as THREE.MeshBasicMaterial | undefined)?.transparent) : groups
  if (visibleGroups.length === 0) return null
  return (
    <>
      {visibleGroups.map(({ materialIndex, indices }) => (
        // Keyed by materialIndex + this group's own first triangle index, not materialIndex alone
        // -- two DIFFERENT `bufferGeometry.groups` entries can share one materialIndex
        // (`sceneResources.ts` collapses a lit/unlit pair onto one material when no lightmap is
        // loaded, but still emits two separate `addGroup` ranges), so materialIndex alone can
        // collide. `indices[0]` is a triangle's flat vertex index, unique across the whole shared
        // geometry, so the pair is always unique.
        <SelectionHighlightGroup
          key={`${materialIndex}-${indices[0]}`}
          bufferGeometry={bufferGeometry}
          indices={indices}
          baseMaterial={materials[materialIndex]}
          color={color}
          opacity={opacity}
          blending={blending}
          opaque={opaque}
        />
      ))}
    </>
  )
}

interface SelectionHighlightGroupProps {
  bufferGeometry: THREE.BufferGeometry
  indices: number[]
  baseMaterial: THREE.Material | undefined
  color: THREE.ColorRepresentation
  opacity: number
  blending: THREE.Blending
  opaque: boolean
}

function SelectionHighlightGroup({ bufferGeometry, indices, baseMaterial, color, opacity, blending, opaque }: SelectionHighlightGroupProps) {
  const geometry = useMemo(() => {
    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', bufferGeometry.attributes.position)
    if (bufferGeometry.attributes.uv) geo.setAttribute('uv', bufferGeometry.attributes.uv)
    geo.setIndex(indices)
    return geo
  }, [bufferGeometry, indices])
  // Only the overlay geometry (the index buffer) is ours to dispose -- `position`/`uv` are SHARED
  // references to the base mesh's own attributes, still in use by it after this unmounts/rebuilds.
  useEffect(() => () => geometry.dispose(), [geometry])

  const base = baseMaterial instanceof THREE.MeshBasicMaterial ? baseMaterial : null
  const masked = (base?.alphaTest ?? 0) > 0
  const side = base?.side ?? THREE.FrontSide
  // `opaque` (the actor-tint variant) always mirrors the base material's own map/alphaTest, masked
  // or not, so the multiply reads the real texture. The additive-white (surface-pick) variant only
  // needs this for a masked group (see the module doc comment's cosmetic-tradeoff note) -- a flat
  // brightness boost over an unmasked group never needed the texture.
  const map = opaque || masked ? (base?.map ?? null) : null
  // `poly-highlight-not-visible-for-brush116-0` (reopened): a masked, fully-OPAQUE-alpha texture
  // (e.g. `Brush100:0`/`Brush106:0`/`Brush111:0`, `masked:true` but every texel alpha=255) never lit
  // up at all -- root-caused with an isolated three.js harness (`_scratch/browser_verify/harness/`),
  // not speculation: WebGL's `alphatest_fragment` chunk discards on `diffuseColor.a`, which is
  // `material.opacity * texel.alpha` (`map_fragment` multiplies opacity by the sampled texel, alpha
  // channel included), NOT the texel's alpha alone. The additive surface-pick overlay's `opacity` is
  // always `HIGHLIGHT_OPACITY` (0.25) -- so `diffuseColor.a` tops out at `0.25 * 1.0 = 0.25`, always
  // below the base's own `alphaTest` (0.5), discarding EVERY fragment regardless of the real texture
  // content. Scaling `alphaTest` by the overlay's own effective opacity cancels that multiply out:
  // `discard iff opacity*texel.a < baseAlphaTest*opacity` reduces to `texel.a < baseAlphaTest`, the
  // exact same cutoff the base material itself applies (verified in the harness: an opaque-alpha
  // texture now lights up, and a half-transparent test texture still stays dark on its cut-out half
  // -- 0 changed pixels there). This equivalence assumes the BASE material's own `opacity` is 1 --
  // true today, since `sceneResources.ts`'s `resolveMaterialState` never sets it. The opaque
  // (actor-tint) variant's real material opacity is always 1 (its params never set `opacity`
  // either), so its scale factor is 1 -- unchanged from before this fix.
  const effectiveOpacity = opaque ? 1 : opacity
  const alphaTest = opaque || masked ? (base?.alphaTest ?? 0) * effectiveOpacity : 0
  const material = useMemo(
    () =>
      new THREE.MeshBasicMaterial(
        opaque
          ? {
              color,
              // Opaque redraw -- no alpha math, so no order-dependence against other transparent
              // draws (unlike the translucent overlay this replaced). depthWrite:true lets it
              // participate in the depth buffer normally, same as any other opaque object this frame.
              depthWrite: true,
              polygonOffset: true, // avoid z-fighting against the base mesh's own coplanar triangles
              polygonOffsetFactor: -POLYGON_OFFSET_FACTOR_MAGNITUDE,
              polygonOffsetUnits: -POLYGON_OFFSET_UNITS_MAGNITUDE,
              side,
              map,
              alphaTest,
            }
          : {
              color,
              transparent: true,
              opacity,
              blending,
              depthWrite: false, // a pure visual overlay -- never occludes anything behind it
              polygonOffset: true, // avoid z-fighting against the base mesh's own coplanar triangles
              polygonOffsetFactor: -POLYGON_OFFSET_FACTOR_MAGNITUDE,
              polygonOffsetUnits: -POLYGON_OFFSET_UNITS_MAGNITUDE,
              side,
              map,
              alphaTest,
            },
      ),
    [opaque, color, opacity, blending, side, map, alphaTest],
  )
  useEffect(() => () => material.dispose(), [material])
  return <mesh geometry={geometry} material={material} />
}

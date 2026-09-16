// Issue 1 fix (2026-09-15): the "lights up" surface highlight for every selected brush. Renders an
// overlay mesh restricted to just the selected triangles (`selectedTriangleGroups`), sharing the
// base geometry's `position`/`uv` attributes directly (an indexed subset -- no vertex data
// duplicated, one small index buffer per draw group), drawn with additive-white blending: a pure
// brightness boost on top of the actor's own material/texture/CSG hue, per `selectedTriangles.ts`'s
// doc comment (matches `BrushOutlines`' "same hue, just bolder" convention rather than painting an
// alien highlight color). Shared by both Viewport3D and OrthoViewport, mirroring BrushOutlines/
// SelectionMarkers' own cross-pane sharing. Only meaningful when the base mesh itself is drawn (not
// in 'wireframe' mode, which has no surface to light up) -- callers gate on `mode !== 'wireframe'`,
// same as the base mesh.
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

import {
  selectedSurfaceTriangleGroups,
  selectedTriangleGroups,
  type SelectedTriangleGroup,
  type TriangleGroupRange,
} from './selectedTriangles'

// Additive white, not a new hue -- a brightness boost that reads correctly over any base texture/CSG
// color. Moderate opacity so it reads as "lit up," not a blown-out white silhouette.
const HIGHLIGHT_COLOR = 0xffffff
const HIGHLIGHT_OPACITY = 0.25

export interface SelectionHighlightProps {
  bufferGeometry: THREE.BufferGeometry
  triangleOwners: (string | null)[]
  selectedNames: ReadonlySet<string>
  /** The SAME per-group material array driving the base `<mesh>` (`activeMaterials` at the call
   * site) -- read for each group's own `map`/`alphaTest`/`side` so a masked group's overlay stays
   * clipped to its real cutout shape instead of lighting up the whole untested triangle (see the
   * module doc comment above). */
  materials: readonly THREE.Material[]
}

export function SelectionHighlight({ bufferGeometry, triangleOwners, selectedNames, materials }: SelectionHighlightProps) {
  const groups = useMemo(
    () => selectedTriangleGroups(triangleOwners, selectedNames, bufferGeometry.groups as TriangleGroupRange[]),
    [triangleOwners, selectedNames, bufferGeometry],
  )
  return <HighlightGroups groups={groups} bufferGeometry={bufferGeometry} materials={materials} />
}

/** The surface (single-polygon) counterpart of `SelectionHighlight` above (GUI.md "Selection & the
 * Inspector"): a texture selection is a DISTINCT selection kind from a whole-brush selection, and
 * highlights only the ONE clicked polygon's triangles -- never the whole brush's, even when the
 * brush itself is also drawn. Same additive-white overlay technique (see the module doc comment
 * above), just driven from `selectedSurfaces` (`selectionSet.ts`'s `surfaceKey` strings) instead of
 * `selectedNames`. */
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

function HighlightGroups({
  groups,
  bufferGeometry,
  materials,
}: {
  groups: SelectedTriangleGroup[]
  bufferGeometry: THREE.BufferGeometry
  materials: readonly THREE.Material[]
}) {
  if (groups.length === 0) return null
  return (
    <>
      {groups.map(({ materialIndex, indices }) => (
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
        />
      ))}
    </>
  )
}

interface SelectionHighlightGroupProps {
  bufferGeometry: THREE.BufferGeometry
  indices: number[]
  baseMaterial: THREE.Material | undefined
}

function SelectionHighlightGroup({ bufferGeometry, indices, baseMaterial }: SelectionHighlightGroupProps) {
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
  // Masked group only: clip the overlay to the SAME real cutout the base material already draws
  // (see the module doc comment's cosmetic-tradeoff note -- `map` here also tints the overlay by
  // the base texture, not a flat color, which is why this is skipped entirely for an unmasked group).
  const map = masked ? (base?.map ?? null) : null
  const alphaTest = masked ? (base?.alphaTest ?? 0) : 0
  const material = useMemo(
    () =>
      new THREE.MeshBasicMaterial({
        color: HIGHLIGHT_COLOR,
        transparent: true,
        opacity: HIGHLIGHT_OPACITY,
        blending: THREE.AdditiveBlending,
        depthWrite: false, // a pure visual overlay -- never occludes anything behind it
        polygonOffset: true, // avoid z-fighting against the base mesh's own coplanar triangles
        polygonOffsetFactor: -1,
        polygonOffsetUnits: -1,
        side,
        map,
        alphaTest,
      }),
    [side, map, alphaTest],
  )
  useEffect(() => () => material.dispose(), [material])
  return <mesh geometry={geometry} material={material} />
}

// The highlight for a selected SURFACE (single texture/polygon) -- `SurfaceSelectionHighlight`
// below. Renders an overlay mesh restricted to just the selected triangles, sharing the base
// geometry's `position`/`uv` attributes directly (an indexed subset -- no vertex data duplicated, one
// small index buffer per draw group). Shared by both Viewport3D and OrthoViewport. Only meaningful
// when the base mesh itself is drawn (not in 'wireframe' mode) -- callers gate on `mode !== 'wireframe'`.
// (A WHOLE-brush selection no longer uses any face overlay -- it recolors the brush's outline ring,
// `BrushOutlines`; the old `selectedNames`-driven overlay was removed, owner ruling.)
//
// The surface overlay reproduces UED22's own selected-surface rendering -- a screen-space STIPPLE of
// flat RGB(0,127,255) dots, not the additive-white wash this file used to invent. See
// `SURFACE_SELECTION_COLOR` below and GUI-PARITY.md "Surface selection highlight" for the
// disassembly it was read from.
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
// shows. The surface overlay restores its own flat color after the alpha test (see
// `stippleBeforeCompile`), so the mask only CLIPS the highlight; it never tints it.
import { useEffect, useMemo } from 'react'
import { useThree } from '@react-three/fiber'
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

// UED22's real selected-surface highlight, ✅ binary-confirmed against this project's own
// `uned/UED22/softdrv.dll` -- `SoftDrv.SoftwareRenderDevice` is the render device all four UnrealEd
// viewports are pinned to (`uned/UED22/UnrealEd.ini`), so this is THE path a selected surface takes.
// `USoftwareRenderDevice::DrawComplexSurface` (export RVA `0xc3a0`) ends with, at VA `0x1000e644`:
//
//     mov  eax, ds:0x10030114        ; Core.dll's GIsEditor (IAT-resolved)
//     cmp  dword ptr [eax], 0        ; editor only
//     je   done
//     test dword ptr [esi], 0x2000000 ; Surface.PolyFlags & PF_Selected
//     je   done
//     mov  byte ptr [ebp+0xc], 0x00  ; R
//     mov  byte ptr [ebp+0xd], 0x7f  ; G
//     mov  byte ptr [ebp+0xe], 0xff  ; B
//
// Channel order is not assumed -- byte-swapped this would be orange. The 32bpp path of the same
// function (`0x1000e7a6`-`0x1000e7bf`) repacks the bytes as `byte0<<16 | byte1<<8 | byte2` before
// storing, and a Win32 32bpp surface is `0x00RRGGBB`, so byte0 is R and byte2 is B. (The 16-bit
// packer below it and `Engine.dll`'s `FColor::FColor(const FPlane&)` agree but only under a
// convention; the 32bpp repack is the one that settles it.) So: RGB(0,127,255), a vivid azure.
// `PF_Selected = 0x02000000` is confirmed by `Editor.dll`'s `polySelectReverse` (RVA `0x4c2a0`),
// which does `xor eax, 0x2000000` on a surf's flags.
const SURFACE_SELECTION_COLOR = 0x007fff

// ...and the technique is NOT a blend of any kind. The block at `0x1000e66a`-`0x1000e870` walks the
// surface's own span buffer and does a raw `mov` of that color straight into the framebuffer
// (`mov word ptr [ecx], si` at 16bpp / `mov dword ptr [ecx], esi` at 32bpp) on a sparse lattice:
//
//   - rows: start at `(SpanBuffer->StartY + 1) & ~1`, step `+= 2` -- every SECOND scanline.
//   - columns: `x = align_up(span->Start + phase, 8) - phase`, step `+= 8` -- every EIGHTH pixel,
//     where `phase = (y & 2) * 2`, i.e. 0 when `(y>>1)` is even and 4 when it is odd.
//
// So 1 pixel in 16 is overwritten with the flat color, in a staggered dot lattice anchored to
// ABSOLUTE screen coordinates (it does not slide with the surface as the camera moves).
const STIPPLE_ROW_STEP = 2
const STIPPLE_COLUMN_STEP = 8
const STIPPLE_ROW_PHASE_SHIFT = 4

/** The surface (single-polygon) selection highlight (GUI.md "Selection & the Inspector"): a texture
 * selection highlights only the ONE clicked polygon's triangles. (A WHOLE-brush selection no longer
 * lights up faces at all -- it recolors the brush's outline ring instead, `BrushOutlines`; the old
 * whole-brush overlay was removed, owner ruling.) Draws UED22's own stipple technique (see
 * `SURFACE_SELECTION_COLOR` above), driven from `selectedSurfaces` (`selectionSet.ts`'s
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
  return <HighlightGroups variant="surface" groups={groups} bufferGeometry={bufferGeometry} materials={materials} />
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
  return <HighlightGroups variant="actor" groups={groups} bufferGeometry={bufferGeometry} materials={materials} />
}

/** `surface` = UED22's screen-space stipple of flat `SURFACE_SELECTION_COLOR` dots over a selected
 * BSP surface/poly. `actor` = the multiplicative `SELECTED_SPRITE_TINT` redraw over a whole selected
 * mesh actor (GUI-PARITY.md "Selection highlight rendering"). */
type HighlightVariant = 'surface' | 'actor'

function HighlightGroups({
  variant,
  groups,
  bufferGeometry,
  materials,
}: {
  variant: HighlightVariant
  groups: SelectedTriangleGroup[]
  bufferGeometry: THREE.BufferGeometry
  materials: readonly THREE.Material[]
}) {
  // `actor` groups whose BASE material is itself translucent/modulated (`sceneResources.ts`'s
  // `resolveMaterialState`: NPC glasses-lens/-frame slots, additive/multiply blend, `transparent:
  // true`) must draw NOTHING here. These slots default to deliberately near-invisible placeholder
  // textures (`BlackMaskTex` under real additive blend, `GrayMaskTex` under real 2x-multiply -- both
  // blend to "no visible change," the "sunglasses" bug this file's sibling doc comment already
  // covers) -- our opaque tint has no equivalent blend-mode reproduction, so sampling that same
  // placeholder texture and drawing it OPAQUE turns "invisible" into "a solid tinted shape" (bug:
  // "something in place of eyeglasses"). Filtered out HERE (before a `SelectionHighlightGroup`
  // mounts at all), not as an early return inside it -- that component's hooks must run
  // unconditionally every render, so skipping mid-component would violate the Rules of Hooks.
  // The `surface` variant is NOT filtered: UED22 stipples any selected surface, translucent ones
  // included, and its dots never sample the base texture, so the "solid tinted shape" failure mode
  // this filter exists for cannot happen there.
  const visibleGroups = variant === 'actor' ? groups.filter(({ materialIndex }) => !(materials[materialIndex] as THREE.MeshBasicMaterial | undefined)?.transparent) : groups
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
          variant={variant}
          bufferGeometry={bufferGeometry}
          indices={indices}
          baseMaterial={materials[materialIndex]}
        />
      ))}
    </>
  )
}

interface SelectionHighlightGroupProps {
  variant: HighlightVariant
  bufferGeometry: THREE.BufferGeometry
  indices: number[]
  baseMaterial: THREE.Material | undefined
}

function SelectionHighlightGroup({ variant, bufferGeometry, indices, baseMaterial }: SelectionHighlightGroupProps) {
  // The stipple lattice is defined in the EDITOR's own screen pixels, and a device pixel here is a
  // hi-DPI supersample of one CSS pixel -- so dividing `gl_FragCoord` by the renderer's pixel ratio
  // reproduces UED22's on-screen dot spacing instead of shrinking it by the DPR.
  const pixelRatio = useThree((s) => s.viewport.dpr) || 1
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
  // The `actor` tint always mirrors the base material's own map/alphaTest, masked or not, so the
  // multiply reads the real texture. The `surface` stipple needs the map only to CLIP a masked
  // group to its real cut-out shape (the "oversized head" fix above) -- its own dots are painted
  // flat afterwards, so an unmasked group needs no texture at all.
  const map = variant === 'actor' || masked ? (base?.map ?? null) : null
  // Both variants now draw fully opaque (`opacity` 1), so the base material's own `alphaTest` is
  // used unscaled. It could not be before: WebGL's `alphatest_fragment` discards on
  // `diffuseColor.a` = `material.opacity * texel.alpha`, so the old 0.25-opacity additive overlay
  // could never reach a 0.5 cutoff and discarded every fragment of a masked group regardless of the
  // real texture (`poly-highlight-not-visible-for-brush116-0`, reopened). This assumes the BASE
  // material's own `opacity` is 1 -- true today; `sceneResources.ts`'s `resolveMaterialState` never
  // sets it.
  const alphaTest = variant === 'actor' || masked ? (base?.alphaTest ?? 0) : 0
  const material = useMemo(() => {
    const mat = new THREE.MeshBasicMaterial({
      color: variant === 'surface' ? SURFACE_SELECTION_COLOR : SELECTED_SPRITE_TINT,
      // Opaque redraw -- no alpha math, so no order-dependence against other transparent draws.
      // The surface stipple never writes depth (a pure overlay of scattered dots); the actor tint
      // does, so it participates normally like any other opaque object this frame.
      depthWrite: variant === 'actor',
      polygonOffset: true, // avoid z-fighting against the base mesh's own coplanar triangles
      polygonOffsetFactor: -POLYGON_OFFSET_FACTOR_MAGNITUDE,
      polygonOffsetUnits: -POLYGON_OFFSET_UNITS_MAGNITUDE,
      side,
      map,
      alphaTest,
    })
    if (variant === 'surface') mat.onBeforeCompile = stippleBeforeCompile(pixelRatio)
    return mat
  }, [variant, side, map, alphaTest, pixelRatio])
  useEffect(() => () => material.dispose(), [material])
  return <mesh geometry={geometry} material={material} />
}

/** Turns a plain `MeshBasicMaterial` into UED22's selected-surface stipple: discard every fragment
 * outside the dot lattice described at `SURFACE_SELECTION_COLOR`/`STIPPLE_*` above, and paint the
 * survivors the flat selection color rather than the texture-modulated one (the map is only there to
 * alpha-clip a masked group). `gl_FragCoord` is an ABSOLUTE drawing-buffer coordinate, the same kind
 * of anchoring UED22's own lattice has -- so the dots stay put on screen as the camera moves,
 * exactly as they do in the real editor; dividing by the pixel ratio converts it to the CSS pixels
 * that correspond to the editor's own screen pixels. */
function stippleBeforeCompile(pixelRatio: number) {
  return (shader: { uniforms: Record<string, { value: unknown }>; fragmentShader: string }) => {
    shader.uniforms.uStipplePixelRatio = { value: pixelRatio }
    shader.fragmentShader = `uniform float uStipplePixelRatio;\n${shader.fragmentShader}`
      .replace(
        '#include <clipping_planes_fragment>',
        `#include <clipping_planes_fragment>
        {
          vec2 sp = floor( gl_FragCoord.xy / uStipplePixelRatio );
          float phase = mod( floor( sp.y * 0.5 ), 2.0 ) * ${STIPPLE_ROW_PHASE_SHIFT.toFixed(1)};
          if ( mod( sp.y, ${STIPPLE_ROW_STEP.toFixed(1)} ) > 0.5 ) discard;
          if ( mod( sp.x + phase, ${STIPPLE_COLUMN_STEP.toFixed(1)} ) > 0.5 ) discard;
        }`,
      )
      // After the alpha test has used the sampled texel, throw the texel's COLOR away: UED22's dot
      // is a raw framebuffer write of the flat color, never a modulation of what the surface drew.
      .replace('#include <alphatest_fragment>', '#include <alphatest_fragment>\n\tdiffuseColor = vec4( diffuse, 1.0 );')
  }
}

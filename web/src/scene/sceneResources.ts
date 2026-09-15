// Scene-building hooks extracted out of Viewport3D.tsx (quad-layout Part 0, Task 1): texture/
// lightmap/marker-texture loading and the built THREE.BufferGeometry/materials memo, verbatim, so a
// SceneResourcesContext (Task 2) can build them ONCE and share them across the Perspective pane and
// the three ortho panes instead of each pane re-uploading the same geometry to the GPU.
import { useEffect, useMemo, useRef, useState } from 'react'
import * as THREE from 'three'

import type { AtlasPayload, LightmapPayload, ScenePayload } from '../api'
import type { GeometryGroup } from './geometry'
import { buildGeometryData } from './geometry'

const UNTEXTURED_GREY = 0x808080

/** Extracts two `THREE.Texture`s per atlas entry, keyed by `tex_index`, by drawing that entry's rect
 * out of the atlas image onto its own canvas -- so each texture can tile with RepeatWrapping (a
 * shared atlas can't repeat past a tile boundary; bug A). NearestFilter matches the low-res look.
 *
 * `map` (world-poly base textures) sets `flipY=false` to keep the atlas's image-row UV convention
 * (V grows downward) -- `geometry.ts`'s `polyUVs` computes V in that SAME convention, so the two
 * agree. `sprite` (point-actor billboards, `<sprite>`'s built-in plane UVs -- (0,0) at the bottom
 * corner, standard flipY=true orientation) keeps three.js's DEFAULT `flipY=true`: a `THREE.Sprite`
 * has no custom UV geometry to compensate for `flipY=false` the way world polys do, so sharing the
 * `map` texture with a sprite renders it upside-down (bug: "sprites are rendered inverted"). Both
 * textures share the SAME canvas pixels, drawn once, so this costs one extra `CanvasTexture` wrapper
 * per atlas entry, not a second draw. Every live-reload swaps `atlas` and rebuilds both maps,
 * disposing the previous textures so nothing leaks; `currentRef` tracks what's live for the unmount
 * / lost-race cleanup too. */
export function useTextures(atlas: AtlasPayload): { map: Map<number, THREE.Texture>; sprite: Map<number, THREE.Texture> } {
  const [textures, setTextures] = useState<{ map: Map<number, THREE.Texture>; sprite: Map<number, THREE.Texture> }>(
    () => ({ map: new Map(), sprite: new Map() }),
  )
  const currentRef = useRef<{ map: Map<number, THREE.Texture>; sprite: Map<number, THREE.Texture> }>({
    map: new Map(),
    sprite: new Map(),
  })

  useEffect(() => {
    let disposed = false
    const img = new Image()
    img.onload = () => {
      if (disposed) return
      const nextMap = new Map<number, THREE.Texture>()
      const nextSprite = new Map<number, THREE.Texture>()
      for (const [key, rect] of Object.entries(atlas.manifest)) {
        const canvas = document.createElement('canvas')
        canvas.width = rect.w
        canvas.height = rect.h
        const ctx = canvas.getContext('2d')
        if (!ctx) continue
        ctx.drawImage(img, rect.x, rect.y, rect.w, rect.h, 0, 0, rect.w, rect.h)

        const mapTex = new THREE.CanvasTexture(canvas)
        mapTex.wrapS = THREE.RepeatWrapping
        mapTex.wrapT = THREE.RepeatWrapping
        mapTex.magFilter = THREE.NearestFilter
        mapTex.minFilter = THREE.NearestFilter
        mapTex.flipY = false
        mapTex.needsUpdate = true
        nextMap.set(Number(key), mapTex)

        const spriteTex = new THREE.CanvasTexture(canvas)
        spriteTex.magFilter = THREE.NearestFilter
        spriteTex.minFilter = THREE.NearestFilter
        spriteTex.needsUpdate = true // flipY stays the THREE.Texture default (true)
        nextSprite.set(Number(key), spriteTex)
      }
      currentRef.current.map.forEach((t) => t.dispose())
      currentRef.current.sprite.forEach((t) => t.dispose())
      currentRef.current = { map: nextMap, sprite: nextSprite }
      setTextures(currentRef.current)
    }
    img.src = `data:image/png;base64,${atlas.png_base64}`
    return () => {
      disposed = true
    }
  }, [atlas.png_base64, atlas.manifest])

  useEffect(() => {
    return () => {
      currentRef.current.map.forEach((t) => t.dispose()) // unmount: release whatever's still held
      currentRef.current.sprite.forEach((t) => t.dispose())
      currentRef.current = { map: new Map(), sprite: new Map() }
    }
  }, [])

  return textures
}

/** Decodes the lightmap atlas PNG into one `THREE.Texture` on `uv1` (channel 1, the second UV set
 * the geometry carries for lit polys). NearestFilter + ClampToEdge match render.rs's nearest,
 * edge-clamped lumel sampling (the atlas's 1-lumel gutter absorbs the clamp); `NoColorSpace` keeps
 * the stored multiplier linear (no sRGB decode); `flipY=false` matches the image-row V convention.
 * `null` (no lit polys) when the payload is absent or empty. Disposes on swap/unmount. */
export function useLightmapTexture(lightmap: LightmapPayload | null): THREE.Texture | null {
  const [texture, setTexture] = useState<THREE.Texture | null>(null)
  const currentRef = useRef<THREE.Texture | null>(null)

  useEffect(() => {
    if (!lightmap || Object.keys(lightmap.manifest).length === 0) {
      currentRef.current?.dispose()
      currentRef.current = null
      // Clear a stale texture when a level has (or loses) all its lights -- a genuine external-
      // system sync, not derivable during render.
      // oxlint-disable-next-line react/set-state-in-effect
      setTexture(null)
      return
    }
    let disposed = false
    const img = new Image()
    img.onload = () => {
      if (disposed) return
      const tex = new THREE.Texture(img)
      tex.channel = 1
      tex.wrapS = THREE.ClampToEdgeWrapping
      tex.wrapT = THREE.ClampToEdgeWrapping
      tex.magFilter = THREE.NearestFilter
      tex.minFilter = THREE.NearestFilter
      tex.colorSpace = THREE.NoColorSpace
      tex.flipY = false
      tex.needsUpdate = true
      currentRef.current?.dispose()
      currentRef.current = tex
      setTexture(tex)
    }
    img.src = `data:image/png;base64,${lightmap.png_base64}`
    return () => {
      disposed = true
    }
  }, [lightmap])

  useEffect(() => {
    return () => {
      currentRef.current?.dispose()
      currentRef.current = null
    }
  }, [])

  return texture
}

/** A soft white circular dot, drawn once and shared by every marker sprite (tinted per-class via
 * `SpriteMaterial.color`) -- one texture upload instead of one per marker. `THREE.Sprite` always
 * faces the camera on its own (no billboard math needed here), so this is the whole visual: a class-
 * coloured dot icon, matching UnrealEd's point-actor icon convention better than a solid cube. */
export function useMarkerTexture(): THREE.Texture | null {
  const [texture, setTexture] = useState<THREE.Texture | null>(null)
  const ref = useRef<THREE.Texture | null>(null)

  useEffect(() => {
    const size = 64
    const canvas = document.createElement('canvas')
    canvas.width = size
    canvas.height = size
    const ctx = canvas.getContext('2d')
    if (!ctx) return // e.g. a test/jsdom environment with no canvas 2D backend -- no marker texture
    const r = size / 2
    const gradient = ctx.createRadialGradient(r, r, 0, r, r, r)
    gradient.addColorStop(0, 'rgba(255,255,255,1)')
    gradient.addColorStop(0.7, 'rgba(255,255,255,1)')
    gradient.addColorStop(1, 'rgba(255,255,255,0)')
    ctx.fillStyle = gradient
    ctx.fillRect(0, 0, size, size)
    const tex = new THREE.CanvasTexture(canvas)
    tex.needsUpdate = true
    ref.current = tex
    setTexture(tex)
    return () => {
      tex.dispose()
      ref.current = null
    }
  }, [])

  return texture
}

/** The cull side + alpha-test + blend material state for a draw group, from its server-resolved
 * `masked`/`twoSided`/`blend` attrs alone (the map/lightMap are wired on separately). Single source
 * for the render-decision -> three.js mapping, unit-tested without a WebGL context.
 * - `twoSided` -> DoubleSide, else FrontSide (render.rs's backface cull; PF_TwoSided|PF_Portal exempt).
 * - `masked` -> alphaTest 0.5 against the texture's mask alpha (holes: fences, rotor).
 * - `translucent` -> half-opacity NormalBlending (see-through); `modulated` -> MultiplyBlending.
 *   Approximations of UE1's additive/modulate-2x, not pixel-exact (spec). */
export function resolveMaterialState(
  group: Pick<GeometryGroup, 'masked' | 'twoSided' | 'blend'>,
): Pick<
  THREE.MeshBasicMaterialParameters,
  'side' | 'alphaTest' | 'transparent' | 'blending' | 'opacity' | 'premultipliedAlpha'
> {
  const state: ReturnType<typeof resolveMaterialState> = {
    side: group.twoSided ? THREE.DoubleSide : THREE.FrontSide,
    alphaTest: group.masked ? 0.5 : 0,
  }
  if (group.blend === 'translucent') {
    state.transparent = true
    state.blending = THREE.NormalBlending
    state.opacity = 0.5
  } else if (group.blend === 'modulated') {
    state.transparent = true
    state.blending = THREE.MultiplyBlending
    // three.js requires this for MultiplyBlending, else it warns and blends wrong (WebGLState.js).
    state.premultipliedAlpha = true
  }
  return state
}

export interface BuiltGeometry {
  bufferGeometry: THREE.BufferGeometry
  materials: THREE.Material[]
  /** Same geometry, same per-group indexing as `materials` -- every lit group's lightmap dropped
   * (`lightMap`/`lightMapIntensity` omitted), so a mesh rendered with THIS array instead of
   * `materials` shows the flat KEY_LIGHT vertex-color shade only, no baked lighting. Lets a pane in
   * `'unlit'` mode actually differ from `'lit'` (main spec's 4-distinct-shading-modes requirement)
   * without rebuilding geometry per pane -- each pane's own mode picks which array its `<mesh>`
   * uses; the two arrays share one `BufferGeometry`/one set of `addGroup` indices. */
  unlitMaterials: THREE.Material[]
  triangleOwners: (string | null)[]
}

/** Builds the ONE `THREE.BufferGeometry` + per-group materials for a scene payload -- one draw
 * group per (texture, masked?, two_sided?, blend, lit?) tuple, each with its own material set from
 * the server-resolved attrs (cull side, alphaTest, blend). The base map tiles on `uv`; per-vertex
 * `color` carries the KEY_LIGHT flat shade (unlit) or white (lit); a lit group additionally samples
 * the shared lightmap texture on `uv1` (`base*color*lightMap`, the render.rs product). Untextured
 * groups (tex_index < 0) get a flat grey base. Disposes the PREVIOUS geometry/materials whenever a
 * fresh build (e.g. a live-reload) replaces them, and on unmount, so nothing leaks. */
export function useBuiltGeometry(
  scene: ScenePayload,
  atlas: AtlasPayload,
  lightmap: LightmapPayload | null,
  textures: { map: Map<number, THREE.Texture>; sprite: Map<number, THREE.Texture> },
  lightmapTexture: THREE.Texture | null,
): BuiltGeometry {
  const { bufferGeometry, materials, unlitMaterials, triangleOwners } = useMemo(() => {
    const built = buildGeometryData(scene.polys, atlas, lightmap)
    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', new THREE.BufferAttribute(built.positions, 3))
    geo.setAttribute('uv', new THREE.BufferAttribute(built.uvs, 2))
    geo.setAttribute('uv1', new THREE.BufferAttribute(built.uv1, 2))
    geo.setAttribute('color', new THREE.BufferAttribute(built.colors, 3))
    geo.clearGroups()
    const mats: THREE.Material[] = []
    const unlitMats: THREE.Material[] = []
    const matIndex = new Map<string, number>()
    const intensity = lightmap?.intensity ?? 1
    for (const group of built.groups) {
      if (group.count === 0) continue
      const lit = group.lit && lightmapTexture !== null
      const key = `${group.texIndex}:${group.masked ? 1 : 0}:${group.twoSided ? 1 : 0}:${group.blend}:${lit ? 1 : 0}`
      let index = matIndex.get(key)
      if (index === undefined) {
        const map = group.texIndex >= 0 ? (textures.map.get(group.texIndex) ?? null) : null
        const baseParams: THREE.MeshBasicMaterialParameters = {
          vertexColors: true,
          ...resolveMaterialState(group), // cull side + alphaTest + blend, from the resolved attrs
        }
        if (map) baseParams.map = map
        else baseParams.color = UNTEXTURED_GREY
        // `unlitMats` at the SAME index: same base params, but never the lightmap -- lets a pane
        // in 'unlit' mode pick this array and genuinely differ from 'lit' (both otherwise rendered
        // the exact same solid mesh, silently identical -- review finding).
        unlitMats.push(new THREE.MeshBasicMaterial({ ...baseParams }))
        const params = { ...baseParams }
        if (lit) {
          params.lightMap = lightmapTexture
          params.lightMapIntensity = intensity
        }
        index = mats.length
        mats.push(new THREE.MeshBasicMaterial(params))
        matIndex.set(key, index)
      }
      geo.addGroup(group.start, group.count, index)
    }
    geo.computeVertexNormals()
    return { bufferGeometry: geo, materials: mats, unlitMaterials: unlitMats, triangleOwners: built.triangleOwners }
  }, [scene, atlas, lightmap, textures, lightmapTexture])

  // Every live-reload replaces `bufferGeometry`/`materials`/`unlitMaterials` with fresh THREE
  // objects; without an explicit dispose the PREVIOUS ones (a full geometry buffer, its materials)
  // leak every cycle. The cleanup closes over the value from the render it belongs to, so it
  // always disposes the one being REPLACED, and disposes the final one on unmount too.
  useEffect(() => {
    return () => {
      bufferGeometry.dispose()
      materials.forEach((m) => m.dispose())
      unlitMaterials.forEach((m) => m.dispose())
    }
  }, [bufferGeometry, materials, unlitMaterials])

  return { bufferGeometry, materials, unlitMaterials, triangleOwners }
}

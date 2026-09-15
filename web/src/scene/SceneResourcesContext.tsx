// Shares ONE built scene (geometry/materials/textures/markers) across every pane -- Perspective and
// the three ortho panes (quad-layout Part 0, Task 2) -- instead of each pane rebuilding/re-uploading
// the same BufferGeometry to the GPU. `SceneResourcesProvider` calls sceneResources.ts's hooks
// exactly once per (scene, atlas, lightmap) triple; every pane reads the result via
// `useSceneResourcesContext()`.
import { createContext, useContext, useMemo } from 'react'
import type { ReactNode } from 'react'
import * as THREE from 'three'

import type { AtlasPayload, LightmapPayload, SceneActor, ScenePayload } from '../api'
import { actorsNeedingMarkers } from './markers'
import { useBuiltGeometry, useLightmapTexture, useMarkerTexture, useTextures } from './sceneResources'

export interface SceneResources {
  bufferGeometry: THREE.BufferGeometry
  materials: THREE.Material[]
  // Same geometry/group indexing as `materials`, lightmap dropped -- a pane picks this array
  // instead when its OWN shading mode is 'unlit', so 'unlit' genuinely differs from 'lit' (review
  // finding: both modes rendered the identical mesh since materials were built once, shared, with
  // no per-mode variant).
  unlitMaterials: THREE.Material[]
  triangleOwners: (string | null)[]
  textures: { map: Map<number, THREE.Texture>; sprite: Map<number, THREE.Texture> }
  markerTexture: THREE.Texture | null
  markerActors: SceneActor[]
  // The full actor list (Part 1, Task 6 addition, not in the plan's original interface list):
  // OrthoViewport's own props carry no `scene` (per the plan, just axis/selectedName/onSelectActor),
  // but click-to-select's AABB fallback (`pickActor`) and triangle-owner resolution
  // (`resolveHitActor`) both need the FULL actor set, not just `markerActors` -- so it rides the
  // context instead of a second prop every ortho pane would otherwise need threaded to it.
  actors: SceneActor[]
}

const SceneResourcesReactContext = createContext<SceneResources | null>(null)

export function SceneResourcesProvider({
  scene,
  atlas,
  lightmap,
  children,
}: {
  scene: ScenePayload
  atlas: AtlasPayload
  lightmap: LightmapPayload | null
  children: ReactNode
}) {
  const textures = useTextures(atlas)
  const lightmapTexture = useLightmapTexture(lightmap)
  const markerTexture = useMarkerTexture()
  const { bufferGeometry, materials, unlitMaterials, triangleOwners } = useBuiltGeometry(scene, atlas, lightmap, textures, lightmapTexture)

  // Point actors with no owned rendered poly (lights, triggers, patrol nodes, sounds, an unresolved
  // DT_Mesh) -- markers.ts's own filter, computed once here rather than per-pane.
  const markerActors = useMemo(() => {
    const ownedNames = new Set(triangleOwners.filter((n): n is string => n != null))
    return actorsNeedingMarkers(scene.actors, ownedNames)
  }, [scene, triangleOwners])

  const value = useMemo<SceneResources>(
    () => ({ bufferGeometry, materials, unlitMaterials, triangleOwners, textures, markerTexture, markerActors, actors: scene.actors }),
    [bufferGeometry, materials, unlitMaterials, triangleOwners, textures, markerTexture, markerActors, scene.actors],
  )

  return <SceneResourcesReactContext.Provider value={value}>{children}</SceneResourcesReactContext.Provider>
}

/** Reads the shared built-scene resources. Throws (naming the missing provider) when called outside
 * a `SceneResourcesProvider` -- a programmer error, not a recoverable render state. */
export function useSceneResourcesContext(): SceneResources {
  const ctx = useContext(SceneResourcesReactContext)
  if (ctx === null) {
    throw new Error('useSceneResourcesContext() called outside a <SceneResourcesProvider>')
  }
  return ctx
}

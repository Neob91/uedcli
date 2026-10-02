// Split out of SceneResourcesContext.tsx (which also exports the SceneResourcesProvider
// COMPONENT) so this file exports only a hook -- Vite's react-refresh plugin can't Fast Refresh a
// file that mixes a component export with any other kind of export ("X export is incompatible"),
// which silently wedges a pane (a stale module graph crashes on the next re-render, e.g.
// "useSceneResourcesContext() called outside a <SceneResourcesProvider>") until a full page reload.
import { useContext } from 'react'

import type { SceneResources } from './sceneResourcesReactContext'
import { SceneResourcesReactContext } from './sceneResourcesReactContext'

/** Reads the shared built-scene resources. Throws (naming the missing provider) when called outside
 * a `SceneResourcesProvider` -- a programmer error, not a recoverable render state. */
export function useSceneResourcesContext(): SceneResources {
  const ctx = useContext(SceneResourcesReactContext)
  if (ctx === null) {
    throw new Error('useSceneResourcesContext() called outside a <SceneResourcesProvider>')
  }
  return ctx
}

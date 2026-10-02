// Point-actor directional-facing arrow gizmo (`AActor.bDirectional`) -- ports a mechanism this
// GUI never had: a 5-segment dart (a shaft + 4 fins) drawn along an actor's local +X (facing)
// axis, in `C_ActorArrow`. RE'd from our own `uned/UED22/Editor.dll`, no third-party source
// (GUI-PARITY.md "Directional arrow gizmo" -- read that section before touching this file).
//
// Everything about WHICH actors show an arrow, and where its 5 lines actually sit in world space,
// is resolved server-side (`uedcli/serve/scene.py`'s `_actor_directional_arrow`/
// `_directional_arrow_lines`) -- this component only draws `SceneActor.directional_arrow.lines`
// (already the actor's Location + Rotation baked in, the same `rotation.actor_matrix` convention
// every brush/mesh vertex already uses) and applies the ONE piece of client-side state the server
// can't know: whether the actor is currently selected.
//
// Real UED22 gates the whole block on `bDirectional` alone, then on `IsA(ACamera) ? (actor !=
// Viewport->Actor) : bSelected` -- never on ortho-vs-perspective (own-binary disassembly: no
// `RendMap`/`IsOrtho` test anywhere in the block), so this renders in EVERY pane, unconditionally
// (matching `BrushOutlines`' own always-world-space convention, not `RadiiOverlays`' toggle).
import { useEffect, useMemo } from 'react'
import * as THREE from 'three'

import type { SceneActor } from '../api'
import { toThreeColor } from './selectionColor'

// `uned/UED22/unrealtournament.ini` `[Editor.EditorEngine]` `C_ActorArrow=(R=163,G=0,B=0,A=0)` --
// the SAME member (`UEditorEngine+0x1f8`) RadiiOverlays.tsx already reads for the ortho collision
// shape and the light/sound radii, reused here rather than re-declared with a new literal.
const C_ACTOR_ARROW = toThreeColor([163, 0, 0])

export interface DirectionalArrowsProps {
  actors: SceneActor[]
  selectedNames: ReadonlySet<string>
}

export function DirectionalArrows({ actors, selectedNames }: DirectionalArrowsProps) {
  const visible = useMemo(
    () =>
      actors.filter((a) => {
        const arrow = a.directional_arrow
        if (arrow == null) return false
        return !arrow.require_selection || selectedNames.has(a.name)
      }),
    [actors, selectedNames],
  )

  const geometry = useMemo(() => {
    const positions: number[] = []
    for (const actor of visible) positions.push(...actor.directional_arrow!.lines)
    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3))
    return geo
  }, [visible])
  useEffect(() => () => geometry.dispose(), [geometry])

  if (visible.length === 0) return null
  return (
    <lineSegments geometry={geometry}>
      <lineBasicMaterial color={C_ACTOR_ARROW} depthTest={false} />
    </lineSegments>
  )
}

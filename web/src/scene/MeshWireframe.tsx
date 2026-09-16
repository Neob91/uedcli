// Mesh-actor wireframe overlay (GUI.md "Shading modes"): a mesh actor's own triangle-edge
// wireframe, drawn only in wireframe mode -- real UnrealEd renders a mesh as wireframe there too,
// matching its brush convention (`BrushOutlines.tsx`), never solid or hidden. Shared by Viewport3D
// and OrthoViewport so both panes draw the identical geometry
// (`SceneResourcesContext.tsx`'s `meshWireframeGeometry`).
//
// Plain, uncoloured lines: unlike a brush, a mesh actor carries no CSG classification to colour its
// wireframe by -- no citable UnrealEd evidence pins an exact colour here (a judgment call, same as
// this codebase's other unpinned tuning values), so this uses plain white, the classic UE1
// wireframe look.
import * as THREE from 'three'

const MESH_WIREFRAME_COLOR = 0xffffff

export function MeshWireframe({ geometry }: { geometry: THREE.BufferGeometry }) {
  return (
    <lineSegments geometry={geometry}>
      <lineBasicMaterial color={MESH_WIREFRAME_COLOR} />
    </lineSegments>
  )
}

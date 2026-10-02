+++
priority = "p2"
kind = "debug"
summary = "Every THREE.Sprite icon draws horizontally mirrored, because the camera rigs mirror the projection matrix."
+++

# GUI actor sprites render mirrored

All four camera rigs (`Viewport3D.tsx`'s `applyCameraPose`, `OrthoViewport.tsx`'s
`applyOrthoCameraPose`) negate `projectionMatrix.elements[0]` to put the left-handed world's
`right` on screen-right. three.js's sprite vertex shader
(`three/src/renderers/shaders/ShaderLib/sprite.glsl.js`) builds the billboard quad in CAMERA space
and then projects it:

```glsl
vec4 mvPosition = modelViewMatrix[ 3 ];
...
mvPosition.xy += rotatedPosition;
gl_Position = projectionMatrix * mvPosition;
```

so the NDC-x negation flips the sprite's own image left-to-right. Affects every `<sprite>` in the
app: the real class icons (`OrthoViewport.tsx`/`Viewport3D.tsx`, `SceneActor.sprite`), the grey
fallback marker, and `SelectionMarkers.tsx`'s pivot crosshair and vertex dots. The marker glyphs are
symmetric so only the real class icons read wrong, but they read wrong in every pane.

Picking is unaffected: `Sprite.raycast` does its own world-space quad intersection and never touches
`projectionMatrix`, and the quad itself is symmetric.

Found while reviewing the mirror technique (`fcfb9486`); not introduced by it in isolation — it is
the same class of breakage as `geometry.ts`'s `REVERSE_FAN` and `camera.ts`'s yaw/A-D signs: a
camera-side mirror is invisible to everything three.js does downstream.

Two ways out, worth deciding together rather than separately:

- **Local**: flip each sprite material's map UVs (`texture.repeat.x = -1; texture.offset.x = 1`),
  or the `center` handling. Cheap, but it is another per-consumer patch, and any new sprite added
  later has to remember it.
- **Structural**: move the one reflection off the camera and onto the scene graph — wrap all world
  content in a `<group scale={[1, -1, 1]}>` and pose the cameras in that mirrored space. three.js
  compensates for an object-side reflection on its own (`WebGLRenderer` flips `frontFace` from
  `object.matrixWorld.determinant() < 0`, and the sprite shader reads `length(modelMatrix[0].xyz)`,
  sign-free), so sprites and winding both become correct with no per-consumer constant. Costs a
  coordinate seam at the group boundary (camera pose, the ray-vs-AABB `pickActor` fallback, the
  ortho cursor readout).

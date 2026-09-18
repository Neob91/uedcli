+++
priority = "p?"
kind = "investigate"
summary = "static-mesh actors should render as wireframe in wireframe/2D modes"
+++

# static-mesh actors should render as wireframe in wireframe/2D modes

Owner finding (live GUI review): in wireframe mode and the 2D ortho panes, a static-mesh actor
should show its actual mesh wireframe (triangle edges), not a full shaded 3D mesh and not a plain
dot/sprite marker. Today (`web/src/scene/Viewport3D.tsx`) a non-brush point actor always draws as
a sprite billboard (a resolved `DT_Sprite` icon, or the generic grey dot) in every mode, including
wireframe — there is no per-actor mesh geometry or wireframe-edge rendering path at all for
StaticMesh actors specifically.

**Before implementing:** check how UED22 actually renders a StaticMesh actor in a wireframe
viewport — does it draw the mesh's real triangle edges (an actual wireframe of the imported mesh
geometry), or a simplified proxy (e.g. its bounding box)? `dev/docs/unrealed/rendering.md` doesn't
currently cover this. This needs either a live UED22 probe or disassembly evidence before picking
an implementation — do not guess at the convention.

Also check whether `SceneActor`/the `/scene` payload (`uedcli/serve/scene.py`) carries anything a
mesh-wireframe render could use today (a mesh reference, or just class/location/rotation/bbox) —
if the payload has no mesh geometry at all, this may need a new backend field, which is a larger
scope than a frontend-only fix.

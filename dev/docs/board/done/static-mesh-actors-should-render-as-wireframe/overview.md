+++
priority = "p?"
kind = "investigate"
summary = "static-mesh actors should render as wireframe in wireframe/2D modes"
+++

# static-mesh actors should render as wireframe in wireframe/2D modes

Owner finding (live GUI review): in wireframe mode and the 2D ortho panes, a static-mesh actor
should show its actual mesh wireframe (triangle edges), not a full shaded 3D mesh and not a plain
dot/sprite marker.

**Resolved 2026-09-18 — RE confirms the convention, and the implementation already exists.**

By the time this item was investigated, `web/src/scene/Viewport3D.tsx`/`OrthoViewport.tsx` already
drew a mesh actor's real per-triangle wireframe in wireframe mode (commit `279fb903`, landed
2026-09-16 on this branch, before this investigation started — the premise above, "no per-actor mesh
geometry or wireframe-edge rendering path at all," was accurate only for an earlier state of the
code and had already been overtaken). What was still missing was RE evidence that this is actually
what UED22 does (it was previously described only in a code comment, uncited) and, separately, that
the `(.2,.8,.1)`/`(.6,.4,.1)` selected/unselected wire colors it uses were sourced from a third-party
UE1 tree now banned as GUI-PARITY evidence (owner ruling 2026-09-18).

Disassembled `render.dll` (`pefile`+`capstone`, `dev/docs/spikes/bspspike/pe.py`) — our own
`uned/UED22/render.dll`, no third-party source. `URender::DrawMesh` (RVA `0xff00`) is a thin
dispatcher into `URender::DrawLodMesh` (RVA `0xd050`), which — gated on the viewport being in Wire
(RendMap 1) or one of the three Ortho modes (13/14/15) — walks the mesh's LOD-aware face list and
issues real `RenDev->DrawLine`-shaped calls per face edge, colored by `AActor.bSelected` with
exactly the two vectors this codebase already hardcodes (`0x10035600`=`(.2,.8,.1)`,
`0x100355f0`=`(.6,.4,.1)`, read directly by the FPlane construction at that branch). **Confirms:
UED22 draws a StaticMesh actor's real triangle-edge wireframe (not a bounding box, not a
sprite/icon) in Wire/Ortho modes** — exactly this codebase's already-implemented convention. One
open, honestly-flagged nuance (not chased further, host docker couldn't mount a live UED22 for this
session): the per-face edge loop appears to draw only 2 of a triangle's 3 edges plus one degenerate
zero-length line, relying on adjacent faces to cover the third edge on a closed mesh — unconfirmed
against a live render for a boundary/silhouette case.

Full trace, RVAs, and the caveat: `GUI-PARITY.md` "Mesh-actor wireframe rendering — real triangle
edges, own-binary confirmed" (2026-09-18).

No further implementation needed. Backend note: `uedcli/preview_native.py`'s
`resolve_mesh_actor_polys`/`resolve_mesh_scene_polys` (commit `c0a79460`, "Option A") already supply
exactly the world-space triangle data `MeshWireframe.tsx` consumes, independent of CSG/build state —
no backend gap here.

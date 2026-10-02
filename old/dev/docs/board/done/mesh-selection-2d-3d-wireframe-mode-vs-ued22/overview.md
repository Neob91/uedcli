+++
priority = "p2"
kind = "investigate"
summary = "how does mesh-actor selection work in UED22's 2D and 3D wireframe modes -- our GUI may differ"
+++

# Mesh selection in 2D/3D wireframe mode vs UED22

DONE 2026-09-18. The owner's hunch reproduced: a real divergence, found and fixed.

**Finding (✅ binary-confirmed, `render.dll`/`Engine.dll` disassembly, our own `uned/UED22/`, no
third-party source):** in Wire/Ortho render modes, UED22's `DrawActorSprite` pushes ONE hit-proxy
(`HActor`) covering an actor's entire draw, and `DrawLodMesh`'s Wire/Ortho branch paints only its
wireframe EDGE lines (no filled interior) -- and the click hit-test itself (`ExecuteHits`) is a
literal per-pixel buffer scan. So UED22 can only select a mesh actor there by a click on/near an
actual drawn edge, never by clicking anywhere inside its open silhouette. Full trace: `GUI-PARITY.md`
"Mesh-actor wireframe SELECTION — edges only, never the filled interior".

This codebase's `meshPickGeometry` (a filled, solid-triangle raycast target) was wired into
`tapSelect.ts` unconditionally, including wireframe mode -- letting an interior click wrongly select
a mesh actor there.

**Fixed**: a new `buildEdgePickData` (`geometry.ts`) builds a raycastable edge-only `LineSegments`
geometry with per-edge owner data (`meshEdgePickGeometry`); `tapSelect.ts` picks a mesh actor by
that in wireframe mode and by the existing filled geometry everywhere else, and the AABB fallback's
existing wireframe-mode brush exclusion is extended to mesh actors too. Touched:
`web/src/scene/{geometry,selection,tapSelect,SceneResourcesContext,sceneResourcesReactContext,
Viewport3D,OrthoViewport}.ts(x)`. New unit tests in `geometry.test.ts`/`selection.test.ts`; full
frontend suite green (366 tests), `tsc -b` clean (4 pre-existing, unrelated errors only).

**Not live-verified**: a live UED22 capture and a live-browser (headless Chromium) pixel A/B were
both attempted and both blocked by real host constraints this session (rootless dockerd cannot mount
the worktree, then host disk 100% full; Chromium missing 17 shared libraries, no root) -- not skipped
for convenience. The attempted live-UED22 harness, `harness-meshsel-probe.py`, is committed alongside
this file for a future session whose docker daemon/host disk can run it.

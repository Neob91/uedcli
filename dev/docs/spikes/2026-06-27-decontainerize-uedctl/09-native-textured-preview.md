# Spike 9 — native textured preview feasibility (remove the editor `level preview` role)

**Status: RESOLVED (data pipeline proven). Every input a textured renderer needs is
natively available, no editor — only a rasterizer remains (standard implementation).**
Harness: [`harness/native_render_data.py`](harness/native_render_data.py).

## Question

`level preview --shaded` (planned) and the editor's render are the remaining editor
*display* role. With native texture decode (Spike 1) and native Model read (the completed
`Model` serial decode), can we render a textured view offline?

## Answer: the render data pipeline is fully native

For a real map's built `Model`, every surface's render inputs resolve natively:
- **Geometry** — Surfs + Nodes + Verts + Points from the native Model read (12/12 maps).
- **Texture** — each `FBspSurf.texture_ref` resolves to `package.name` via the `.dx`
  import table (Spike 4), and that texture decodes natively from the install (Spike 1).
- **UV** — `FBspSurf` carries `pBase` (Points index) + `TextureU`/`TextureV` (Vectors
  indices); surface UV = `((P − Points[pBase])·TextureU, ·TextureV)`.

Coverage (case-insensitive package lookup, like `dxpkg`):

| Map | surfs | distinct ext. textures | natively decoded | UV vectors valid |
|---|---|---|---|---|
| `00_Intro.dx` | 4573 | 138 | **137/138** | 200/200 |
| `01_NYC_UNATCOHQ.dx` | 3570 | 119 | **119/119** | 200/200 |
| `02_NYC_Bar.dx` | 953 | 35 | **34/35** | 200/200 |

The residual 0–1 per map are **myLevel/embedded** textures (local exports in the `.dx`
itself) — also natively decodable from the map's own export table (Spike 1 decodes any
package), just skipped by this external-ref probe.

## Actual renderer built — it renders real maps

`harness/native_render.py` does it end-to-end: parse the level `Model`, resolve+decode
each surf texture natively, project top-down ortho, triangulate each node polygon, and
rasterize with affine UV + a z-buffer. Output (pure-stdlib PNG, no editor/engine):

| Map | render | node-polys drawn | textures | time |
|---|---|---|---|---|
| `02_NYC_Bar.dx` | 900×606 | 1428 (0 skipped) | 34/35 | 0.7 s |
| `01_NYC_UNATCOHQ.dx` | 1400×470 | 5174 (0 skipped) | 119/119 | 1.1 s |

The Bar render is a clean, recognizable textured floorplan (tiled floor textures, room
layout) — confirming geometry, texture decode, and UV mapping all compose correctly with
zero editor. (Aesthetics like bbox framing / perspective vs top-down are renderer polish,
not feasibility.) This upgrades `level preview` from wireframe (`preview.py`) to a native
textured render and removes the editor's display role from the loop. Sample output lives
under `_scratch/shots/` (gitignored).

## Net
This is the last editor *role* (after geometry-build/D2 and lighting) shown to be natively
replaceable at the data level. Combined with the rest of the series, **no editor capability
the authoring/preview loop uses is fundamentally editor-bound except the CSG build (D2) and
the lighting bake** — both already scoped. (A textured preview can even render *unlit*
fullbright like the editor's PlainTex mode, so it doesn't depend on the lighting bake.)

# Editor GUI & console reference  [ENGINE]

UnrealEd 2.x GUI/console reference: keyboard shortcuts, brush colours, 2D/3D
navigation, the browsers, and prefab `.T3D` import/export. Engine-generic:
applies to UnrealEd 2.x for Unreal/UT/Deus Ex alike.

> uedcli drives verbs, not this GUI. It authors the git-tracked T3D trunk with
> composing verbs (`brush build … | actor add -`, `brush poly set`,
> `actor prop set`, `mover key …`) and touches the editor only to
> `level materialize` / `preview`. This page documents the GUI and the headless
> console verbs for a GUI-aware reader. Headless console driving:
> [`../../commands.md`](../../commands.md); editor traps:
> [`../../quirks.md`](../../quirks.md); render modes:
> [`../../rendering.md`](../../rendering.md).

> **Siblings.** [`dx-classes.md`](dx-classes.md) · [`dx-npcs.md`](dx-npcs.md) ·
> [`dx-conversations-computers.md`](dx-conversations-computers.md) ·
> [`asset-pipeline.md`](asset-pipeline.md). Full compiled reference:
> [`README.md`](README.md).

Markers: `[ENGINE]` throughout. 📖 = tutorial corpus; 🔬 = live-probed.

---

## 1. Function & modifier keys  [ENGINE] 📖

| Key | Action |
|---|---|
| **F1** | help |
| **F4** | actor properties |
| **F5** | surface properties (texture/flags/alignment) |
| **F6** | level properties (Audio/Song, etc.) |
| **F7** | compile scripts |
| **F8** | Rebuild (geometry / BSP / lighting / paths dialog) |
| **B** / **H** | toggle brush / actor visibility |
| **P** | realtime preview / play-in-editor |
| **1 / 2 / 3** | camera movement speed |

**Editing modifiers:**
- **Ctrl-Z** Undo · **Ctrl-Y** Redo. 🔬 (Ctrl-R is *Replace With Selected Class*, not Redo.)
- **Shift-A / Shift-S / Ctrl-I / Shift-D** = Add / Subtract / Intersect /
  Deintersect CSG ops on the builder brush. 🔬 decoded from the UED22
  `unrealed.exe` accelerator table. `Ctrl-A`/`Ctrl-S` are the standard Select All /
  Save, not CSG ops; the community "Ctrl-A/S/N/D" claim is wrong for this build.
- **Ctrl-B** Build All · **Ctrl-W** (or **Ctrl-D**) duplicate actor. 🔬
- **A + RMB** add actor here · **L + RMB** add light here · **Alt + RMB** =
  grab (pick up) a surface's texture into the active texture.
- **Copy Polygons → To Brush** clones a brush from selected polys.

**Surface-selection hotkeys** (faces selected in a 3D view):
**Shift-B / C / F / W / Y / T** = select brush / coplanar / floors / walls /
slanted / same-texture surfaces; **Ctrl-Shift-A** = all surfaces. 🔬
(**Shift-P** is *Matching PolyFlags* and **Shift-A** is CSG Add — neither is "all
surfaces"; select all actors is **Ctrl-A**.)

---

## 2. Brush & viewport colours  [ENGINE] 📖

Colour code in the 2D/3D viewports:

| Colour | Meaning |
|---|---|
| **Red** | the builder brush (the red cookie-cutter; never part of the level) |
| **Yellow** | subtracted space |
| **Blue** | added (solid) brush |
| **Pink** | semisolid brush |
| **Green** | nonsolid brush |
| **Purple** | mover (always drawn as wireframe) |
| **Yellow-green** | zone portal |

(Configurable defaults — View → Advanced Options. There is no "brown/orange"
subtracted tier; subtracted space is yellow.)

**Black 3D viewport after a rebuild** → *Mode → Textures*, or *Camera → Reset
All* (see [`../../rendering.md`](../../rendering.md) for the black-viewport traps).

---

## 3. 2D / 3D navigation  [ENGINE] 📖

- **2D viewports** (Top/Front/Side): LMB-drag = select/marquee; RMB-drag = pan;
  Ctrl-LMB = move selected brush; Ctrl-RMB = rotate; Ctrl-LMB+RMB = scale.
  **Brush clipping markers: Ctrl+RMB in a 2D view** (2 markers = a planar cut; a 3rd only
  tilts that single plane — still one planar cut, not a compound cut).
- **3D viewport:** LMB-drag = look/move; RMB-drag = look in place; both = strafe.
  Camera speed set by the **1 / 2 / 3** keys.
- **Grid snap** stays on; grid 16 for general work, drop lower for detail.
  (uedcli does not enforce snapping — it is guidance; see
  [`./csg-bsp.md`](./csg-bsp.md).)

---

## 4. Browsers  [ENGINE] 📖

Accessed from the top toolbar / *View → Browsers*:

- **Actor Class Browser** — the class tree; select a class to place. (uedcli
  equivalent: `class list` / `class show`.)
- **Texture Browser** — pick a package, then a **Group** to narrow the list
  (Group is browser-convenience only, except the reserved Group `Ladder`
  which makes a surface climbable — see [`dx-classes.md`](dx-classes.md) §1).
  New/edit procedural textures here (Fire/Water textures — set FX params before
  painting; left-drag paints, right-drag erases).
- **Sound Browser** / **Music Browser** — audio/song packages
  ([`asset-pipeline.md`](asset-pipeline.md)).
- **Group Browser** — the actor-`Group=` organizational dimension (distinct from
  uedcli's `folder` sidecar).
- **Mesh Viewer** — preview meshes/skins.

---

## 5. Prefabs — `.T3D` import/export  [ENGINE] 📖

- **Prefab load/save** = *File → Import / Export Level* as a **`.T3D`** file. This
  keeps actors and their texturing.
- Incompatible with **Brush → Export `.T3D`** (a single-brush export, a
  different format). Don't mix them.
- **Load all texture packages first** before importing a prefab, or its surfaces
  lose their textures.
- **`.u3d` brush Save/Load is broken** — Export/Import `.T3D` is the reliable
  path (import as "Solid Mesh" + "Keep Original Polygons Intact"). This
  independently validates uedcli's git-tracked-T3D-trunk design
  ([`README.md`](README.md)).

---

## 6. Useful console commands  [ENGINE] 🔬

Typed in the editor console (or issued headlessly by uedcli —
[`../../commands.md`](../../commands.md)):

- **Build/rebuild:** `MAP REBUILD`, `LIGHT APPLY` (bake lightmaps),
  `PATHS BUILD [HIGHOPT|LOWOPT]`.
- **Stats/diagnostics:** `STAT FPS`, `STAT ZONE` (visible vs rejected — confirms
  culling), `STAT GLOBAL` / `STAT POLYC` / `STAT MESH`, `MEMSTAT`, `OBJ LIST`. (There is no `STAT RENDER`.)
- **Surface:** `POLY TEXPAN` / `TEXSCALE` / `TEXALIGN` / `TEXINFO`.
- **Actor:** `ACTOR ALIGN` (snap to grid).
- **Caution:** never run **`texture cull`** with hidden brushes present — it
  wipes their textures.

Render-mode ("rmode") viewport views (wireframe / Zone-Portal optimization view /
lighting-only) are in [`../../rendering.md`](../../rendering.md); the optimization
workflow in [`./zones-performance.md`](./zones-performance.md).

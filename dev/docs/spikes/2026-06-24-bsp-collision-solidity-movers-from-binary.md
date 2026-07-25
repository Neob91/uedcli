# Collision, solidity, and movers — why you fall through / hit invisible walls (from the binaries)

**Date:** 2026-06-24
**Method:** static disassembly of the UED22 DLLs (the `capstone`+`pefile` harness in
`_scratch/bspspike/`; same setup as the companion spike
[`2026-06-24-bsp-csg-hole-mechanism-from-binary.md`](2026-06-24-bsp-csg-hole-mechanism-from-binary.md),
which covers *render* holes). This spike covers the **collision** side: why a floor that looks
solid lets you fall through, why empty space sometimes blocks you, and how
**solid / semisolid / nonsolid / mover** differ.
**Confidence:** decompiled facts (read from the compiled code) for everything with an address
below. A couple of higher-level "why the symptom happens" links are inference from the
mechanism and are marked as such.

> Read the companion render-hole spike first — it establishes that a "hole" is an `FPoly` the
> build discarded at `FPoly::Finalize`. This spike shows that **collision and rendering both come
> off the same built BSP**, so a discarded face is missing from *both* (you see through it *and*
> fall through it), and explains the cases where they diverge.

---

## 1. How world collision actually works (the key structural fact)

The world's collision lives on `UModel` (the level's BSP). The entry points (Engine.dll RVAs):

| Function | RVA | Role |
|---|---|---|
| `UModel::LineCheck` | `0x1ae4c0` | line/box trace vs the world BSP (movement, projectiles, traces) |
| `UModel::PointCheck` | `0x1aeba0` | point/box overlap vs the world BSP (standing, encroachment) |
| `UModel::FastLineCheck` | `0x1ada40` | boolean visibility/blocking line check |
| `UModel::PointRegion` | `0x1aee60` | which zone a point is in |
| (recursive line walker) | `0x1ae190` | the self-recursive BSP descent `LineCheck` drives |
| `ULevel::SingleLineCheck` / `MultiLineCheck` | `0x162400` / `0x161500` | the level-wide dispatch over world + actors |
| `FCollisionHash::ActorLineCheck` / `ActorPointCheck` | `0x125080` / `0x125380` | the **per-actor** collision path (movers, etc.) |

**The decisive finding:** the world-collision walkers compute pure plane geometry —
`FPlane::PlaneDot` (point-to-plane distance) and `TransformPlaneByOrtho` — and recurse the node
tree (`0x1ae190` calls itself). They **do not test `PolyFlags` solidity bits per node during the
walk** (a full scan of all six collision statics for `test/and` against `PF_NotSolid`/`PF_*`
masks found *zero* such tests). That means:

> **Solidity is baked into the BSP *structure* at build time, not re-decided at collision time.**
> Collision is "does the trace cross a node surface in the tree?" — so whether something blocks
> you is entirely determined by **which nodes exist in the tree and where their planes are**.

This single fact explains both bug classes:

- **Fall-through floor** = the floor's collision **node is missing** from the tree. Same root as
  a render hole (the face was discarded at `Finalize` — see companion spike), OR the floor was
  built as a non-cutting brush that never created a blocking node (semisolid/nonsolid, §3). The
  trace descends the tree and finds nothing to cross → you pass through. *(mechanism-confirmed;
  the "looks solid but isn't" link is the render/collision shared-BSP fact.)*
- **Invisible wall (blocked, nothing visible)** = a collision **node exists where you don't
  expect one**. Because collision tests the node's *plane*, not its rendered polygon area, a node
  whose surface renders as ~nothing (a degenerate sliver, or a `PF_Invisible` surface, §4) still
  partitions space and blocks the trace. Common origins: a leftover partition from a subtractive
  brush whose region wasn't fully re-cleared (CSG order, see companion spike §2), or a near-zero
  poly that survived as a node. *(mechanism-confirmed; the specific provenance of any one phantom
  is per-map.)*

## 2. The build decides solidity — `csgRebuild`'s two passes

`csgRebuild` (Editor.dll `0x4a650`) walks the level's brushes and applies each via the
`UEditorEngine::bspBrushCSG` **virtual** (called at `vtable+0x214`, args
`(brush, model, PolyFlags, CsgOper, …)`), then runs the build virtual `bspBuild`
(`vtable+0x1ec`) and a refresh pass (`vtable+0x264`). Confirmed from the disassembly: brushes are
processed **in actor order** (`ULevel::Brush()`/`IsStaticBrush`), and **solid** Add/Subtract
brushes are what cut the solid/empty structure; **semisolid / nonsolid / portal** brushes are
processed too but with modified flags (§3) so they *add surfaces without re-cutting solidity*.

The flag values are confirmed live in the code: `PF_NotSolid = 0x8`, `PF_Semisolid = 0x20`,
`PF_Portal = 0x04000000`.

## 3. Solid vs semisolid vs nonsolid vs mover — confirmed differences

### Solid (default)
Cuts the world BSP. Add fills solid, Subtract carves empty. The resulting node tree is what
collision walks, so **solid geometry collides reliably** — the volume itself is represented.
Walkable floors must be solid (`csg-and-bsp.md` already says so; this is the mechanism: only a
solid brush guarantees a blocking node structure under your feet).

### Semisolid (`PF_Semisolid`, 0x20)
Added to the BSP as **surfaces but without re-cutting the solid/empty structure**. So a semisolid
contributes blocking *planes* where its faces are, but doesn't define a solid *volume*. That is
exactly why `csg-and-bsp.md` calls semisolids **"unreliable underfoot"**: you collide with the
face, but the space behind/around it isn't solid, so edge cases (corners, grazing angles, overlap
with other semis/nonsolids) leak. Mechanism-level: collision is structural (§1), and a semisolid
only adds a thin surface node, not a closed solid region.

### Nonsolid (`PF_NotSolid`, 0x8)
No collision node contribution → the collision walk never finds it → **you pass through it
entirely**. Decorative/volume-marker only. A nonsolid used as a floor → guaranteed fall-through.

### Portals (`PF_Portal`, 0x04000000) — the semisolid+portal trap, binary-confirmed
`csgRebuild` special-cases portals at `0x4a800`–`0x4a821`:
```
eax = brush->PolyFlags                 ; [ecx+0x260]
test al, 0x20                          ; PF_Semisolid?
   cmp byte [ecx+0x20c], 1             ;   && CsgOper == CSG_Add?
   test eax, 0x4000000                 ;   && !PF_Portal  → handle as plain semisolid (skip)
test eax, 0x4000000                    ; PF_Portal?
   and eax, 0xffffffdf                 ;   clear PF_Semisolid  (~0x20)
   or  eax, 8                          ;   set   PF_NotSolid
   mov [ecx+0x260], eax                ;   write back, THEN bspBrushCSG with these flags
```
So **a portal brush is forced to `PF_NotSolid` (and any `PF_Semisolid` on it is stripped) before
CSG.** A zone portal therefore *never collides* — you can always walk through the portal sheet
itself. This is the mechanism behind the folklore "a brush touching a zone portal must be SOLID"
(`csg-and-bsp.md`): you can't get collision from the portal; you need a **separate solid brush**
for the wall, and making the portal semisolid to "fix" it does nothing because the engine erases
that bit. Combining semisolid + portal is the documented severe-BSP-problem case, and here is the
code doing the forced conversion.

### Movers (`AMover`) — a different collision system entirely
Movers do **not** participate in the world BSP. `AMover` (Engine.dll, e.g. ctor `0x170b40`,
`PostEditMove 0x170e50`, `SetBrushRaytraceKey 0x171520`, `SetWorldRaytraceKey 0x1716c0`) carries
its **own `UModel` brush** and registers it in the dynamic **collision hash**; collision against a
mover goes through `FCollisionHash::ActorLineCheck`/`ActorPointCheck` (`0x125080`/`0x125380`) →
`UModel::LineCheck` on the *mover's own* brush in actor-relative space — not the world tree. Consequences:

- A mover **never causes world BSP holes** (it's not in the world CSG), so the "fall-through /
  invisible wall" failure modes above don't originate from movers.
- A mover's collision is **its own brush's geometry**, transformed by the mover's position each
  frame. A malformed mover brush (non-convex, open, off-grid) collides wrongly *in isolation* —
  independent of the world build. Its pivot (`PrePivot`) defines the rotation arc (see
  `quirks.md` "Pivots").
- Because it's dynamic, a mover's collision is keyed/rehashed on move (`Set*RaytraceKey`), so it
  blocks correctly even while animating.

## 4. Where collision and rendering diverge (the genuinely confusing cases)

They share the BSP, but a *surface* carries `PolyFlags` that the renderer and the collision build
treat differently — so the two can disagree on purpose, and that "on purpose" is what reads as a
bug to a mapper:

| Surface flag | Renders? | Collides? | Symptom if misapplied |
|---|---|---|---|
| (normal solid) | yes | yes | — |
| `PF_Invisible` (0x1) | **no** | yes | "invisible wall" — intended, but surprising |
| `PF_NotSolid` (0x8) | yes | **no** | "fall through a wall you can see" |
| `PF_TwoSided` (0x100) | both sides | one-sided plane | grazing/back-face leaks |
| `PF_Portal` (0x04000000) | (special) | **no** (forced, §3) | walk through a portal opening |

Plus the structural divergence from §1: a **degenerate/sliver node** can block (collision uses
its plane) while rendering ~nothing → invisible wall; and a **dropped face** removes both, but an
*adjacent* surviving face can make the gap look "covered" → fall-through where it looks solid.

## 5. The editor's own validator — `bspValidateBrush`

`bspValidateBrush` (Editor.dll `0x37290`) is the engine's brush-sanity check. It calls
`UModel::BuildBound` and logs **`"BspValidateBrush linked %i of %i polys"`** — it attempts to
**link every poly's edges to its neighbours** (a watertight convex/closed solid has every edge
shared by exactly two faces). `linked < total` ⇒ the brush is **not watertight** (an open edge,
a T-junction, or a self-intersection) ⇒ a hole/leak/CSG-crash source. This is a ready-made
ground-truth signal a detection tool can capture from the live editor (§ in the spec).

## 6. Implications for a detection tool (feeds the `level doctor` spec)

The mechanisms above are *predictable from the authored model* for the common cases, and
*confirmable live* for the rest. The companion spec
`specs/2026-06-24-uedctl-bsp-doctor-design.md` (landed; spec deleted, see `decisions.md` 2026-06-24)
turns this into a command. The load-bearing detection inputs this spike establishes:

- **Dropped-face prediction (fall-through + render hole):** replicate `Finalize`/`RemoveColinears`/
  `CalcNormal` predicates model-side (degenerate, <3 verts after dedup, zero-area at the 1e-8
  size² floor, coincident <1e-4, near-colinear).
- **Watertightness:** every brush edge shared by exactly two faces (mirror `bspValidateBrush`'s
  "linked X of Y").
- **Off-grid / 0.25-band T-junctions:** a vertex of one brush lying within `THRESH_SPLIT_POLY_WITH_PLANE`
  (0.25 uu) of another brush's face plane but not coincident with a vertex there → sliver/T-junction
  → both holes and phantom collision.
- **Solidity misuse:** nonsolid/semisolid used as a walkable floor (fall-through risk);
  `PF_Semisolid` + `PF_Portal` on one brush (engine strips it — definite problem); portal without
  a separate solid wall.
- **CSG-order:** additive brush before an overlapping subtract (erased); subtract overlapping
  nothing (no-op).
- **Live ground truth (`--deep`):** rebuild in an ephemeral editor, capture `FPoly::*` warnings
  and `BspValidateBrush linked X of Y` from `Editor.log`, and diff authored faces vs built
  `Surfs`.

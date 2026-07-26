# Recipe: glass  [ENGINE]

A window you can see through but not walk through. The mechanism: a **translucent 2-sided sheet** gives
you the visible glass, and because **sheets never block collision on their own**, a thin **Invisible
Collision Hull** placed around the sheet stops the player. 📖

## What you're building

1. A **sheet** across the window opening — translucent + 2-sided, with a glass texture (the visible
   glass).
2. A thin **Invisible Collision Hull** enclosing the sheet — a semisolid with all faces invisible — so
   the glass blocks movement.

## Editor procedure (the mechanism)

1. **Make the window opening** in the wall (subtract it, or leave a gap).
2. **Build a sheet** sized to the opening on the correct **vertical** axis (not floor/ceiling
   orientation — glass is a wall).
3. **Add Special → Transparent Window** with a glass texture selected, and check **2-Sided** so you see
   the glass from both rooms.
4. **Build a thin box** around the sheet (the sheet sits inside it — e.g. an 8-uu-thick slab matching the
   window).
5. **Add Special → Invisible Collision Hull** on that box, textured with something you'll never see (the
   hull's faces are invisible in-game). This is what actually blocks the player.
6. **Test** (press P): in-game the hull vanishes visually but the glass texture shows and the player
   can't pass.

**Tips:** the collision hull must **not touch surrounding walls or zone boundaries** — a hull abutting
geometry causes HOM. Keep it a clean thin box just around the glass.

## uedcli pipeline (what you run)

```
# 1. the visible glass: a translucent, 2-sided sheet across the opening (translucent set at build; sheets are 2-sided by default)
brush build sheet --plane xz --width 128 --height 96 --flag translucent --texture CoreTexGlass.OldeStanGlass_A --at 256,0,128 | actor add -

# 2. the collision: a thin semisolid box around the sheet; flag its faces invisible → an Invisible Collision Hull.
#    (cube has no --flag, so this is two steps: `actor add` prints the hull's name — substitute it below.)
brush build cube --csg add --solidity semisolid --width 128 --breadth 8 --height 96 --at 256,0,128 | actor add -   # prints e.g. Cube_ab12cd — thin along Y (the pane's normal)
brush poly find <hull-name> | brush poly set - --add-flag Invisible
```

- Prefer **Translucent** for clean glass (masks dark colours), **Modulated** for dirty/tinted glass
  (grey is neutral; darker darkens the backdrop, lighter brightens it) — see
  [../textures-and-surfaces.md](../textures-and-surfaces.md).
- For *breakable* glass, Deus Ex has a `BreakableGlass` mover instead of a static sheet — see
  [../../deusex/](../../deusex/).

## Glass in ONE brush: the intersect-composite window

The sheet-plus-hull recipe above makes glass as **separate actors**. But when the glass must be part
of a **single brush** — most importantly a **mover door with a window in it** (a mover *is* one brush,
so a separate glass actor can't ride it) — you build the whole thing as one welded brush with
`brush intersect`. This leans on the per-face-solidity fact in
[../geometry-and-bsp.md](../geometry-and-bsp.md#solidity-is-stored-per-face-not-per-brush).

**The construction (what and why):**

1. An **additive SOLID slab** — the door/wall panel.
2. A **subtracted opening** through it — the window hole (make it pierce the full thickness).
3. A **semisolid additive pane** filling that opening, textured glass + flagged **Translucent**.
   Semisolid — *not* solid — for two linked reasons: a solid pane's side faces would **merge** with
   the subtracted reveal walls, and translucency would then let you see straight **into** the panel's
   interior; a semisolid pane's coincident faces **don't merge**, so the pane sits flush in the
   opening with no ugly gap and reads as real glass. 📖
4. **`brush intersect`** the whole set into ONE brush. The weld keeps each surviving face's solidity,
   so you get a solid frame with semisolid + translucent glass faces in a single brush.

```
# build the three (or more) pieces into one T3D set, then weld:
{
  brush build cube --csg add       --width 128 --breadth 16 --height 224 --at 0,0,112 --texture CoreTexMetal.ClenGrayMetal_A
  brush build cube --csg subtract  --width 80  --breadth 32 --height 64  --at 0,0,136 --texture CoreTexMetal.ClenGrayMetal_A
  brush build cube --csg add --solidity semisolid --width 80 --breadth 16 --height 64 --at 0,0,136 --texture CoreTexGlass.OldeStanGlass_A
} > /tmp/door_set.t3d

# weld to ONE mover brush (hinge at the min corner); then make the glass faces translucent
brush intersect /tmp/door_set.t3d --mover-class DeusEx.DeusExMover --pivot min | actor add -   # prints e.g. DeusExMover_ab12cd
brush poly find DeusExMover_ab12cd --texture CoreTexGlass.OldeStanGlass_A | brush poly set - --add-flag Translucent
```

- The pieces feed `intersect` in **CSG order**: additive slab first (makes solid), subtracts next
  (carve), semisolid panes last (fill). For a **multi-pane** window, subtract several openings and add
  one semisolid pane per opening — the door material left between them is the mullion frame, for free.
- **Collision — the whole door blocks, glass included.** The frame is solid, and the **glass faces
  come out semisolid, which collides exactly like solid** (only a *nonsolid* face is walk-through). So
  a semisolid-paned mover door is simply a solid door with a see-through window — no extra collision
  work. This is why `--mover-class` keeps the source per-face solidity and **rejects `--solidity`**:
  there is nothing to override. ✅
- **`level doctor` reports the welded mover as not watertight** — e.g. `watertight … edge … shared by
  3 faces (non-manifold)`, one per coincident pane edge. That is a **false positive here**: the
  coincident semisolid pane faces are intentional, and a **mover never goes through world BSP**, so the
  manifold requirement doesn't apply to it. Judge it with `level preview --game`, not doctor. ✅
  *(live-verified 2026-07-25; a known `doctor` limitation — it should skip the watertight check for
  mover brushes.)*
- `--mover-class` makes the weld a base mover; author the swing/slide with `mover key rotate|move`
  (see [../movers.md](../movers.md)). For a static wall window, drop `--mover-class` and the same
  intersect gives you a one-brush framed window.

## Related

- [../actors.md](../actors.md) — why sheets don't block and how collision hulls work.
- [../textures-and-surfaces.md](../textures-and-surfaces.md) — Translucent vs Modulated, 2-Sided.

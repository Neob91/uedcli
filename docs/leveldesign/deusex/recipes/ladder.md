# Recipe: a ladder  [DX]

A ladder in Deus Ex is **not an actor and not a flag** — it is a **texture**. The engine treats any
surface textured with a texture whose **`Group` name is `Ladder`** as climbable. Apply such a texture
to a wall face and the player can climb it. That is the whole mechanism.

> **DX-SDK / community-documented:** Deus Ex's player-movement code treats any surface whose texture
> `Group` is `Ladder` as climbable. There is no ladder class, no
> `bClimbable` flag, no `Ladder` navigation setup required for the climb itself. Built-in ladder
> textures ship in `CoreTexMetal`: **`ladder_a`** (a flat ladder image — use on a plain flat wall) and
> **`LadrBrwnMetal`** (use on a flat face *in front of* rungs you modelled with 3D geometry). Any
> texture you add to a package under a `Group=Ladder` becomes a ladder too.

## Procedure

1. **Have a flat wall face** where the ladder goes, tall enough to climb and reaching the ledge/floor
   at the top. No special geometry is required — a normal solid wall surface is fine.
2. **Apply a `Ladder`-group texture to that face.** Use `CoreTexMetal.ladder_a` for a painted-on flat
   ladder, or `CoreTexMetal.LadrBrwnMetal` if you built actual protruding rungs and want the climb
   surface in front of them.
3. **Align the texture** so the rungs sit upright and tile cleanly (wall alignment).
4. **That's it** — rebuild/materialize and the surface is climbable in-game. No actor, no property,
   no path node for the climb itself.

## With uedctl

```bash
# Find the wall face(s) you want to make a ladder, then texture them.
# The brush name is positional; --facing picks the specific face — here the wall face pointing
# along +X into the room (use -X / +Y / -Y for a wall on another side).
brush poly find ShaftWall --facing +X | brush poly set - --texture CoreTexMetal.ladder_a

# For rungs you modelled in 3D, texture the flat climb face in front of them instead:
brush poly find LadderWell --facing +X | brush poly set - --texture CoreTexMetal.LadrBrwnMetal

# Align it upright and tiling on the wall:
brush poly find ShaftWall --facing +X | brush poly align - --wall
```

## Caveats and gotchas

- **The Group is what matters, not the texture name.** `ladder_a`/`LadrBrwnMetal` are just the
  built-ins that happen to live in the `Ladder` group. A custom texture works identically the moment
  its package group is `Ladder`.
- **The `Ladder` texture-group is unrelated to uedctl's `folder` and to the T3D `Group=` actor
  property** — three different "group" senses. This one is the texture-browser group baked into the
  package, and it is the *only* one with in-game behaviour.
- **The climb texture makes a surface climbable for the *player* only.** There is **no `Ladder`
  navigation node** in DX (the `Ladder` group is a texture mechanism, not a nav point), and DX's
  `ScriptedPawn` AI does not climb ladders via a nav node — don't expect to wire NPC ladder-climbing
  the way you'd place a `PathNode`.

## See also

- [`../classes.md`](../classes.md) — the ladder-is-a-texture note in the class catalog.
- [`../../general/`](../../general/) — texturing, surface alignment, and the DX `CoreTex*` palette.

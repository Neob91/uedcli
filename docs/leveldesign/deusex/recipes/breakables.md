# Recipe: breakable glass, walls, and crates  [DX]

Deus Ex lets the player shoot through windows, blast through weak walls, and smash crates for loot.
Three mechanisms:

- **BreakableGlass** — a thin translucent `DeusExMover` pane that shatters when hit.
- **BreakableWall** — a `DeusExMover` wall segment destroyable with the right tool.
- **Breakable crates** — `DeusExDecoration` containers that spill `contents` when broken.

Author the two movers like a [door](deusex-door.md): build the brush as a mover, texture it first,
place it in a hole you cut. They don't move, so they need no keyframes.

## A: breakable glass

### Procedure

1. Cut the window opening through the wall (subtract a hole connecting two spaces).
2. Build a thin pane — a 1-uu-thick brush filling the opening — as a `BreakableGlass` mover. Texture
   it with a glass texture from `CoreTexGlass`.
3. Flag every surface `Translucent`.
4. Position it in the opening. No keyframes.
5. Optionally back it with an invisible collision hull to block movement until broken (a bare sheet
   doesn't block on its own — see caveats).

### With uedcli

```bash
# 2-3. A thin BreakableGlass pane, glass-textured, translucent — built as a SHEET mover.
#      (The sheet generator carries the per-face `--flag`; the cube generator has no face-flag
#      option, so glass is a sheet: thin in X, spanning Y=64 x Z=96, in the yz plane.)
brush build sheet --plane yz --width 64 --height 96 \
  --mover-class DeusEx.BreakableGlass \
  --texture CoreTexGlass.OldeStanGlass_A --flag translucent \
  --at 320,0,80 | actor add -
```

## B: breakable wall

Same as a door, but a solid-looking wall segment.

### Procedure

1. Cut the hole in the wall where it will break through (connect two subtracted spaces). A jagged
   or slightly rotated opening reads better than a clean square.
2. Build the fill brush as a `BreakableWall` mover, textured to match (or nearly match) the
   surrounding wall — a small texture offset hints "this bit is different."
3. Set breaking difficulty. Two knobs gate it: `minDamageThreshold` (default 20) is the smallest
   single hit that registers at all; `doorStrength` (default 0.40) is a 0–1 durability pool each
   registering hit chips away (by `Damage×0.01`), breaking at ~0. A crowbar does only ~6 damage, so a
   stock `BreakableWall` can't be crowbarred at any `doorStrength` — to make it crowbar-weak, lower
   `minDamageThreshold` to ≤6 (same as `BreakableGlass`: threshold 3). Leave the defaults to demand a
   LAM/GEP.
4. Fit it into the opening on-grid so there are no gaps.

### With uedcli

```bash
brush build cube --width 8 --breadth 96 --height 96 \
  --mover-class DeusEx.BreakableWall \
  --texture CoreTexConcrete.DrtyGrayCemnt_A \
  --at 320,0,80 | actor add -
#   -> BreakableWall0

# 3. Crowbar-weak wall: lower minDamageThreshold below the crowbar's ~6 hit (bBreakable=True is the class default):
actor prop set BreakableWall0 minDamageThreshold=6
```

## C: breakable crates

Place a container decoration.

### Procedure

1. Place a crate. Pick a `CrateBreakable…` under `DeusExDecoration → Containers`. The medium
   breakables and their default loot:
   - `CrateBreakableMedCombat` → 10mm ammo
   - `CrateBreakableMedGeneral` → lockpick
   - `CrateBreakableMedMedical` → MedKit
2. Customise the loot (optional) — set `contents` to any `DeusExAmmo`/`DeusExPickup` class.
3. Add variety (optional) — fill `content2` and/or `content3`. When broken the pick is a weighted
   cascade: it starts with `contents`, then `content2` overrides it with ~30% chance, then `content3`
   likewise — so `contents` is the most common drop and each later slot ~30%. Keep it thematic: ammo
   in Combat crates, medkits in Medical, misc in General.

### With uedcli

```bash
# 1. Default crate — done.
actor build DeusEx.CrateBreakableMedGeneral --at 128,128,32 | actor add -

# 2-3. Custom + random contents.
actor build DeusEx.CrateBreakableMedCombat \
  --prop contents=DeusEx.Ammo10mm \
  --prop content2=DeusEx.AmmoSabot \
  --prop content3=DeusEx.WeaponCombatKnife \
  --at 192,128,32 | actor add -
```

## Properties reference

| Actor / property                                     | Meaning                                                                                        | Typical |
| ---------------------------------------------------- | ---------------------------------------------------------------------------------------------- | --- |
| `BreakableGlass`                                     | Thin translucent shatter pane (a `DeusExMover`)                                                | a `sheet` mover, face `translucent` |
| `BreakableWall.minDamageThreshold` / `.doorStrength` | min registering hit / resistance                                                               | default **20** / **0.40**; lower `minDamageThreshold` to ≤6 for a crowbar |
| `DeusExMover.bBreakable`                             | Can be destroyed at all                                                                        | `True` |
| `CrateBreakableMed{Combat,General,Medical}`          | Loot container                                                                                 | default loot per type |
| `contents` / `content2` / `content3`                 | Item class(es); multiple → weighted cascade (`contents` most likely; `content2`/`3` each ~30%) | a `DeusExAmmo`/`DeusExPickup` |

## Caveats and gotchas

- Texture the mover before it exists. `BreakableGlass`/`BreakableWall` are movers — pass
  `--texture` on `brush build` (and, on a `sheet`, `--flag` for the surface flags); you can't
  `brush poly set` them afterwards.
- A sheet/thin pane doesn't block on its own. To stop the player until the window breaks, add an
  invisible collision hull behind the pane (all-invisible-poly semisolid — see
  [`../../general/`](../../general/)).
- Put a crowbar near breakable crates to teach the affordance (see the DX design philosophy under
  [`../`](../)).
- Test with a nearby LAM/GEP to verify a high-strength breakable wall blows.

## See also

- [`deusex-door.md`](deusex-door.md) — the mover-authoring flow these reuse.
- [`../classes.md`](../classes.md) — the `DeusExDecoration` container family.
- [`../../general/`](../../general/) — translucency flags, collision hulls, and CSG holes.

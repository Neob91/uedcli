# Recipe: an NPC on patrol  [DX]

A patrolling guard is a **`ScriptedPawn`** with `Orders=Patrolling`, walking a chain of
**`PatrolPoint`** navigation actors. This recipe places one guard, routes it on a loop, and makes it
hostile to the player. The full NPC reference (roster, reactions, inventory, binding) is in
[`../npcs.md`](../npcs.md) — this is the concrete patrol procedure.

> **Pathnode-first, always.** NPCs move only along the level's compiled **path network**. If paths
> aren't built, the guard stands still forever and gives you **no error**. Build paths as the last
> step — and rebuild after any geometry change. `PatrolPoint`s are themselves navigation points, so a
> simple patrol can rely on them, but a guard that must also cross open floor needs `PathNode`s too.

## Procedure

1. **Lay the patrol route** — place `PatrolPoint` actors along the path you want walked, each within
   **line-of-sight and <700 uu** of the next (≤350 on stairs), all at the same height above the floor.
   The actor's yaw is the facing the NPC takes at that point.
2. **Chain them.** Give each `PatrolPoint` a `Tag`, and set its **`Nextpatrol`** (a `name`) to the `Tag`
   of the following point. To loop, point the last one's `Nextpatrol` back at the first's `Tag`. Two
   points is enough for a there-and-back beat. Set `PauseTime` (seconds) if the guard should halt at a
   point. (Note: `NextPatrolPoint` is a *runtime-resolved object* reference, **not** the editable field —
   the mapper-set one is `Nextpatrol`.)
3. **Place the guard** — any concrete `ScriptedPawn` leaf (e.g. `Soldier` or `MJ12Troop` from
   `HumanMilitary`) near the first patrol point.
4. **Order it to patrol** — `Orders=Patrolling`, `OrderTag` = the **first** patrol point's `Tag`.
5. **Set alliances** — to make it hostile to the player, add `"Player"` at `AllianceLevel=-1`,
   `bPermanent=True` in `InitialAlliances[0]`. (Levels: **−1 hostile, 0 neutral, +1 friendly**.)
6. **(Optional) inventory / binding** — `InitialInventory` for its weapon, `BindName` if story logic
   references it. Usually leave reactions/fears at the class defaults.
7. **Build paths and playtest.** Rebuild the path network (the `Paths Define` step), then run the map.

## With uedctl

```bash
# 1-2. A two-point patrol loop. Each point's Nextpatrol names the OTHER's Tag.
actor build Engine.PatrolPoint --prop Tag=warehouse_p1 --prop Nextpatrol=warehouse_p2 \
  --prop PauseTime=2 --at 256,0,40 --rotate 0,0,0 | actor add -
actor build Engine.PatrolPoint --prop Tag=warehouse_p2 --prop Nextpatrol=warehouse_p1 \
  --prop PauseTime=2 --at 256,512,40 --rotate 0,32768,0 | actor add -

# 3-6. Place the guard, order it patrolling from p1, make it hostile to the player.
actor build DeusEx.MJ12Troop \
  --prop Orders=Patrolling --prop OrderTag=warehouse_p1 \
  --prop InitialAlliances.0.AllianceName=Player \
  --prop InitialAlliances.0.AllianceLevel=-1 \
  --prop InitialAlliances.0.bPermanent=True \
  --prop BindName=mj12_patrol_a \
  --at 256,0,80 --rotate 0,0,0 | actor add -
```

> **Paths must be built in the editor** (`PATHS BUILD` / F8 → Paths Define). **`level materialize` does
> NOT currently run the paths pass** — so a materialized map has no reachspecs and the guard won't move
> until paths are built in the editor. (Known gap; uedctl has no standalone "define paths" verb yet.)
> Verify by playing that the guard walks its loop.

## Making an NPC hostile to *other* NPCs

`InitialAlliances` holds up to 8 relationships. Beyond `"Player"`, you can name any alliance:

```bash
# Greasels friendly to Grays, hostile to the "mj12" faction:
actor build DeusEx.Greasel \
  --prop InitialAlliances.0.AllianceName=Gray --prop InitialAlliances.0.AllianceLevel=1 --prop InitialAlliances.0.bPermanent=True \
  --prop InitialAlliances.1.AllianceName=mj12 --prop InitialAlliances.1.AllianceLevel=-1 --prop InitialAlliances.1.bPermanent=True \
  --at 512,512,64 | actor add -
```

Many classes ship with a default `Alliance` name (a Greasel's is `"Greasel"`, already friendly to
Karkians). Give an NPC a custom `Alliance` name if a trigger will flip its allegiance later (via an
`AllianceTrigger`).

## Properties reference

| Actor / property                     | Meaning |
| ------------------------------------ | --- |
| `PatrolPoint.Tag` / `.Nextpatrol`    | This point's name / the `Tag` of the next point (editable `name`; `NextPatrolPoint` is the runtime object ref) |
| `PatrolPoint.PauseTime`              | Seconds the NPC waits here |
| `ScriptedPawn.Orders` = `Patrolling` | Walk the patrol chain (a **state name**, not an enum) |
| `ScriptedPawn.OrderTag`              | The **first** `PatrolPoint`'s `Tag` |
| `InitialAlliances[i]`                | `(AllianceName, AllianceLevel −1..+1, bPermanent)`; player = `"Player"` |
| `BindName`                           | Spaces-free id that flags/conversations/triggers key off |
| `InitialInventory[i]`                | `(class, Count)` — the weapon/items it spawns with |

## Caveats and gotchas

- **No paths = no movement, silently.** The single most common patrol failure. Rebuild paths after
  every geometry change.
- **`OrderTag` points at the first patrol point**, not at the NPC itself.
- **Same-height navigation points.** All `PatrolPoint`s / `PathNode`s along a route should sit the same
  distance above the floor, or paths may fail to connect.
- **Place a concrete leaf**, never the abstract `ScriptedPawn`/`HumanMilitary` base.
- **`PatrolPoint` is `Engine.PatrolPoint`** (an `Engine.NavigationPoint` subclass), not
  `DeusEx.PatrolPoint` — build it with the `Engine.` package prefix.
- **Struct-array props use the dot form** — `InitialAlliances.0.AllianceName`, not the T3D
  `InitialAlliances(0).…` parenthesis form (the CLI rejects `KEY(N)`).
- **These UT knobs don't exist in DX** — don't set `SeekTag`, `HateTag`,
  `bFearDarkness`, `bCanClimb` (see [`../npcs.md`](../npcs.md) for the full absent list). (`Aggressiveness`
  is a UED22-package addition uedctl accepts but the game ignores — not truly absent; see the KB note.)

## See also

- [`../npcs.md`](../npcs.md) — the full `ScriptedPawn` reference (roster, reactions, inventory).
- [`../classes.md`](../classes.md) — navigation and gameplay-wiring actors.
- [`../../general/`](../../general/) — the path network and `PathNode` spacing rules.

# Recipe: a nanokey  [DX]

A `NanoKey` is a Deus Ex key item. It opens a locked **`DeusExMover`** door whose `KeyIDNeeded`
matches the key's `KeyID`. The key can sit in the world for the player to pick up, or be carried by an
NPC (dropped when they're killed or knocked out) via a `PickupDistributor`.

## A: a nanokey in the world

### Procedure

1. **Make the door need a key.** On the locked `DeusExMover` door, set `KeyIDNeeded` to a `name` and
   `bLocked=True` (a key on an unlocked door is pointless). See [`deusex-door.md`](deusex-door.md).
2. **Place a `NanoKey`** in the world. Set its `KeyID` to the *same* `name` as the door's
   `KeyIDNeeded`.
3. **Set its appearance** (optional) — `SkinColor` = `SC_Level1`…`SC_Level4` (it always shows as the
   blue Level-1 key in the editor, but renders correctly in-game).
4. **Give it a `Description`** — the text the player sees on pickup. **Set this**, or the player gets
   the placeholder "NO KEY DESCRIPTION - REPORT THIS AS A BUG!".

### With uedctl

```bash
# 1. Door requires the key.
actor prop set Door_Lab_Mover bIsDoor=True bLocked=True KeyIDNeeded=lab_key

# 2-4. The matching key in the world.
actor build DeusEx.NanoKey \
  --prop KeyID=lab_key \
  --prop SkinColor=SC_Level2 \
  --prop Description="Laboratory access key" \
  --at 640,128,40 | actor add -
```

## B: a nanokey carried by an NPC (PickupDistributor)

Instead of placing the key in the world, hand it to a specific NPC — the player must kill or stun them
to get it. A single **`PickupDistributor`** can distribute up to **8** nanokeys.

### Procedure

1. **Make the door need a key** exactly as in A (step 1).
2. **Give the target NPC a unique `Tag`.** The distributor identifies the carrier by
   `ScriptedPawnTag`, so if several NPCs share a `Tag`, retag the one who should hold the key.
3. **Place a `PickupDistributor`** anywhere (near the `DeusExLevelInfo`/`PlayerStart` is convenient).
4. **Fill in `NanoKeyData[0]`** — its `KeyID`, `Description` (as in A), plus
   `ScriptedPawnTag` = the carrier's `Tag`. (Its `SkinColor` field is **inert** — the shipped
   `PickupDistributor` code doesn't copy it to the distributed key; colour only works on a directly
   *placed* `NanoKey`.) Add more entries (`[1]`, `[2]`, …) for more keys/NPCs; add
   another distributor if you exceed 8.

### With uedctl

```bash
# 2. Ensure the carrier has a unique Tag.
actor prop set MJ12Troop3 Tag=guard_with_key

# 3-4. A distributor that gives that guard the lab key.
actor build DeusEx.PickupDistributor \
  --prop NanoKeyData.0.KeyID=lab_key \
  --prop NanoKeyData.0.Description="Laboratory access key" \
  --prop NanoKeyData.0.ScriptedPawnTag=guard_with_key \
  --at 0,0,40 | actor add -
```

## Properties reference

| Actor / property                                   | Meaning |
| -------------------------------------------------- | --- |
| `DeusExMover.KeyIDNeeded`                          | The `KeyID` (a `name`) that unlocks this door |
| `NanoKey.KeyID`                                    | Must equal the door's `KeyIDNeeded` |
| `NanoKey.SkinColor`                                | `SC_Level1`…`SC_Level4` in-game colour |
| `NanoKey.Description` (DeusExPickup)               | Pickup text — **always set it** |
| `PickupDistributor.NanoKeyData[i]`                 | A key given to an NPC: `KeyID`, `Description`, `ScriptedPawnTag` (its `SkinColor` is **inert** — not copied by the distributor) |
| `PickupDistributor.NanoKeyData[i].ScriptedPawnTag` | The `Tag` of the NPC who carries this key |

## Caveats and gotchas

- **The `KeyID` names must match** (case-insensitive FNames) — `KeyID` on the key ⇄ `KeyIDNeeded` on the door. A typo
  = an unopenable door.
- **`bLocked=True` is required** — a nanokey does nothing to an already-unlocked door.
- **Carrier `Tag` must be unique** — if the distributor's `ScriptedPawnTag` matches several pawns, the
  key placement is ambiguous. Retag the intended carrier.
- **Struct-array indexing** — use the **dot** form `NanoKeyData.0.KeyID` (index and subfield both
  dotted); the CLI rejects the T3D `NanoKeyData(0).KeyID` parenthesis form.

## See also

- [`deusex-door.md`](deusex-door.md) — the locked door the key opens.
- [`npc-patrol.md`](npc-patrol.md) — placing and tagging the NPC who carries it.
- [`../classes.md`](../classes.md) — the pickup/key catalog.

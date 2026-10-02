# Recipe: particle emitters  [DX]

Stock UnrealEngine 1 (and UT99) has no particle system; its "effects" are sprite/trail hacks. Deus Ex
adds a mapper-placeable particle family under `Actor → Effects`, built on `ParticleGenerator`, for
steam, dust, dripping water, electric arcs, and fire. These are point actors: place, set properties,
optionally gate on a trigger.

## The family

| Class                 | What it does |
| --------------------- | --- |
| `ParticleGenerator`   | The base emitter — steam, dust, smoke, gas. Tune rate/rise/lifespan/texture. |
| `WaterDrips`          | Ceiling drips — fall straight down under gravity (`bGravity`, on by default); rotation has no effect. |
| `ElectricityEmitter`  | A damaging electric arc; `bDirectional` aims it; carries its own light. |
| `Fire`                | A flame sprite plus an `LE_FireWaver` light. |
| `LaserEmitter`        | The laser beam visual (up to 2 reflections; freezes >960 uu from the player). The tripwire is `LaserTrigger`/`BeamTrigger`, which spawns one. |
| `ProjectileGenerator` | Periodically spawns a `ProjectileClass`. |
| `TrashGenerator`      | Wind-blown debris ("paper"/tumbleweeds). |

> Not emitters: `SmokeTrail` (code-spawned only) and `WaterFountain` (a drinkable `DeusExDecoration`).

## A: steam / dust / gas (`ParticleGenerator`)

### Procedure

1. Place a `ParticleGenerator` at the source (a vent, a broken pipe, a corner of dust).
2. Set the look — `particleTexture` (e.g. `Effects.Smoke.Gas_Poison_A`),
   `particleDrawScale`, `riseRate` (upward drift), `particleLifeSpan`, `frequency` /
   `numPerSpawn` / `checkTime` (how often/how many spawn).
3. Gate it (optional) — set `bTriggered=True` and `bInitiallyOn=False` so it only emits after
   something fires its `Event`, and give it a `Tag` for the trigger to target. `bInitiallyOn` defaults
   True, so with `bTriggered` alone the generator spews immediately and the first trigger turns it off.

### With uedcli

```bash
# Always-on steam from a vent:
actor build DeusEx.ParticleGenerator \
  --prop particleTexture=Effects.Smoke.SmokePuff1 \
  --prop riseRate=20 --prop frequency=1 --prop particleLifeSpan=4 \
  --prop particleDrawScale=0.1 \
  --at 0,0,16 | actor add -

# Poison gas that only starts when triggered (bInitiallyOn=False is REQUIRED, or it spews immediately):
actor build DeusEx.ParticleGenerator \
  --prop particleTexture=Effects.Smoke.Gas_Poison_A \
  --prop bTriggered=True --prop bInitiallyOn=False --prop Tag=vent_gas \
  --at 128,0,16 | actor add -
```

## B: water drips (`WaterDrips`)

### Procedure

1. Place a `WaterDrips` on the ceiling. Drips fall straight down under gravity — rotation has no effect
   (`ejectSpeed`=0), no arrow to aim.
2. Tune `frequency` / `particleTexture` as for the base generator.

### With uedcli

```bash
actor build DeusEx.WaterDrips --at 0,0,240 | actor add -   # falls by gravity (bGravity default on); no rotation needed
```

## C: electricity arc (`ElectricityEmitter`)

### Procedure

1. Place an `ElectricityEmitter` where the arc originates (a damaged panel, exposed wires).
2. Aim it — set `bDirectional=True` and rotate the actor so its arrow points along the arc. It damages
   the player and carries its own light, so no separate light is needed.
3. Pairs with a `Shocked` [pain zone](water-zone.md#b-pain--gas--hazard-zones).

### With uedcli

```bash
actor build DeusEx.ElectricityEmitter \
  --prop bDirectional=True \
  --at 0,0,64 --rotate 0,16384,0 | actor add -
```

## D: fire (`Fire`)

### Procedure

1. Place a `Fire` where the flame sits. It draws a flame sprite and adds its own `LE_FireWaver` light,
   so it self-illuminates.
2. Optionally add a coloured static light nearby for surrounding glow — a larger fire scene usually
   wants extra motivated lighting.

### With uedcli

```bash
actor build DeusEx.Fire --at 0,0,24 | actor add -
```

## Properties reference

| Property (`ParticleGenerator`)    | Meaning                                                   | Default |
| --------------------------------- | --------------------------------------------------------- | --- |
| `particleTexture`                 | The sprite each particle draws                            | — |
| `frequency`                       | Spawn frequency                                           | 1 |
| `checkTime`                       | Seconds between spawn checks                              | 0.1 |
| `numPerSpawn`                     | Particles per spawn                                       | — |
| `riseRate`                        | Upward drift speed                                        | 10 |
| `particleLifeSpan`                | Seconds a particle lives                                  | 4 |
| `particleDrawScale`               | Particle size                                             | 0.1 |
| `bTriggered`                      | Emit only after a Trigger fires the `Event` (DX addition) | False |
| `ElectricityEmitter.bDirectional` | Arc aims along the actor arrow; damages; own light        | — |
| `WaterDrips.bGravity`             | Drips fall                                                | — |

## Caveats and gotchas

- Deus-Ex-only: `ParticleGenerator`/`Fire`/etc. live in `DeusEx.u`, not stock UT99 maps.
- `WaterDrips` fall straight down by gravity — `ejectSpeed`=0, so rotation has no effect; no arrow to aim.
- `ElectricityEmitter` and `Fire` bring their own light — don't add a light for the emitter, though
  you may add ambient light for the scene.
- `particleTexture` names a real texture; DX ones live in the `Effects.Smoke` group (e.g.
  `Effects.Smoke.SmokePuff1`, `Effects.Smoke.Gas_Poison_A`, `Effects.Smoke.Gas_Tear_A`). Browse the
  `Effects` package for the exact `Package.Group.Name`. `--prop` does not validate the ref at author
  time (unlike `brush build --texture`), so a wrong name fails silently in-game — copy the exact name
  from the package.
- `LaserEmitter` freezes past ~960 uu from the player — keep tripwires close to where the player walks.

## See also

- [`water-zone.md`](water-zone.md) — hazard zones these emitters visually dress.
- [`../classes.md`](../classes.md) — the DX effects/emitter family in the catalog.
- [`../../general/`](../../general/) — engine lighting (the `LE_*` light effects `Fire` uses).

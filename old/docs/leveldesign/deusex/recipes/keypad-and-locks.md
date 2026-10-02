# Recipe: keypads, control panels, and locks  [DX]

Deus Ex gates areas behind hackable devices: keypads you enter a code into (or hack with
multitools), and control panels that disable laser fields. All share the `HackableDevices`
base (`bHackable`, `hackStrength`), fire an `Event` when satisfied, and target another actor by its
`Tag`.

## A: keypad → locked door

A keypad opens or unlocks whatever its `Event` targets when the player enters `validCode` or hacks it.

### Procedure

1. Make the door lockable. Engine movers have no lock, so the target must be a
   `DeusExMover` with `bIsDoor=True` and `bLocked=True` (see [`deusex-door.md`](deusex-door.md));
   give it a `Tag` (e.g. `Door_Lab`).
2. Place the keypad on a wall near the door, ~60–80 uu above the floor (4–5 grid squares). Pick
   `Keypad1`, `Keypad2`, or `Keypad3` — identical behaviour, different look.
3. Set `validCode` to a 4–5 digit string. `bToggleLock` (default `True`): `True` toggles the
   target's lock without opening it; `False` fires the keypad's `Event`, opening the wired door via
   its trigger state — that path ignores `bLocked`, so the door opens without clearing its lock. The
   example uses `False`.
4. Set hackability: `bHackable=True` with `hackStrength` (0.20 = 20%, two multitools for an
   untrained player); `bHackable=False` forces code-only.
5. Wire it to the door: set the keypad's `Event` to the door's `Tag`. The editor shows this as a
   red line from keypad to door.

### With uedcli

```bash
# 1. A locked DeusExMover door with a Tag (see deusex-door.md for the full door).
actor prop set Door_Lab_Mover bIsDoor=True bLocked=True Tag=Door_Lab

# 2-4. Place a keypad, code + hackability.
actor build DeusEx.Keypad1 \
  --prop validCode=4021 --prop bToggleLock=False \
  --prop bHackable=True --prop hackStrength=0.20 \
  --prop Event=Door_Lab \
  --at 480,64,72 --rotate 0,0,0 | actor add -
```

## B: control panel → laser field

A `ControlPanel` (a hackable device with no code, only hacking) disables a set of laser triggers when
bypassed, by firing their `UnTriggerEvent`.

### Procedure

1. Place the laser triggers. Use `LaserTrigger` for the red beams — breaking one triggers the
   alarm by default. Four from alternating directions reads well. Give them all the same
   `Tag` (e.g. `LaserField1`). The red arrow shows each beam's direction.
2. Place a `ControlPanel` on a nearby wall.
3. Wire the panel to the lasers: set `UnTriggerEvent[0]` to the lasers' `Tag`. Hacking the panel
   un-triggers (switches off) the beams. Set `hackStrength` for difficulty.

### With uedcli

```bash
# 1. Lasers sharing one Tag (place several, alternating facing via --rotate yaw).
actor build DeusEx.LaserTrigger --prop Tag=LaserField1 --at 256,0,48 --rotate 0,0,0   | actor add -
actor build DeusEx.LaserTrigger --prop Tag=LaserField1 --at 256,64,48 --rotate 0,32768,0 | actor add -

# 2-3. Control panel that switches the field off when hacked.
actor build DeusEx.ControlPanel \
  --prop UnTriggerEvent.0=LaserField1 --prop hackStrength=0.30 \
  --at 240,0,72 | actor add -
```

## Red `LaserTrigger` vs blue `BeamTrigger`

- `LaserTrigger` — the red beams. Breaking one auto-triggers the alarm; set `bNoAlarm` to suppress
  that.
- `BeamTrigger` — the blue beams. Same directional trip mechanism, no automatic alarm. Fires
  arbitrary events (explosions, gun turrets, opening a door to release a robot). Wire its
  `Event` to whatever `Tag` it should activate.

Both are directional (the arrow is the beam) and both are commonly disabled by a `ControlPanel`.

## Locking a door in general

Only a `DeusExMover` can be locked (the engine `Mover` cannot). The lock surface area:

- `bLocked` — starts locked.
- `lockStrength` — lockpick difficulty (0.10 = 10%).
- `bPickable=False` — cannot be picked; needs a code, key, or hack of the wired device.
- `KeyIDNeeded` — a `NanoKey` with matching `KeyID` unlocks it (see [`nanokey.md`](nanokey.md)).
- A wired keypad/console **overrides** the lock when its code/hack succeeds.

## Properties reference

| Actor / property                              | Meaning |
| --------------------------------------------- | --- |
| `Keypad1/2/3.validCode`                       | The code that opens/unlocks the target |
| `Keypad.bToggleLock`                          | default `True` = toggle the target's lock only; `False` = fire the keypad's `Event` (opens the wired door via its trigger, bypassing `bLocked`) |
| `HackableDevices.bHackable` / `.hackStrength` | Multitool-hackable and how hard (0.20 = 20%) |
| `HackableDevices.UnTriggerEvent[0..]`         | Tags this device switches off (control panel → lasers) |
| device `.Event`                               | Tag this device fires/activates (keypad → door) |
| `LaserTrigger`                                | Red beam; breaks → alarm (`bNoAlarm` suppresses) |
| `BeamTrigger`                                 | Blue beam; no auto-alarm; fires its `Event` |
| `ControlPanel`                                | Hack-only panel; typically disables a laser field |

## Caveats and gotchas

- Placement height (~60–80 uu) is just authored coordinates — there is no grid-snap step in
  uedcli; pick on-grid values directly.
- Array properties like `UnTriggerEvent` and a console's `Views`/`doorTag` are indexed with the
  dot form: `--prop UnTriggerEvent.0=…` (the CLI rejects the T3D `KEY(N)` parenthesis form —
  write `KEY.N`).
- The keypad→door "red line" is editorial; model-side the link is just `keypad.Event ==
  door.Tag`. Make the strings identical and it connects.

## See also

- [`deusex-door.md`](deusex-door.md) — building the lockable `DeusExMover` these target.
- [`security-camera.md`](security-camera.md) — controlling doors from a security console instead.
- [`nanokey.md`](nanokey.md) — the key-based unlock path.
- [`../classes.md`](../classes.md) — the full hackable-device catalog.

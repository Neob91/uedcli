# Recipe: security cameras, consoles, and turrets  [DX]

A Deus Ex security camera watches an area, swings back and forth, and raises the alarm when it spots
the player. Optionally it feeds a `ComputerSecurity` console.

> The camera feed shows up inside the hacked-computer UI, not on a world monitor. When the player logs
> into or hacks a `ComputerSecurity`, the console's screen shows up to three camera feeds. There is no
> `ScriptedTexture`-on-a-wall camera monitor in stock DX (`ScriptedTexture` is a draw-on-surface
> facility for scoreboards/counters; the camera-view-to-surface `DrawPortal` is a UE1 `Canvas` native
> DX's own code never calls). Design cameras as console feeds, not wall TVs.

## A: a standalone camera

### Procedure

1. Place a `SecurityCamera` on a wall or ceiling. Rotate it toward its target with `--rotate` (yaw),
   in unreal rotation units (49152 = 270°, to face −Y). It ships active, hackable at 20%, and raises
   the alarm; it does not swing unless you set `bSwing=True`.
2. Tune its vision (optional). Vision properties are UE byte-angles (65536 = 360°), the same units
   `--rotate` uses (16384 = 90°); pass them verbatim:
   - `cameraFOV` — field of view. Default 4096 = 22.5°.
   - `cameraRange` — sight distance in uu. Default 1024.
   - `bSwing` / `swingAngle` / `swingPeriod` — panning. `bSwing` defaults False (True to pan);
     `swingAngle` default 8192 = 45°; smaller `swingPeriod` = faster sweep = harder to sneak past.
   - `bActive` — starts on; `bNoAlarm=True` to watch without raising the alarm.
3. Set hackability (optional) — `bHackable`, `hackStrength` (0.20 = two multitools untrained).
4. Tag it if a console will show its feed.

### With uedcli

```bash
actor build DeusEx.SecurityCamera \
  --prop cameraFOV=4096 --prop cameraRange=1024 \
  --prop bSwing=True --prop swingAngle=8192 --prop swingPeriod=8 \
  --prop bHackable=True --prop hackStrength=0.20 \
  --prop bNoAlarm=False --prop Tag=Cam_Lobby \
  --at 256,512,240 --rotate 0,49152,0 | actor add -
```

## B: wire cameras (and doors and turrets) to a console

### Procedure

1. Place a `ComputerSecurity` console on a wall, ~60–80 uu up. It ships with no accounts (`userList`
   blank) — add one (username/password/accessLevel) in `userList` or the console is hack-only, pick a
   `ComputerNode` logo, and optionally set `lockoutDelay` (default 120 s after a failed ICE-breaker).
2. Assign camera feeds. The console has `Views[0..2]` — three monitors. Set each `Views[i].cameraTag`
   to a camera's `Tag`; blank views show static. `titleString` per view captions the monitor.
3. Assign controllable doors. Each `Views[i].doorTag` (per-view; no console-level `doorTag`) points to
   a `DeusExMover`'s `Tag`; the player can lock/unlock/open/close it from the console.
4. Assign controllable turrets. Each `Views[i].turretTag` points to an `AutoTurret`/`AutoTurretSmall`
   `Tag`; the player can set it to Bypassed / Allies / Enemies / Everything.

### With uedcli

```bash
# 1. The console (ADD an account — there is none by default — and pick a logo).
actor build DeusEx.ComputerSecurity \
  --prop UserList.0.userName=admin --prop UserList.0.password=hunter2 \
  --prop ComputerNode=CN_UNATCO --prop lockoutDelay=60 \
  --at 240,512,72 | actor add -
#   -> ComputerSecurity0

# 2-4. Wire feeds, a controllable door, and a turret into view 0.
actor prop set ComputerSecurity0 \
  Views.0.cameraTag=Cam_Lobby \
  Views.0.titleString="Lobby" \
  Views.0.doorTag=Door_Lab \
  Views.0.turretTag=Turret_Hall
```

## C: auto-turrets

> Place `AutoTurret` or `AutoTurretSmall`, not the `…Gun` variants. `AutoTurretGun` /
> `AutoTurretGunSmall` only model the "hackable gun" internally; associated with a console they won't
> appear as a controllable turret and generally won't work as placed. `AutoTurret` sits directly under
> `DeusExDecoration`; `AutoTurretSmall` `extends AutoTurret`.

### Procedure

1. Place an `AutoTurret` (large) or `AutoTurretSmall`. For a ceiling turret, rotate it 180° in pitch
   or roll (`--rotate` in unreal rotation units; 32768 = 180°) so it hangs correctly.
2. Tag it so a console can control it.
3. Its hack strength is fixed at 50%; you don't set it.

### With uedcli

```bash
# Wall turret:
actor build DeusEx.AutoTurret --prop Tag=Turret_Hall --at 512,0,200 --rotate 0,0,0 | actor add -

# Ceiling turret: flip 180° so it mounts to the ceiling.
actor build DeusEx.AutoTurretSmall --prop Tag=Turret_Vault --at 0,0,248 --rotate 0,0,32768 | actor add -
```

## Properties reference

| Actor / property                                       | Meaning                                           | Default |
| ------------------------------------------------------ | ------------------------------------------------- | --- |
| `SecurityCamera.cameraFOV`                             | Field of view (byte-angle)                        | 4096 (22.5°) |
| `SecurityCamera.cameraRange`                           | Sight distance (uu)                               | 1024 |
| `SecurityCamera.bSwing` / `swingAngle` / `swingPeriod` | Panning on/off, arc, seconds/sweep                | False / 8192 (45°) |
| `SecurityCamera.bActive` / `bNoAlarm`                  | On at start / suppress alarm                      | True / False |
| `ComputerSecurity.Views[i].cameraTag`                  | Camera feed shown on monitor `i`                  | (blank = static) |
| `ComputerSecurity.Views[i].doorTag`                    | A `DeusExMover` this console can operate          | — |
| `ComputerSecurity.Views[i].turretTag`                  | An `AutoTurret` this console can retask           | — |
| `ComputerSecurity.ComputerNode`                        | Login-screen logo (`CN_UNATCO`, `CN_MJ12Net`, …)  | — |
| `AutoTurret` / `AutoTurretSmall`                       | The turret to place (not the `…Gun` variants)     | hack fixed 50% |

## Caveats and gotchas

- No world monitor. The player sees a camera only through the console UI; there is no
  camera-to-wall-surface render in DX (see the top note).
- Only `AutoTurret`/`AutoTurretSmall` are console-controllable; the `…Gun` variants are internal.
- `Views` is an array of structs; address subfields with the dot form `Views.i.field` in
  `actor prop set` (the CLI rejects the T3D `Views(i).field` parenthesis form).

## See also

- [`deusex-door.md`](deusex-door.md) — the doors a console operates.
- [`keypad-and-locks.md`](keypad-and-locks.md) — the shared hackable-device model.
- [`../classes.md`](../classes.md) — the hackable-device and computer catalog.

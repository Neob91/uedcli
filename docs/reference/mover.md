# mover

A **mover** is a brush actor that animates between **keyframes** (poses). uedcli authors them
model-side: a generator builds the base mover, then `mover key` verbs author its keyframes. Key 0 is
the **base pose** (the ordinary `Location`/`Rotation`); keys 1..`NumKeys`-1 are stored as offsets
from base. A mover has **2..8 keys** (`NumKeys` — the KeyPos/KeyRot arrays are a fixed `[8]`).

The workflow is **raise the count, then edit the keys** (mirroring the editor): `mover key count`
sets how many keys exist; `mover key move`/`rotate` edit an existing key by index (never growing the
count).

See [the mover keyframe workflow](../usage/mover-keyframes.md) for a worked keyframe-authoring example.

- **What counts as a mover is the CLASS HIERARCHY, not the class name.** `mover key` accepts any
  actor whose class is `Engine.Mover` or descends from it — including subclasses whose name does not
  end in `Mover` (`CaroneElevatorSet.CaroneElevator`, `CaroneElevatorSet.CEDoor`,
  `DeusEx.BreakableGlass`, `DeusEx.BreakableWall`) — and, symmetrically, a class that merely ends in
  `Mover` without descending from it is not one. A rejection says which class failed and against
  what: `mover key count: Wall0 is not a Mover (class Engine.Brush does not descend from
  Engine.Mover)`. Resolving the hierarchy reads the game's `.u` packages, so `mover key` needs a
  project + `~/.uedcli/config.toml` (see [Projects](../README.md#projects-uedclitoml)).
- **`--mover-class <Package.Name>`** (on `brush build`) must be fully qualified. It **rejects
  `--csg`/`--solidity`** (a mover carries neither); `--at`/`--texture`/`--group`/`--base-name` apply
  normally.
- **`mover key count <name> [<n>]`** gets (no `n`) or sets (`n` in 2..8) `NumKeys`. Setting is
  **non-destructive** — it only changes the count; lowering it leaves the now-inactive keys' offsets
  dormant, so raising it again restores them. Out of range is a clean error naming the value. It is
  **exactly equivalent to `actor prop set <name> NumKeys=<n>`** (`NumKeys` is a first-class settable
  prop; `KeyPos`/`KeyRot`/`KeyNum` remain `mover key`-only).
- **`mover key move`/`rotate <index>` are edit-only** (`1 <= index < NumKeys`); they do NOT grow
  `NumKeys` — raise it first with `mover key count`. Index 0 is the base pose (edit it with `actor
  move`/`actor rotate`, which rigidly shift/rotate the whole animation).
  - **`--to` requires a coordinate frame:** `--from-base` (the coords are the offset from the base
    pose, written straight in) or `--from-world` (absolute world; uedcli subtracts the base). Passing
    `--to` with no frame is an error — there is no silent default.
  - **`--by DX,DY,DZ`** nudges the *current* offset and is frame-agnostic (it rejects
    `--from-base`/`--from-world`).
  - *Tilted-base caveat:* the rotation math is per-component FRotator arithmetic, geometrically naive
    for a non-cardinal base `Rotation` — for a tilted base, `--from-world` and `--from-base` are not a
    simple additive re-basing.
- **`mover key list --json`** emits `{idx, world_pos, world_rot, off_pos, off_rot, base}` per key.
- Mover config props (`MoveTime`/`DelayTime`/`StayOpenTime`/`OtherTime` timing, the
  `MoverGlideType`/`MoverEncroachType`/`BumpType` behavior enums, `Tag`/`Event`, return-group leader)
  are plain scalars — set them with `actor prop` or the generator's `--prop`, not the `mover key`
  family.

See also: [`actor prop`](actor/prop.md), [the mover keyframe workflow](../usage/mover-keyframes.md), [the door mover flow](../usage/door-mover-flow.md), [Movers](../leveldesign/general/movers.md) (the level-design craft: encroachment, triggering, the black-door fix).

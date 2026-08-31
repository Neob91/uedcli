# actor build

Writes a point-actor T3D for the given class. The class must be fully qualified; a bare name (no `.`)
is rejected.

```
actor build <Package.Class> [--at X,Y,Z] [--base-name NAME] [--prop KEY[.PATH]=VALUE …] [--rotate PITCH,YAW,ROLL]
```

- `--at` sets `Location` (default origin).
- `--base-name` is the stem for the emitted Name (default: the bare class name, e.g. `Light`).
- `--prop KEY[.PATH]=VALUE` (repeatable) bakes a property, **schema-validated against the class**
  (unknown key / bad enum / out-of-bounds index → exit 2; needs the game `.u`). A `Location` token
  routes to the typed field, overriding `--at`.
- `--rotate PITCH,YAW,ROLL` (unreal rotation units — 16384 = 90°) SETS `Rotation` absolutely —
  shorthand for `--prop Rotation=PITCH,YAW,ROLL`. `--rotate 0,0,0` **writes**
  `Rotation=(Pitch=0,Yaw=0,Roll=0)` (an omitted `Rotation` means "the class default", which is not
  zero for every class); omit the flag entirely to emit no `Rotation` line.

```bash
uedcli actor build Engine.Light --at 1000,2000,128 --prop LightBrightness=80 | uedcli actor add -
```

See also: [`actor add`](add.md), [`actor prop`](prop.md).

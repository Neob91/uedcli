# class preview

`class preview <Package.Class>` renders the class's default `Mesh` as an orthographic PNG thumbnail,
natively — it decodes the mesh and its skins from the game's own `.u` packages and software-renders
them, with no editor, container or game. It writes one PNG and prints `<ref><TAB><path>` to stdout
(a human azimuth summary goes to stderr):

```bash
uedcli class preview DeusEx.CrateUnbreakableLarge --out crate.png
# DeusEx.CrateUnbreakableLarge	/abs/path/crate.png   (stdout)
# azimuth 8192 uu (mesh-local yaw, 65536=360deg; not world facing)   (stderr)
```

- The shot is the same **mesh-local frame** as `class show`'s `extents`: the mesh's `Scale` is
  applied, `Origin`/`RotOrigin` are not, and the framing auto-centres — so the picture and the
  extents agree. The default view is **iso** (front-three-quarter).
- **`--rotate PITCH,YAW,ROLL`** poses the mesh at that mesh-local rotator (unreal rotation units,
  16384 = 90°, 65536 = a full turn) **before** the camera shoots it — the **pose oracle**: preview a
  *candidate placement rotation* before you commit it, instead of round-tripping through the game.
- **azimuth** is the camera's mesh-local yaw in unreal rotation units (65536 = 360°) — which yaw in
  the image faces you. `--rotate`'s yaw shifts it. It is a **mesh-local** reading and does **not**
  claim world facing: a non-identity `RotOrigin` re-aims the mesh in the world and is unreconciled
  here (same scope limit as `class show`'s extents). It appears on the stderr summary, and in `--json`.
- **`--out FILE`** names the PNG (relative paths join the cwd; the extension is always replaced by
  `.png`); with no `--out` a unique temp file is written. **`--size PX`** sets the edge length
  (default 512). **`--json`** prints one object `{"ref", "path", "azimuth", "rotate"}` instead of the
  text row (`rotate` is the applied `[pitch, yaw, roll]` or `null`).
- A **non-mesh** class (`DrawType` `DT_Sprite`/`DT_Brush`/`DT_None`) has no mesh to render — a stderr
  note, **exit 0**, no image (matching `class show`'s null extents; not an error). A `DT_Mesh` class
  whose `Mesh` default is unresolvable, or a skin that fails to decode, **exits 2** naming it — never
  a wrong picture. With no composed package path, `class preview` **exits 2** (`no package search
  path`).

See also: [`class show`](show.md).

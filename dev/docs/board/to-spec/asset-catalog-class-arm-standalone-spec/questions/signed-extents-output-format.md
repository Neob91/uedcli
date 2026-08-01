# Report the mesh bbox as signed mesh-local extents, in the frame the spec fixes?

## Context

The load-bearing change (spec §3, §8.1). `class show` and `--json` report the mesh bounding box.
The choice is representation, not whether to report it.

- **Proposed:** `extents: x lo..hi  y lo..hi  z lo..hi` (text) and `"extents": {"x":[lo,hi], …}`
  (`--json`), **always signed** (never a `W×D×H` magnitude), integer Unreal units, in one mesh-local
  frame — **`Scale` applied, pre-`Origin`/`RotOrigin`, each axis re-sorted lo≤hi, `DrawScale` not
  applied**.
- **Why signed:** the collision cylinder is rotation-invariant and carries zero facing information
  (`docs/leveldesign/general/actors.md`), so the signed box is the only place pivot-relative asymmetry
  can live — the facing hypothesis (Q `mount-faces-tag-namespace`, `facing-scope-call`) rests on it. A
  magnitude triple answers seating only.
- **Why integers / this frame:** integers compare directly to `CollisionRadius`/`CollisionHeight` and
  world coordinates; the one frame keeps the reported box, `preview`'s `azimuth`, and the image from
  disagreeing (the rasterizer applies `Scale` then camera pose and auto-centres, so `Origin` drops out).
- **Grounded:** the decoder returns `box`/`scale`/`origin`/`rot_origin` (spike
  `2026-07-25-native-mesh-decode`, `umesh.py`), so no new decode work.

**Recommendation:** adopt as written. `direction/asset-catalog.md` implies the default — the tool
"reports facts literally stored in the package … mesh bounding box" and does not infer — but it does not
fix the signed-vs-magnitude spelling or the frame, so this needs a ruling. The extents also feed
`docs/leveldesign` craft (Q `value-framing-and-craft-line`), which is why it is the owner's call.

## Answer

<!-- Empty = open. -->

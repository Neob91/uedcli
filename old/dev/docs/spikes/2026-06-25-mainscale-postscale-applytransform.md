# MainScale vs PostScale, and what `ACTOR APPLYTRANSFORM` bakes

**Date:** 2026-06-25
**Method:** live probe in `uned-spike1` (UED22 under wine). Built an **asymmetric** box (local
half-extents X=64, Y=32, Z=16 — distinct per axis so orientation is readable) via uedcli's
`builders.cube`, hand-set `MainScale`/`PostScale`/`Rotation` in the actor T3D, `MAP IMPORTADD`'d it,
`SELECTNAME` + `ACTOR APPLYTRANSFORM`, and read the baked PolyList + remaining transform fields back
via `MAP EXPORT`.
**Confidence:** ✅ live-verified (every coordinate below is a `MAP EXPORT` readback).

This confirms the transform semantics needed to make uedcli **use** scale (previews + bounds),
**store** it (already round-trips as a string; needs parsing), and do **offline permanent
transforms** (bake rotation+scale into vertices, reset the fields).

---

## Findings

### 1. MainScale is LOCAL / pre-rotation; PostScale is WORLD / post-rotation

Both are `FScale` = `Scale` (FVector) + `SheerRate` + `SheerAxis` (the `SheerAxis=SHEER_ZX` uedcli
already emits is the identity-shear default).

- **Test B — `MainScale=(Scale=(X=2))` + `Rotation=(Yaw=16384)` (90°), then APPLYTRANSFORM.** Baked
  vertices: **X≈±32, Y≈±128**, Z=±16. The doubled axis landed on **world Y**. So the ×2 scaled the
  brush's *local* X, and the 90° yaw then carried local-X to world-Y ⇒ **MainScale is applied in the
  brush's local frame, BEFORE rotation.**
- **Test C — `PostScale=(Scale=(X=2))` + `Rotation=(Yaw=16384)`, then APPLYTRANSFORM.** Baked
  vertices: **X≈±64, Y≈±64**, Z=±16. Without scale the 90° yaw alone gives world X=±32, Y=±64; the
  ×2 landed on **world X** ⇒ **PostScale is applied in the world frame, AFTER rotation.**
- **Test A — `MainScale=(Scale=(X=2))`, no rotation.** X ±64→±128, Y/Z unchanged (sanity: scale on
  the named axis).

So the world transform is:

```
world = Location + PostScale · R · MainScale · (v − PrePivot)
```

(`R` from the GMath table per `2026-06-19-group-rotate-exact-parity`; the ±31.999989/±32.000011
in test B is that table's float32 floor, not error.)

### 2. `ACTOR APPLYTRANSFORM` bakes the ENTIRE chain, not just MainScale

In every test the export came back with **`MainScale`, `PostScale` reset to identity
`(SheerAxis=SHEER_ZX)` AND no `Rotation` line** (reset to 0), with the PolyList now holding the
**world-space** transformed vertices. So `APPLYTRANSFORM` bakes **MainScale + Rotation + PostScale**
together and zeroes all three.

> **Corrects `unrealed/commands.md`**, which said `APPLYTRANSFORM` "bakes `MainScale` … resets
> scale to identity" (implying MainScale only). It bakes the full transform.

This is exactly the "permanent transform" primitive: one console verb already does what we want.
uedcli can replicate it **offline** (no editor) by evaluating the chain in §1 and resetting the
fields — but see the open items.

### 3. Negative scale (mirror) bakes to a VALID, correctly-wound brush

- **Test D — `MainScale=(Scale=(X=-1))`, APPLYTRANSFORM, then `MAP REBUILD`.** The brush survived
  rebuild (CSG-valid), MainScale reset to identity, and the baked first polygon's winding produces
  the correct outward `-X` normal (cross-product of its vertex ring = `(-,0,0)`). So the editor
  **reversed the polygon winding** to compensate for the reflection's flipped orientation.

**Load-bearing for the offline port:** a naïve offline bake that just multiplies coords by the
scale matrix would, for a negative determinant (odd number of negative scale axes), leave the
winding reversed → inside-out solid → CSG crash on rebuild. uedcli's bake **must reverse each
polygon's vertex order when `det(PostScale·R·MainScale) < 0`** to match the editor. (This is the
same winding gotcha as the planned `actor mirror`; mirror is just `MainScale` with one −1 axis, so
the two features share this fix.)

## Open items (for the spec — not blockers)

- **Sheer.** `SheerRate`/`SheerAxis` (e.g. a non-`SHEER_ZX` axis with a non-zero rate) was NOT
  tested — all tests used the identity-shear default. The exact per-`SheerAxis` shear matrix needs
  its own spike/RE. v1 can scope to **scale-only** and explicitly reject a non-zero `SheerRate`.
- **Location / PrePivot interaction during the bake.** Both were `(0,0,0)` here, so it's not yet
  pinned whether the baked PolyList stays **PrePivot-relative** (`… + PrePivot`, Location/PrePivot
  fields kept) or folds Location/PrePivot in. One more test with non-zero `Location` AND non-zero
  `PrePivot` settles it before the offline bake can claim editor parity. (D8 says never rewrite
  `PrePivot` implicitly — so the bake likely keeps vertices pivot-relative and leaves
  `Location`/`PrePivot` untouched, but verify.)
- **APPLYTRANSFORM on IMPORTADD brushes works** (confirmed here — `SELECTNAME` + `APPLYTRANSFORM`
  baked an IMPORTADD'd brush), unlike `ACTOR DELETE` which no-ops on them. Not needed for the
  offline port (which computes the bake in Python) but noted.

## Implications for the feature

- **Store:** `MainScale`/`PostScale` already round-trip as opaque prop strings; the work is to
  **parse** them into `Scale`+`SheerRate`+`SheerAxis` so geometry code can use them.
- **Use (preview/bounds):** fold `PostScale·R·MainScale·(v−PrePivot)` into the world-vertex path
  (`rotation.world_vertices` and its consumers — `preview`, `query.level_bounds`/`list_*`,
  `writes.actor_bounds`), so scaled/sheared brushes render and measure correctly. Today these honour
  R+PrePivot but skip scale (`unrealed/quirks.md` "Pivots").
- **Permanent transform (offline):** a verb that evaluates the chain into the PolyList, **reverses
  winding on negative determinant**, `clean()`s to grid, and resets `Rotation`/`MainScale`/
  `PostScale` to identity — mirroring `ACTOR APPLYTRANSFORM` with no editor. Subsumes `actor
  mirror`.

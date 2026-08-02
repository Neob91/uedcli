# Geometry & BSP  [ENGINE]

Clean, on-grid geometry avoids most problems; off-grid geometry produces invisible holes.

## Subtract, then add

The world starts as infinite solid void. Subtract rooms out of the solid, then add detail brushes
inside the hollow.

A builder brush (the editor's red "cookie cutter") is shaped, then committed as a Subtract or Add
operation. The builder brush itself is never part of the level — only the operations it stamps are.
uedcli hides the builder brush behind generators: each `brush build` prints a T3D brush actor
carrying its own shape and CSG operation.

```
brush build cube --csg subtract --width 512 --breadth 512 --height 256 --texture CoreTexMetal.ClenGrayMetal_A | actor add -   # carve a room
brush build cube --csg add --solidity semisolid --width 32 --breadth 32 --height 256 | actor add -                           # a pillar inside it
```

- `--csg subtract` hollows solid; `--csg add` fills space back in. Carve the shell first, furnish after.

## Brush order determines the result

At build time the compiler walks brushes in order; where two operations overlap the same region, the
last one wins.

- Send subtractive / structural brushes first; additive / detail brushes last. ✅
- uedcli's CSG precedence is the trunk's `(order_value, name)` sort. Move a brush in that order with:

```
brush build cube --csg add --width 64 --breadth 64 --height 128 | actor add -   # prints the allocated name (e.g. Cube_ab12cd; pass --base-name to steer it)
actor order --last Cube_ab12cd     # furnish last (default for adds)
actor order --first Wall1           # structural first
```

## Solidity: solid, semisolid, nonsolid

Every CSG brush has a solidity (`--solidity` on `brush build`), controlling whether the brush cuts
the BSP and whether it can seal a zone.

| Solidity            | Cuts BSP?                 | Can be subtracted-from / seal a zone?      | Use for |
| ------------------- | ------------------------- | ------------------------------------------ | --- |
| **solid** (default) | yes                       | yes                                        | structural surfaces; anything you subtract from; zone boundaries |
| **semisolid**       | **no** (cuts only itself) | no                                         | solid-collision detail that needn't cut BSP — beams, pillars, trim, **walkable** ledges |
| **nonsolid**        | no                        | no (placed only inside a subtracted solid) | markers, **zone-portal sheets**, pure decoration |

- Semisolids are fully walkable, with the same reliable collision as solid; the only difference is a
  semisolid does not cut the world BSP (it splits only itself). 📖
- Semisolid keeps node count low. Because it cuts only itself, use it to localise off-grid, curved,
  or fine detail so it doesn't emit world-splitting planes; collision is unaffected.
- A semisolid must not touch another semisolid, a nonsolid, or a zone portal — this reliably wrecks
  the local BSP (invisible polys / HOM / merged zones). 📖 To make two touching semisolids safe, weld
  them into one brush with `brush intersect` (see below). 📖 This is the narrow case where intersect
  earns its keep, distinct from the "always intersect touching brushes" myth rejected below (which is
  about routinely intersecting solid on-grid brushes that don't need it).

```
brush build cube --csg add --solidity semisolid --width 128 --breadth 16 --height 16 | actor add -   # a decorative beam
brush build sheet --width 256 --height 128 --flag portal --flag invisible | actor add -              # a zone-portal sheet (nonsolid by default; invisible so the plane doesn't render)
```

### Solidity is stored per-face, not per-brush

In UE1 a brush has no single "solidity" field — solidity is two bits in each polygon's `PolyFlags`:
`PF_Semisolid` (`0x20` = 32) and `PF_NotSolid` (`0x08` = 8). A "solid" brush is one whose faces carry
neither bit; a "semisolid" brush is one whose faces all carry `0x20`. (In the editor, changing a
brush's PolyFlags from 32 to 0 flips its wireframe from pink/semisolid to blue/additive — the same
per-face bit uedcli's `--solidity` sets.) 📖

`brush build … --solidity semisolid` stamps that bit onto every face of the one brush it emits, so a
single builder looks per-brush. But the bit is really per-face, so one brush can carry a mix of
solidities — and `brush intersect` is how you build one:

- `brush intersect` CSG-merges a piped brush set into one welded brush (additives make solid,
  subtractives carve it), keeping each surviving face's own solidity: a face from a solid additive
  stays solid, a face from a semisolid additive stays semisolid (`0x20`). So intersecting a solid slab
  + a subtracted opening + a semisolid pane yields a single brush that is solid frame with a semisolid
  window in it. ✅ *(live-verified: the welded brush's glass faces read `Flags=32`, the frame faces
  `0` — 2026-07-25.)*
- This is why the glass-in-a-door recipe works: a mover is one brush, and the intersect bakes the
  frame-and-glass composite into that one brush with the glass faces still semisolid + translucent.
  There is no "separate glass actor" — see
  [recipes/glass.md](recipes/glass.md#glass-in-one-brush-the-intersect-composite-window) and
  [movers.md](movers.md). The per-face rule is also why a semisolid pane can sit flush in its opening
  without a gap: its side faces coincide with the subtracted reveal walls but, being semisolid, do not
  merge into them (a solid pane would merge, and translucency would then look straight into the brush
  interior).

## Avoiding BSP holes and HOM

A BSP hole is a missing or see-through world face. In game it shows as HOM (hall-of-mirrors — the
last frame smears across the gap because nothing drew there); in solid space a hole can even kill the
player. It happens when the compiler couldn't cleanly split a piece of geometry and discarded the
face — the discarded face is the hole. ✅

The community myth that "off-grid coordinates cause a floating-point overflow" is false. The real
cause is a handful of discrete tolerance bands in the split/merge tests (a ~0.25 uu plane-alignment
band; a ~1e-4 uu vertex-merge band). Off-grid coordinates land inside those bands, so faces get
mis-classified, collapsed, or thrown away. The fix: stay out of the bands by building on clean
coordinates.

uedcli does not snap geometry to grid as you build — on-grid discipline is yours to keep. When a
brush has drifted (a corner reading `15.997` where `16` belongs), `brush snap - --grid N --tolerance
T` rounds each near-grid vertex back to the grid while leaving intentional off-grid angles alone (see
[usage.md](../../usage.md) "Brush shape & surfaces"); it cleans float noise, not a brush that is
genuinely off-grid by design.

### Defenses

1. Stay on-grid, in powers of two. Build in clean multiples — 2, 4, 8, 16, 32, 64, 128, 256. `96`,
   `112`, `128` are fine; `100` is not. Off-grid signature: a coordinate reading `15.999976` where
   `16` belongs.
2. Rotate solid (world-cutting) brushes only in 90° increments. A solid brush's off-grid planes spray
   bad BSP cuts through the whole world, leaving irrational coordinates no "transform permanently"
   step can rescue. Semisolids, nonsolids, and decoration rotate to any angle freely — they don't
   partition the world BSP, so their off-grid planes only cut themselves (a 45°-rotated box as a
   semisolid is fine, and often the right tool).
3. Keep every face planar and convex. Never pull one corner of a quad off its plane; never place two
   coincident vertices. A face carries exactly one plane — off-plane vertices make rendering and
   classification diverge (cracks / HOM) or collapse the face entirely.
4. Coplanar surfaces: either exactly coplanar, or ≥1 unit apart. A sheet laid flush on a floor
   z-fights (flickers) — lift it ≥1 uu, because 1 uu is wider than the 0.25 uu split band. Never leave
   two surfaces almost-but-not-quite in the same plane.
5. Push off-grid / curved / detail geometry to semisolid. It receives cuts but emits no
   world-splitting planes — keep it clear of other semisolids/nonsolids/portals (see above).
6. Watch node count. Every brush face is a partitioning plane; an awkward face becomes a "supercut"
   that splits many others and seeds error. Aim for a node:poly ratio around 2:1 (retail UT maps run
   ~2.5–2.6:1; an unsplit cube is 1:1); a high ratio (rule of thumb, roughly >4:1) is a warning sign,
   not a hard threshold. A runaway ratio, or one giant over-detailed brush, is the sign to simplify.
   Hard ceiling ≈ 65,536 BSP nodes — overflow it and UnrealEd can no longer save the map (a separate
   ~128,000-point limit is what actually crashes); instability often starts around 45–55k.

### If a hole appears anyway

Work through these repair moves (`materialize` again after each to check):

- Reorder the offending brush — `actor order --first` / `--last`.
- Snap it back on-grid and rebuild (`brush snap` for near-grid drift).
- Flip a nearby semisolid ↔ solid — re-cuts the local BSP a different way (a standard fix).
- Split the room into smaller, simpler brushes.
- Nudge the culprit brush slightly and rebuild.

### Myths to reject

- "Off-grid causes a floating-point overflow" — no; it's the tolerance bands above.
- "High node count itself causes holes" — correlation, not cause; the only hard node effect is that
  overflowing the ~65,536 static-node count blocks the save (the crash is the separate ~128,000-point limit).
- "Always intersect/deintersect touching brushes" — unnecessary on-grid, and often adds complexity.
  (The one real exception is two touching semisolids, which should be welded into one brush — see
  "Solidity is stored per-face" above; a narrow safety case, not a routine habit.)
- "Overlapping brushes cause holes" — false; only coplanar-coincident + off-grid surfaces do.
- Antiportals and static-mesh round-trip repair are UE2+ techniques — they do not exist in UE1.

## Related

- [zones-and-performance.md](zones-and-performance.md) — sealing the shell into zones; the poly budget.
- [brush-shapes.md](brush-shapes.md) — the shapes you build these brushes from.
- [human-scale.md](human-scale.md) — what "on-grid at the right size" means in numbers.

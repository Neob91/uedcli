# Recipe: ring cornice (copy-rotate around an axis)  [ENGINE]

UE1 has no curved brushes, so a ring, crown, segmented rail, or cornice is built from one straight
block, copy-rotated around an axis.

### What you're building

A ring of ~8 identical trapezoidal blocks spaced 45° apart around a central vertical (Z) axis, each
rotated to face the centre — a voussoir/cornice ring.

### uedcli pipeline (what you run)

```
# 1. one block out at the ring radius (+X), 40 radial x 64 tangential x 24 tall
brush build cube --width 40 --breadth 64 --height 24 --at 128,0,0 | actor add -     # -> wedge_ab12cd

# 2. taper its two tangential sides into a trapezoid (narrow edge toward the centre) — two clips
brush clip wedge_ab12cd --plane 148,32,0  -16,40,0  --keep below
brush clip wedge_ab12cd --plane 148,-32,0 -16,-40,0 --keep below

# 3. replicate 7 more at 45° steps about the Z axis (16384 UU = 90°, so 8192 = 45°)
for i in 1 2 3 4 5 6 7; do
  dup=$(bin/uedcli actor duplicate wedge_ab12cd --by 0,0,0 | tail -1)   # copy onto itself
  bin/uedcli actor rotate "$dup" --by 0,$((i*8192)),0 --pivot 0,0,0     # ORBIT about the world axis
done
```

`actor rotate … --pivot 0,0,0` both orbits the copy's Location around the world pivot and composes
the yaw into its Rotation, so one command places and turns each block. No trig needed beyond
45° = 8192.

### Notes

- `actor duplicate … --by 0,0,0` stacks a copy on the original, ready to be orbited. `duplicate`
  requires a placement, and `0,0,0` is the "copy in place" value.
- Known bug — don't run the loop too fast. Rapid back-to-back `duplicate`+`rotate` can hit a trunk
  delta-write race that silently drops the copies (0 actors persisted). Until it's fixed, run the
  steps un-hurried / check the actor count after each, or retry a step that produced no name.
- Rotation angles are UU, not degrees: `65536 = 360°`, so `8192 = 45°`, `10922 ≈ 60°` (8 vs 6 vs 12
  facets = `65536 / N`).
- Blocks needn't touch — small gaps read as discrete cornice blocks; overlap them if you want a
  continuous ring. True radial side planes (through the axis) only work if each block subtends its
  full facet angle; for narrow blocks at a large radius, taper via the outer corners as above.

# Recipe: add / subtract twin  [ENGINE]

Not a shape but a **workflow** — the way real levels seat shaped trim, ledges, and platforms into walls.
Build a shaped **additive** solid, copy it, flip the copy to **subtractive**, and drop it into the wall
so it carves a recess the exact shape of the trim. The piece then sits in its own perfect negative.

### What you're building

A wall block, a beveled trim block (additive), and a subtractive duplicate of the trim carving a
matching recess into the wall.

### uedctl pipeline (what you run)

```
# 1. the wall mass
brush build cube --width 512 --breadth 256 --height 256 --csg add | actor add -           # Wall_ab12cd

# 2. the additive trim: a beveled block sitting proud of the wall
brush build cube --width 128 --breadth 64 --height 64 --csg add --at 0,320,0 | actor add - # Trim_cd34ef
brush clip Trim_cd34ef --plane 64,0,0 1,0,1 --keep below         # 45° bevel on the +X/+Z edge

# 3. the SUBTRACT twin: duplicate the trim, move it into the wall, flip its CSG op
actor duplicate Trim_cd34ef --by 0,-320,96                        # copy, translated into the wall mass
actor prop set Trim_cd34ef_<suffix> CsgOper=CSG_Subtract          # flip add -> subtract: it now CARVES
```

The additive trim and the subtractive cut are the **same brush** (same clip, same dimensions), so the
recess matches the trim exactly.

### Notes

- **Flipping add ↔ subtract is `CsgOper`.** `actor duplicate` has no `--csg` flag today, so you set the
  property directly: `actor prop set <name> CsgOper=CSG_Subtract` (the enum values are `CSG_Add` /
  `CSG_Subtract`). This works but is undiscoverable — a first-class affordance may come later. Until
  then, remember the enum spelling.
- **Order matters for CSG.** A subtractive brush must be processed *after* the solid it carves — check
  `actor order` if the recess doesn't appear (later = carves what's already there).
- **This is why so much real geometry comes in blue/orange pairs.** When you see a shaped additive brush
  and a near-identical subtractive one nearby, it's this idiom: build the solid, carve its twin.
- Verify the twin is truly identical with two `brush poly list` calls — same face areas, centroids
  offset only by the translation vector.

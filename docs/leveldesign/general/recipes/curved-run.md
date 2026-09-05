# Recipe: curved run (continuous texture along a bend)  [ENGINE]

One texture flowing continuously along a run of faces that turns — a cylinder wrap, a curved track
bed, or an L-shaped wall — instead of the pattern restarting at every facet. `brush poly align run`
does it model-side: it walks a connected strip, lays U along the run and V across it, and carries the
phase across every seam.

## What you're building

A brush whose curved strip of faces (a revolve's swept side, a cylinder's sides) carries one
seamless texture around the bend.

## uedcli pipeline (what you run)

```
# 1. build the curved brush. A revolve sweeps a 2D profile around an axis into one brush; its swept
#    side faces (ItemName Side0/Side1/…) are the strip to texture.
brush build revolve --point 192,-16 --point 256,-16 --point 256,16 --point 192,16 --angle 32768 --segments 6 --axis x --at 0,0,0 | actor add -   # --angle 32768 = 180°; prints e.g. Bed_ab12cd

# 2. texture the strip, then align it as one continuous run. `find` selects the swept bed by ItemName;
#    `align run` reads that face set from stdin (order does not matter — the walk is derived).
brush poly find Bed_ab12cd --item Side0 | brush poly set - --texture DeusExDeco.Textures.Metal
brush poly find Bed_ab12cd --item Side0 | brush poly align run -

# 3. wrap a cylinder the same way — exclude the caps (they touch every side, so a run cannot include them):
brush poly find Tower --item Side | brush poly align run -
```

## Notes

- `align run` **derives its own walk order**, so the order faces arrive in has no bearing on the
  result — a `brush poly find … | align run -` pipe is safe however `find` orders its output.
- It must be one un-forking strip of one brush. A set that **branches** (a face touching 3+ others —
  a cylinder's cap touches every side) or is **disconnected** exits 2 naming the faces, with the hint
  to filter with `--item Side`.
- `--turn UU` rotates the whole run's texture (16384 = 90°). A cylinder wrap stays exact at any angle;
  a **flat** bend shears at its seams — `align run` prints the worst seam shear to stderr so you can
  mitre a sharp flat corner or accept the seam.
- Scale before you align a run (`brush poly scale … --by`), not after: the run computes its seam
  phases for the density it sees. Pan after (`brush poly pan`), and pan the whole run or none of it.
- Re-run the alignment after any CSG/geometry edit — a rebuild can disturb texturing.

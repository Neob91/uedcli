# brush measure relation

**`brush measure relation`** replaces eyeballing a render with exact computed facts: for every pair
of faces across the named brushes (2+ names, or `-` for a stdin name list), it reports whether the
planes are coplanar or parallel, both normals, the signed distance between them, the 2-D footprint
relationship (`none`/`vertex`/`edge`/`partial`/`contains`/`coincident`), and the centroid/edge-min
deltas in the shared plane's own U/V axes. `--top N` caps how many ranked candidate face-pairs are
shown per brush pair (default 1, closest first); `--top all` shows every qualifying pair. Brushes
sharing no plane and no parallel-facing relationship with anything else named are reported as
`disjoint` rather than silently omitted.

```
$ uedcli brush measure relation Wall_North Floor
Wall_North <-> Floor  (1 of 12 candidates shown)
  Wall_North:5 <-> Floor:4
    plane: coplanar
    normals:
      Wall_North:5: (0.000, 0.000, -1.000)
      Floor:4: (0.000, 0.000, 1.000)
    distance: 0.000uu
    footprint_2d: contains (Wall_North:5 in Floor:4)
    deltas:
      centroid: U=120.000uu V=0.000uu
      edge: U-min=0.000uu V-min=0.000uu

checked: 2 brushes, 1 pairs, every face
```

See also: [`brush poly`](poly.md), [`brush vertex`](vertex.md).

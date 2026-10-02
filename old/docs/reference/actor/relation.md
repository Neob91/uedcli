# actor relation

find / compare / set

For connectivity/containment discovery across MULTIPLE brushes — which brushes touch, contain, or
are carved by which — see [`level graph`](../level/graph.md); `actor relation` answers questions
about a pair of faces (or a face and an actor) you already know. `REF`/`--relative-to` is always a
face selector — a bare brush Name (all its polys) or `Name:SELECTOR` (`SELECTOR` = `all` or comma
indices) — in every subcommand, because a face is what you align against. `TARGET`/`candidates` can
additionally name a non-brush actor (a Light, a Keypad, any point actor with a `Location`), compared
or moved by that `Location` rather than by a face.

**`actor relation compare REF TARGET...`** reports the exact geometric relationship between a
reference face selector and one or more targets — replaces eyeballing a render with computed facts.
Against another brush's face selector it reports whether the planes are coplanar or parallel, both
normals, the signed distance between them, the 2-D footprint relationship (`none`/`vertex`/`edge`/
`partial`/`contains`/`coincident`), and the centroid/edge-min deltas in the shared plane's own U/V
axes. Against a bare non-brush actor's Name it reports a narrower set — a point has no footprint area
and no edges, so there is nothing to fill an edge or footprint_2d value in with: `distance` (signed,
along REF's normal), `point_footprint` (`inside`/`on_boundary`/`outside` of REF's own footprint), and
`centroid_u`/`centroid_v` (the point's own U/V position, no delta to compute against). `TARGET`
accepts more than one selector, or `-` alone to read a newline list from stdin — exactly `actor
relation find`'s output shape, so `find | compare REF -` gets full detail on exactly the set `find`
matched. Repeated face selectors naming the same brush have their polys unioned into one comparison;
a repeated non-brush Name is not. `--top N` caps how many ranked candidate pairs are shown per brush
target (default 1, closest first); `--top all` shows every qualifying pair — `--top` has no effect on
a non-brush target, which reports exactly one block. REF and a brush target must name different
brushes unless `--allow-self` is given (comparing two faces of the same brush).

```
$ uedcli actor relation compare Wall_North Floor
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

Against a non-brush actor, the same command instead prints one block per target with the point's own
field set:

```
$ uedcli actor relation compare Room Light
Room:0 <-> Light
  distance: -212.000uu
  point_footprint: inside
  centroid_u: 512.000uu
  centroid_v: 512.000uu
```

**`actor relation find <candidates...> --relative-to REF[:idx]`** is a stateless producer: it prints
candidates related to a reference face, one per line, for piping into `actor relation compare -`,
`actor relation set -`, `brush poly align -`, or `brush poly move -`. A brush candidate prints as a
`candidate:idx` selector; a non-brush candidate, having no face index, prints as a bare Name.
`candidates` is zero or more actor Names, or `-` to read a newline list from stdin; omit it entirely
(no names, no `-`) to search every OTHER BRUSH in the level — the implicit, no-names search never
includes non-brush actors, only an explicitly named one is a real candidate. `--relative-to` is
required: a bare brush Name ranks against every one of its polys, `Name:idx` pins to one reference
face. Filters AND together: `--max-gap N` / `--min-gap N` bound the perpendicular gap, `--footprint
LIST` (comma-separated `none`/`vertex`/`edge`/`partial`/`contains`/`coincident`) and `--plane
{coplanar,parallel}` narrow by relationship shape — since a face-pair predicate has nothing to test a
point against, giving either flag drops every non-brush candidate from the results rather than
erroring. `--top N` (default 1) / `--top all` controls how many pairs are kept per brush candidate;
a non-brush candidate always contributes at most one row, whatever `--top` says. `find` only ever
reports IDENTITY, never geometry: stderr gets one aggregate count ("N face(s) matched across M
candidate(s)"); `--json` emits each match's `ref`/`ref_poly`/`candidate`/`poly` as a JSON array on
stdout instead (and drops the stderr summary) — a non-brush match's `poly` is `null`. For the
geometric detail behind a match, pipe into `actor relation compare REF -`, which reads exactly this
stdout shape. The reference's own brush is excluded from the default search and rejected if named
explicitly, unless `--allow-self`.

`--max-gap`'s comparison carries a tiny built-in tolerance for float dust, so a genuinely flush pair
always passes `--max-gap 0`. Without `--footprint`, a same-plane brush candidate with NO footprint
overlap is dropped by default (never shown as a match) — but if one exists within `--max-gap`, stderr
adds a note ("N candidate face(s) nearby with no footprint overlap — pass --footprint none to
include") rather than staying silent about it; this near-miss note is footprint-keyed and never
counts a non-brush candidate.

```
$ uedcli actor relation find --relative-to Wall_North --max-gap 8
Panel:0
Shelf:2
$ uedcli actor relation find --relative-to Wall_North --max-gap 8 | \
    uedcli actor relation compare Wall_North -
Wall_North <-> Panel
  ...
Wall_North <-> Shelf
  ...
```

**`actor relation set TARGET --relative-to REF:idx`** moves `TARGET` (its `Location` only — a
brush's shape is unchanged, a non-brush actor has nothing else to move) so it hits a target gap,
centroid offset, or edge offset from the fixed `REF`, which never moves. A brush `TARGET` must be an
exact `Name:idx` (a bare name or index list is rejected — the move target can't be ambiguous); a
non-brush `TARGET` is its bare Name, since it has no face to select. `TARGET` may instead be `-`,
reading a newline list from stdin (brush `TARGET:idx` and non-brush bare Names both allowed), moving
each one relative to the same `REF`. A brush `TARGET` and `REF` must already be parallel or coplanar
(typically piped straight from `actor relation find`'s output) — a non-planar pair is a clean exit 2;
a non-brush `TARGET` has no plane of its own, so this check does not apply to it — `REF`'s own plane
is what every offset below is measured against. Every flag takes an explicit target distance, and an
omitted flag leaves that degree of freedom untouched: `--gap N` sets the signed perpendicular
distance along REF's normal; `--centroid-u N` / `--centroid-v N` set the centroid offset on that
axis (for a non-brush `TARGET`, its own point position stands in for its centroid); `--edge-u-min N`
/ `--edge-u-max N` (and the `-v-` equivalents) set the offset from that specific edge of `REF`
instead — mutually exclusive with the matching `--centroid-*` flag on the same axis, and still
meaningful against a non-brush `TARGET` even though its own "edge" is a single point, since `REF`'s
own U-min and U-max remain two different values. At least one flag is required. Unlike `find` and
`compare`, `set` does not accept `--allow-self` — a brush `TARGET` and `REF` must be different
brushes. When `TARGET` is `-` (piped list), all targets are validated before any are mutated or
saved; a failure in any target leaves the whole batch untouched.

```
$ uedcli actor relation find --relative-to Wall_North --max-gap 8 | \
    uedcli actor relation set - --relative-to Wall_North:5 --gap 0 --centroid-u 0
Panel
Shelf
```

See also: [`brush poly`](../brush/poly.md), [`brush vertex`](../brush/vertex.md).

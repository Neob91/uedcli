# brush relation

measure / find / set

**`brush relation measure REF TARGET...`** reports the exact geometric relationship between a
reference face selector and one or more target selectors — replaces eyeballing a render with
computed facts: whether the planes are coplanar or parallel, both normals, the signed distance
between them, the 2-D footprint relationship (`none`/`vertex`/`edge`/`partial`/`contains`/
`coincident`), and the centroid/edge-min deltas in the shared plane's own U/V axes. A selector is a
bare brush Name (all its polys) or `Name:SELECTOR` (`SELECTOR` = `all` or comma indices) — pin
`Wall:5 Floor:4` to compare exactly those two faces, or leave a side bare to rank every one of that
brush's polys against the other side. `TARGET` accepts more than one selector, or `-` alone to read
a newline selector list from stdin — exactly `brush relation find`'s output shape, so `find |
measure REF -` gets full geometric detail on exactly the set `find` matched. Repeated
target selectors naming the same brush have their polys unioned into one comparison. `--top N` caps
how many ranked candidate pairs are shown per target (default 1, closest first); `--top all` shows
every qualifying pair. REF and a target must name different brushes unless `--allow-self` is given
(comparing two faces of the same brush).

```
$ uedcli brush relation measure Wall_North Floor
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

**`brush relation find <candidates...> --relative-to REF[:idx]`** is a stateless producer: it
prints candidate faces related to a reference face as `candidate:idx` selectors, one per line, for
piping into `brush relation set -`, `brush poly align -`, or `brush poly move -`. `candidates` is
zero or more brush Names, or `-` to read a newline list from stdin; omit it entirely (no names, no
`-`) to search every OTHER brush in the level. `--relative-to` is required: a bare brush Name ranks
against every one of its polys, `Name:idx` pins to one reference face. Filters AND together:
`--max-gap N` / `--min-gap N` bound the perpendicular gap, `--footprint LIST` (comma-separated
`none`/`vertex`/`edge`/`partial`/`contains`/`coincident`) and `--plane {coplanar,parallel}` narrow
by relationship shape. `--top N` (default 1) / `--top all` controls how many pairs are kept per
candidate. `find` only ever reports IDENTITY, never geometry: stderr gets one aggregate count
("N face(s) matched across M candidate(s)"); `--json` emits each match's `ref`/`ref_poly`/
`candidate`/`poly` as a JSON array on stdout instead (and drops the stderr summary). For the
geometric detail behind a match — plane, normals, distance, footprint_2d, deltas — pipe into
`brush relation measure REF -`, which reads exactly this stdout shape. The reference's own brush
is excluded from the default search and rejected if named explicitly, unless `--allow-self`.

`--max-gap`'s comparison carries a tiny built-in tolerance for float dust, so a genuinely flush
pair always passes `--max-gap 0`. Without `--footprint`, a same-plane candidate with NO footprint
overlap is dropped by default (never shown as a match) — but if one exists within `--max-gap`,
stderr adds a note ("N candidate face(s) nearby with no footprint overlap — pass --footprint none
to include") rather than staying silent about it.

```
$ uedcli brush relation find --relative-to Wall_North --max-gap 8
Panel:0
Shelf:2
$ uedcli brush relation find --relative-to Wall_North --max-gap 8 | \
    uedcli brush relation measure Wall_North -
Wall_North <-> Panel
  ...
Wall_North <-> Shelf
  ...
```

**`brush relation set TARGET:idx --relative-to REF:idx`** moves `TARGET`'s whole brush (its
Location only — the shape is unchanged) so it hits a target gap, centroid offset, or edge offset
from the fixed `REF`, which never moves. Both selectors are exact `Name:idx` (a bare name or index
list is rejected — the move target can't be ambiguous); `TARGET` may instead be `-`, reading a
newline `TARGET:idx` list from stdin, moving each one relative to the same `REF`. The two faces
must already be parallel or coplanar (typically piped straight from `brush relation find`'s
output) — a non-planar pair is a clean exit 2. Every flag takes an explicit target distance, and an
omitted flag leaves that degree of freedom untouched: `--gap N` sets the signed perpendicular
distance along REF's normal; `--centroid-u N` / `--centroid-v N` set the footprint centroid offset
on that axis; `--edge-u-min N` / `--edge-u-max N` (and the `-v-` equivalents) set the offset from
that specific edge instead — mutually exclusive with the matching `--centroid-*` flag on the same
axis. At least one flag is required. Unlike `measure` and `find`, `set` does not accept
`--allow-self` — the TARGET and REF must be different brushes. When TARGET is `-` (piped list),
all targets are validated before any are mutated or saved; a failure in any target leaves the whole
batch untouched.

```
$ uedcli brush relation find --relative-to Wall_North --max-gap 8 | \
    uedcli brush relation set - --relative-to Wall_North:5 --gap 0 --centroid-u 0
Panel
Shelf
```

See also: [`brush poly`](poly.md), [`brush vertex`](vertex.md).

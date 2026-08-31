# One-shot CSG construction — `brush intersect` / `brush deintersect`

Some geometry can only be produced by CSG (the engine's boolean carve/intersect over brushes).
`builders.py`/`clip.py` are model-side and emit primitives straight to T3D, but a boolean
result — the solid a cluster of adds and subtracts encloses, or the void they carve — has to be
computed by the CSG algorithm. `brush intersect` / `brush deintersect` are the two verbs that do it.

They are stateless generators: a T3D brush set in on stdin, one merged brush actor T3D out on
stdout. See [`../../docs/reference/brush/intersect.md`](../../docs/reference/brush/intersect.md)
for the user-facing reference and [`architecture.md`](architecture.md) for where they sit in the
layer map.

> Historical note. These were once `stash intersect` / `stash deintersect`, which drove a live
> UnrealEd through a per-command ephemeral container. Both the editor dependency and the
> stash-shaped interface are gone: the merge is native (`brushcsg.py` →
> `uedcli_native.intersect_brushset`, the decoded `bspBrushCSG` intersect tail), and the input is a
> pipe, so every tier feeds it through its own `show` verb. The verbs were deleted, not aliased
> (`CLAUDE.md` "no back-compat cruft"). *(`direction/generators.md`, 2026-07-24 16:32 / 17:04, 2026-07-25.)*

## The recipe

1. Produce or select the input brushes. Either generate them (`brush build cube/cylinder/…`)
   or take them from the tree (`actor find … | actor show -`), a stash (`stash show <id>`), or the
   library (`prefab show <name>`). All four emit the same T3D block form.
2. Compute the boolean. Pipe the set into `brush intersect -` (needs ≥1 additive; merges
   against an EMPTY background) or `brush deintersect -` (needs ≥1 subtractive; merges against a
   SOLID background and returns the void as a solid). Stdin order is the CSG order — a mixed
   add/subtract set is order-dependent, so the pipe controls it. The merge is model-side, no editor.
3. Land the result. Pipe it into `actor add -` (one add into the trunk), redirect it to a
   file, or `stash capture --from-t3d -` / `stash promote` it into the durable `prefabs/` library.

The intermediate construction never touches the trunk — only the final brush lands, via a single
`actor add`.

```bash
uedcli actor find --folder castle.door | uedcli actor show - \
  | uedcli brush deintersect - --mover-class Engine.Mover --solidity solid --pivot min \
  | uedcli actor add -
```

## The stash register

Every project has a machine-local stash register at `<root>/.uedcli/stash/` (inside the
project's self-ignoring state dir) (`stash_register.FileStashRegister`). It holds named entries,
each a captured set of actors (`write_stash`/`read_stash`/`list_stashes`/`drop_stash`). `stash
capture` fills it from the selected level or from `--from-t3d <FILE…|->` (one-or-more T3D files, or
`-` for a stdin snippet). It is a general-purpose scratch register, not part of the CSG path — the
merge verbs read a pipe, and a stash reaches them via `stash show <id> |` like anything else.

## How the result is verified

The bar is T3D face-set parity with UnrealEd's own `BRUSH FROM INTERSECTION`/`DEINTERSECTION`,
enforced offline against committed goldens in `uedcli/tests/fixtures/intersect/`
(`test_brush_merge.py` — cases covering ordered add/subtract/re-add, overlapping and abutting
brushes, nested and disjoint voids, and thin/rotated/off-grid geometry). The goldens were captured
from the live editor by `tests/editor_oracle.py`, which survives only as the regenerator: it runs
under `-m integration` (deselected by default), and rewrites the fixtures only when
`UEDCLI_REGEN_GOLDENS=1` is set, so a wedged editor run can never silently become the new oracle.

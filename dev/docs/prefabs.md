# One-shot CSG construction — `brush intersect` / `brush deintersect`

Some geometry can only be produced by **CSG** (the engine's boolean carve/intersect over brushes):
`builders.py`/`clip.py` are pure model-side and emit primitives straight to T3D, but a boolean
*result* — the solid a cluster of adds and subtracts actually encloses, or the void they carve —
has to be computed by the real CSG algorithm. `brush intersect` / `brush deintersect` are the two
verbs that do it.

They are **stateless generators**: a T3D brush set in on stdin, one merged brush actor T3D out on
stdout. See [`../../docs/usage.md`](../../docs/usage.md) for the user-facing reference and
[`architecture.md`](architecture.md) for where they sit in the layer map.

> **Historical note.** These were once `stash intersect` / `stash deintersect`, which drove a live
> UnrealEd through a per-command ephemeral container. Both the editor dependency and the
> stash-shaped interface are **gone**: the merge is native (`brushcsg.py` →
> `uedctl_native.intersect_brushset`, the decoded `bspBrushCSG` intersect tail), and the input is a
> pipe, so every tier feeds it through its own `show` verb instead of needing a bespoke wrapper.
> The verbs were deleted outright, not aliased (`CLAUDE.md` "no back-compat cruft").
> *(decisions.md 2026-07-24 16:32 / 17:04, 2026-07-25.)*

## The recipe

1. **Produce or select the input brushes.** Either generate them (`brush build cube/cylinder/…`)
   or take them from the tree (`actor find … | actor show -`), a stash (`stash show <id>`), or the
   library (`prefab show <name>`). All four emit the same T3D block form.
2. **Compute the boolean.** Pipe the set into `brush intersect -` (needs ≥1 additive; merges
   against an EMPTY background) or `brush deintersect -` (needs ≥1 subtractive; merges against a
   SOLID background and returns the void as a solid). **Stdin order is the CSG order** — a mixed
   add/subtract set is order-dependent, so the pipe is what controls it. No editor, no container:
   the merge is model-side and instant.
3. **Land the result.** Pipe it into `actor add -` (one clean add into the trunk), redirect it to a
   file, or `stash capture --from-t3d -` / `stash promote` it into the durable `prefabs/` library.

The intermediate construction never touches the trunk — only the final brush lands, via a single
explicit `actor add`.

```bash
uedctl actor find --folder castle.door | uedctl actor show - \
  | uedctl brush deintersect - --mover-class Engine.Mover --solidity solid --pivot min \
  | uedctl actor add -
```

## The stash register

Every project has a machine-local **stash register** at `<root>/.uedctl/stash/` (inside the
project's self-ignoring state dir) (`stash_register.FileStashRegister`). It holds named entries,
each a captured set of actors (`write_stash`/`read_stash`/`list_stashes`/`drop_stash`). `stash
capture` fills it from the selected level or from `--from-t3d <FILE…|->` (one-or-more T3D files, or
`-` for a stdin snippet). It is a **general-purpose scratch register**, not part of the CSG path —
the merge verbs read a pipe, and a stash reaches them the same way anything else does, via
`stash show <id> |`.

## How the result is verified

The bar is **T3D face-set parity with UnrealEd's own `BRUSH FROM INTERSECTION`/`DEINTERSECTION`**,
and it is enforced OFFLINE against committed goldens in `uedctl/tests/fixtures/intersect/`
(`test_brush_merge.py` — cases covering ordered add/subtract/re-add, overlapping and abutting
brushes, nested and disjoint voids, and thin/rotated/off-grid geometry). The goldens were captured
from the live editor by `tests/editor_oracle.py`, which survives ONLY as the regenerator: it runs
under `-m integration` (deselected by default), and it rewrites the fixtures only when
`UEDCTL_REGEN_GOLDENS=1` is set, so a wedged editor run can never silently become the new oracle.

# Spec — uniquify batch-added actors + rename build `--name` → `--base-name`

*Ephemeral design scratch. Decisions land in `dev/docs/decisions.md`; durable behavior folds into
`architecture.md` + `usage.md` once built.*

## Problem

Two coupled dogfooding findings (inbox 2026-07-12):

1. **CRITICAL — `actor add` silently collapses actors that share a `Name` (N → 1).**
   Concatenating several `brush build`/`actor build` outputs with the same `Name` into one T3D and
   `actor add`-ing it keeps only the LAST. **Root cause (confirmed):** `model.parse_t3d`
   (`model.py:88`) stores actors in a `dict` keyed by `Name`, so duplicates are overwritten *at
   parse time* — before `actor add`'s per-actor uniquify loop (`dispatch.py:1612`, which is itself
   correct) ever sees them. The same collapse hits every path that parses user-supplied,
   concatenated T3D, i.e. also **`stash capture --from-t3d/--from-stdin`** (`_capture_from_t3d`,
   `dispatch.py:81`).

2. **`brush build --name` is a misnomer, and `actor build` has no counterpart.** `alloc_name`
   (`trunk.py:73`) *always* appends `_<rand>`, so the stored name is always `<value>_<rand>` — the
   value passed is only ever a **stem/prefix**, never the literal final name. `actor build` has no
   `--name`-family flag at all, so every `actor build Engine.Light` is named `Light`, which then
   collapses under bug (1) on a batch add.

## Decisions (Andrzej, 2026-07-12)

- **Rename `brush build --name` → `--base-name`** (rejected: keep `--name` — misleading; `--name-prefix`
  — `_<rand>` is a suffix, not a prefix chain). Use the **same `--base-name`** on the new
  `actor build` flag for parity.
- **Fix scope = all user-T3D ingest points**, not just `actor add` (rejected: `actor add` only) —
  no ingest path may silently drop duplicate-named actors.

## Design

### A. `parse_t3d_actors` — an ordered, duplicate-preserving parse (model.py)

Add:

```python
def parse_t3d_actors(text: str) -> list[Actor]:
    """Every actor in `text` as an ordered list, PRESERVING duplicate Names.
    `parse_t3d` keys actors by Name in a dict, so on a Name collision it silently keeps only the
    last; any caller ingesting user-concatenated T3D MUST parse via this and uniquify before
    dict-keying."""
```

Refactor `parse_t3d` to build its dict from `parse_t3d_actors` (one parse loop, single source of
truth). A stored `Level` still keeps unique-Name invariant (dict is correct there); the collapse is
only wrong at the *user-T3D ingest boundary*.

### B. `actor add` (dispatch.py:1601–1631)

Replace `parse_t3d(text).actors.values()` with `parse_t3d_actors(text)` with builder brushes
filtered **out** (`not is_builder_brush(a)`). The existing uniquify loop (`alloc_name` →
`<stem>_<rand>` per actor) already gives each a unique identity — it now simply receives all N. Add
a stdout confirmation `added N actor(s)` (directly answers the finding's "only caught via
`actor find | wc -l`"; precedent: `_apply_set` already prints `applied N actors`, dispatch.py:328).

### C. `stash capture` (`_capture_from_t3d`, dispatch.py:76–96)

Parse via `parse_t3d_actors` (ordered list, dups preserved). **Filter by the `names` subset FIRST,
against the raw source names, THEN uniquify only the chosen set** — this is the order-critical fix
the reviewers caught: uniquifying before filtering re-drops a duplicate the user explicitly asked
for (`capture Torch` over two `Torch`s would suffix the 2nd, so the bare-`Torch` filter matches only
the 1st — a silent recurrence of the very bug). Filtering first, both `Torch`s match; then uniquify
(first keeps its bare Name, each later collision → `alloc_name(stem, seen)`) so both are captured.
Source order is captured from the chosen list's order *before* `normalize_level` re-sorts
`level.actors` by Name (order is held on `level.order`, which normalize leaves intact). Because the
`full` dict (dispatch.py:95) and returned `order` (dispatch.py:96) are BOTH Name-keyed/derived,
uniquifying before them is necessary AND sufficient — no second collapse. Equivalent to today in the
all-unique and capture-all cases.

### D. Rename `--name` → `--base-name` on brush build (cli.py:266; dispatch.py:1441,1443)

`_common_build_opts` is shared across every shape + `--mover-class`, so the single rename covers
all. `dest="base_name"`; update the two `args.name` reads in the brush-build branch to
`args.base_name`. New help: makes clear it is a stem and a `_<rand>` suffix is appended at
`actor add`. (The unrelated `actor find --name` at cli.py:165 is untouched.)

### E. `actor build --base-name` (cli.py ~200; dispatch.py:1416)

Add `--base-name` (dest `base_name`, default `None`); the emitted `Actor` name becomes
`args.base_name or cls`. Stateless generator semantics unchanged; the real unique identity is still
minted at `actor add`.

## Tests

- `parse_t3d_actors` returns all N for a duplicate-Named input; `parse_t3d` still collapses (invariant
  documented, not a regression).
- **Regression (the CRITICAL bug):** `actor add` of a concat of N same-Named actors → N stored actors,
  all names unique; plus a mixed input (some duplicate + some already-unique) → all preserved.
- `actor add` prints `added N actor(s)` (assert the count string).
- `stash capture --from-stdin` of N same-Named actors → N members (capture-all).
- `stash capture <dupname> --from-stdin` over a duplicated source → N members (the filter-then-uniquify
  regression; would pass under the wrong order too only for capture-all, so this explicit-`names` case
  is the one that pins it). Assert source order preserved and first member keeps its bare Name.
- `stash capture --from-t3d FILE` variant (not only `--from-stdin`) exercised at least once.
- `brush build cube --base-name Merlon` emits `Name="Merlon"`; multi-step (spiral) still per-step
  indexed; `--name` now rejected by argparse.
- `actor build Engine.Light --base-name Torch` emits `Name="Torch"`; default (no flag) still `Light`.

### Test migration (required — will otherwise turn the suite red)

Renaming to `dest="base_name"` means the brush/actor-build branches read `args.base_name`. Existing
tests that hand-build an `argparse.Namespace` with the old `name=` kwarg (or omit it for actor build)
must be updated: `test_dispatch.py:249,266`, `test_generators.py:89,128,381` (brush build `name=` →
`base_name=`), and `test_generators.py:146,161,171,200` (actor build namespaces gain `base_name=None`).
Audit by grep, don't trust the line numbers blindly.

## Docs & board

- `architecture.md` 274–282 (brush/actor build generator descriptions) + `usage.md` 124–197 (flag
  tables/examples): `--name` → `--base-name`, add `actor build --base-name`.
- `decisions.md`: append the rename + uniquify-on-ingest entries (with rejected alternatives).
- Move the two resolved inbox items (CRITICAL silent-collapse; `actor build` no-`--name`) to
  `done.md`.

## Flag for Andrzej (post-review)

A cold reviewer noted the `--name` rename is a **hard break** on an LLM-facing surface: any
existing prompt/example using `brush build --name` now hard-fails with argparse's "unrecognized
arguments". Per your explicit rename directive I am NOT adding a back-compat alias; but a hidden
`--name` alias (`add_argument("--name", dest="base_name", help=argparse.SUPPRESS)`) would remove that
breakage class at ~zero cost while keeping the new spelling canonical in help/docs. Captured as an
inbox flag to decide, not silently actioned.

## Out of scope

- Multi-step `brush build` per-step indices (`Merlon0`/`Merlon1`) are NOT preserved through
  `actor add` — its `stem = name.rstrip("0-9")` collapses them to a shared stem before the random
  suffix. Pre-existing behavior, unchanged here.

- The other dogfooding items (`level create`, `actor build` batch beyond naming, doctor duplicate-
  Location warning). The `actor find --class LevelInfo` glob bug is separate.

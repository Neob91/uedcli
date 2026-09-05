+++
priority = "p1"
kind = "bug"
summary = "native concatenates LightBits/Lights in BSP-walk order; UED22 uses surf-index order — blocks the ladder at N>=10 (WanChai) / N>=11 (UNATCO)"
+++

# native lightmap concat order is BSP-walk, not surf-index

The lockstep ladder passes N=1..9 on all three levels, then WanChai
`06_HongKong_WanChai_Market` fails from N=10 and UNATCO `03_NYC_UNATCOHQ` from N=11. Both are a
single world `Model` body residual whose only unmasked divergence is in the lightmap arrays.

## Pinned cause (both cells): data-concatenation ORDER, not lighting content

The lit set, per-surf light counts, grid descriptors (`UClamp`/`VClamp`/`Pan`/`UScale`/`VScale`),
and the `LightMap` record ARRAY order are all **byte-identical** native==ued. The `LightBits` bytes
and the `Model.Lights` region-2 run contents are identical too (modulo the gate's ObjRef remap).
The sole divergence is the `DataOffset` and `iLightActors` VALUES stamped into each `FLightMapIndex`,
because native lays the `LightBits` planes and the per-surf `Lights` runs down in a **different order**
than UED22.

- **UED22 concatenates the per-surf `LightBits` planes and `Lights` runs in surf-INDEX order.**
- **native concatenates them in BSP-tree-walk order** (`lightmap_emit_order`), the same order it
  (correctly) emits the `LightMap` record array.

The `LightMap` record array is in BSP-walk order in BOTH — that part native already matches. The bug
is that native uses that same walk order for the *data* concatenation, whereas UED22 decouples the
two: record array = walk order, data concatenation = surf-index order.

### Evidence

WanChai N=10: exactly 2 lit records, rec3=surf24 and rec6=surf19; everything else dark. Descriptors
match. Only:

    native  rec3 DataOffset=0 iLightActors=26   rec6 DataOffset=8 iLightActors=28
    ued     rec3 DataOffset=8 iLightActors=28   rec6 DataOffset=0 iLightActors=26

UED lays surf19's data first (DataOffset 0), surf24's second (8) => surf-index ascending (19<24).
native lays them in record/walk order (rec3 surf24 before rec6 surf19). The two 8-byte planes are
even byte-equal (`ffffffffffff0000`), so the swap is only visible in the offsets/`iLightActors`.

UNATCO N=11: 4 records with `iLightActors>=0` (all EMPTY runs, `LightBits`=0), rec0=surf17,
rec5=surf30, rec36=surf6, rec48=surf39. `iLightActors` order:

    native  surf17=0  surf30=1  surf6=2   surf39=3   (record/walk order)
    ued     surf6=0   surf17=1  surf30=2  surf39=3   (surf-index ascending 6<17<30<39)

Both build the same 4 empty runs; UED orders them in the `Lights` array by surf index, native by walk
order.

Repro (cached builds under `_scratch/actor-parity/<level>/{native,ref}_N*.dx`):

    python _scratch/_lm_full.py  <native.dx> <ref.dx>   # per-record DataOffset/iLightActors/uc/vc
    python _scratch/rec2surf.py  <dx>                    # record -> surf link
    python _scratch/_bits_swap.py <native.dx> <ref.dx>   # LightBits planes + Lights array

## Why it surfaces only at N>=10 / N>=11

The reorder is a no-op whenever there is <=1 lit/empty-run surf, or the lit/empty surfs happen to
appear in walk order == surf-index order. N=1..9 satisfied that by coincidence. WanChai N=10 is the
first cell where two lit surfs appear in walk order (surf24 before surf19) opposite to surf-index
order (19 before 24). UNATCO N=11 is the first where a surf-index-early surf (surf6) sits late in the
walk (rec36).

## f4abce2 is NOT implicated

The N=8 fix (`f4abce2`) only added the EMPTY-RUN encoding (a lone `-1` terminator for a gather-visible
but per-lumel-unlit surf). At WanChai N=10 the two divergent records are genuinely LIT (real bits,
real light runs) — f4abce2's empty-run path is never exercised for them. At UNATCO N=11 the divergent
records ARE empty runs that f4abce2 correctly creates (UED22 creates the same 4); the divergence is
only their ORDER in the arrays, a separate pre-existing bug in the concat loop. Reverting f4abce2
would not fix either cell and would re-break N=8 (WanChai) and make UNATCO N=11 worse (dark where UED
has empty runs). f4abce2 stays.

## Fix plan (bounded, low-risk)

In `uedcli-native/src/light.rs` `bake` (the "(5) Serial concat" block, ~L438-455), decouple record-
array order from data-concatenation order. Currently one `emit_record` call does both — assign
`DataOffset`/`iLightActors` + append `LightBits`/`Lights`, AND push the record + link the surf — all
driven by `lightmap_emit_order` (walk order).

Split into two passes:

1. **Surf-index order (`for si in 0..bakes.len()`):** for each `SurfBake`, assign its
   `rec.data_offset`/`rec.i_light_actors` and append its `bits`/`light_indices` to
   `model.light_bits`/`model.lights`. This lays the data arrays in surf-index order (the empty-run and
   dark encodings from `emit_record` are preserved verbatim; dark records append nothing so their
   position is irrelevant).
2. **BSP-walk order (`lightmap_emit_order`, then the defensive surf-order sweep):** push each surf's
   now-finalized record into `model.light_map` and set `surf.i_light_map` to the pushed index. This
   keeps the record ARRAY (and the `surf.iLightMap` link) in walk order, which already matches UED22.

Concretely: split `emit_record` into `finalize_offsets(model, &mut SurfBake)` (pass 1) and a record-
push loop (pass 2). Update the doc comment at L438-444 (it currently asserts walk order aligns
`LightBits`/`Lights` positionally — that premise is the bug). Update the unit test
`emit_record_populated_empty_and_dark_encodings` to the split API; it can still pin the three on-disk
encodings by running pass 1 in index order then pass 2.

The permeating region (`write_permeating_region`, region 1 of `Model.Lights`) is written before the
bake concat and is untouched — the reorder only affects the region-2 per-surf runs appended after it.

Confirm the editor's surf-index concat order against the disasm before landing: the raytrace pass
(`Editor 0x100a5010`, spike §20 §1 step 4, "called once per lit static surface") is expected to iterate
`Model.Surfs` in index order, which is what assigns `DataOffset`/`iLightActors` sequentially. Two cells
already show surf-index-ascending (6 data points); a one-line disasm check of the caller loop closes it.

### Size / risk

Small: ~20-30 lines in `bake` plus splitting `emit_record` and adjusting one unit test. No change to
the visibility gather (`visible_surfs.rs`), the per-lumel bake, grid sizing, or the empty-run/dark
distinction. NOT a re-derivation of `GetVisibleSurfs`/`shadowBSP`.

Risk is low but the change touches every level's lightmap byte layout, so validate corpus-wide:
re-run the parity gate on all three ladder levels N=1..9 (must stay PASS — the reorder is a no-op there)
and N=10..16, and the wider retail corpus via the standard sweep, before merging. Lighting couples
across surfs/lights only through these two arrays, and the fix reorders whole per-surf blocks without
changing their contents, so a regression would show up as a shifted `DataOffset`/`iLightActors` on some
level — caught directly by the gate.

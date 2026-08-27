# May I make these four corrections to `spikes/2026-07-15-native-materialize/sections/20-lighting-bake.md`, and add a write-up for the new spike?

## Context

Each item below is a statement that doc makes which fresh `Editor.dll`/`render.dll` disassembly
(2026-08-27) plus the editor's own `LIGHT APPLY` output on `01_NYC_UNATCOHQ` now contradicts. The code
is already corrected and carries the evidence in its comments; the doc is what is left, and
`dev/docs/` needs your yes.

Two more docs contradict the code the same way and would need the same yes:
`dev/docs/architecture.md` still lists Rust `light.rs`/`paths.rs` as "removed 2026-08-23" and says the
native build that consumed the lighting pass was removed; `dev/docs/direction/materialize.md` says the
native geometry path "has no lighting yet". Both are now false.

## 1. §22 finding 1 — the grid-sizing rule

Currently: `Clamp = ceil(extent / lumel_scale)`, fitted 484/484 on `Test_Castle.dx`.

Proposed replacement:

> **Grid dim = `Clamp(ceil((extent − 0.25) / lumel_scale), 2, 256)`.** The `0.25` is the half-lumel
> pad at each end (`Pan = min − 0.125`) taken back out before the division.
>
> Fitted against the editor's own `LIGHT APPLY` output on `01_NYC_UNATCOHQ` (3434 lit records, 6868
> axes; `spikes/2026-08-27-native-light-apply-parity/harness/grid_formula_fit.py`), predicting each
> record's stored `UClamp`/`VClamp` from that record's own surf extent:
>
> | candidate | axes exact |
> |---|---:|
> | `ceil((extent − 0.25)/scale)` | **6868 / 6868** |
> | `ceil(extent / scale)` | 6605 / 6868 |
> | `round(extent / scale)` | 6379 / 6868 |
> | `trunc((extent − 0.25)/scale − 0.5) + 1` | 6116 / 6868 |
>
> The two leading forms differ only where the extent sits within 0.25 ABOVE an exact multiple of the
> lumel scale — e.g. surf 7, extent 160.001831 at scale 32: `ceil(5.00006) = 6`, editor stores 5.
> `Test_Castle`'s axis-aligned geometry never produces such an extent, which is why the earlier fit
> scored 484/484 there and only broke on real level content. Every boundary the earlier form cites
> still holds (extent 64 at 32 → 2, 1024 at 32 → 32, 80 at 32 → 3, 16 at 32 → clamped to 2).
>
> Confirmed instruction-by-instruction at `Editor 0x100a5bf0`: `size = rint((extent − 0.25)/scale −
> 0.5) + 1`, `cvtsd2si` at round-to-nearest, which is the same `ceil` for any extent that is not
> bit-exactly `0.25 + n·scale`. Two further corrections from the same decode:
> * **The upper bound is not a clamp.** `size > 256` DOUBLES the lumel scale and recomputes the axis
>   (`0x100a5dba`; the V axis retries independently at `0x100a5dac`), so an oversized surface gets a
>   different `UScale` too, not a truncated grid.
> * **Only the extent subtraction is f32.** Everything after it is f64 down to one narrowing store,
>   and the `0.25`/`0.5`/`0.125` constants are f64 in `.rdata` (`movsd`), not f32.

## 2. §21 (A) — the within-run order of the per-leaf permeating lists

Currently: "the byte-level order is gather-order *in export-ref space*, not sorted".

Proposed: it is exactly **descending `Level->Actors` index order**. `Portalize`
(`Editor 0x100aa370`) loops lights outer in ascending `Level->Actors` order, completes one light's
whole flood before the next, dedupes per (leaf, light), and PREPENDS each mark
(`0x100a6f2c`) — so the flatten emits each leaf's run reversed. The measured leaf-0 run
`[44,43,42,39,19,13,12]` is that rule, not an arbitrary trace. (Full decode in board item
`port-the-per-leaf-permeating-light-lists-model`.)

## 3. §6 — both residuals are now closed

Currently: residual 1 is "corner `u`, centre `u+0.5`, or the 2×2 supersample implied by the `0.25`
constant at `0x100dcb00`"; residual 2 is the inverse-basis assembly, "the one lighting item that can
be silently, broadly wrong".

Proposed: residual 1 is settled — **one ray per lumel, at the grid CORNER**
(`Editor 0x100a5920`–`0x100a5a42`). The `0.25` at `0x100dcb00` is not a supersample: it is the
`PF_BrightCorners` grid inset (§4 below). Residual 2 is confirmed CORRECT as implemented: the editor
builds `FCoords(0, TextureU, TextureV, Normal).Inverse().Transpose()` and reads off `XAxis`/`YAxis`,
which unwinds to `u_dir = (TextureV × Normal)/det`, `v_dir = (Normal × TextureU)/det` with
`det = TextureU · (TextureV × Normal)`. One refinement that does matter for byte identity: the editor
walks the grid by repeated f32 ADDITION of `u_dir · UScale`, not by solving per lumel, and applies the
`Normal × 4` bias ONCE to the grid origin.

## 4. New — `PF_BrightCorners`, which the doc does not mention at all

Proposed addition (it was 84% of the last shadow-bit residual):

> `PF_BrightCorners = 0x00080000` — named from `unrealed.exe`'s own surface-flags dialog table
> (`.data 0x4cd8f8`, beside control `0x42a`, captioned "Bright Corners"; the same table gives
> `PF_DirtyShadows = 0x00040000`). It changes the bake in two ways and the stored descriptor in none:
>
> 1. The SAMPLE grid is inset: origin `+= 0.25 · (u_dir + v_dir)` and the step becomes
>    `(f32)((f64)UScale − 0.5/(USize−1))` (`0x100a56ff`–`0x100a5818`). The SERIALIZED
>    `UScale`/`VScale` keep the un-shrunk values.
> 2. The shadow ray's `ExtraNodeFlags` goes from `0x04` to `0x14` (`0x100a597a`). Bit `0x10` does NOT
>    exempt a node from being solid — inside the walker (`Engine 0x101ae190`) a solid terminal is a
>    hit only once some empty cell has been reached, and since the walk takes the near half of every
>    crossing first, "no empty cell yet" means the ray STARTED in solid; with the bit set it reports
>    CLEAR instead (`0x101ae451`–`0x101ae45b`). That matters because a lumel grid is the surface's
>    texture-space BOUNDING BOX, so on a non-rectangular or corner-adjacent face many lumels sit
>    inside neighbouring brushes.
>
> Measured effect on the UNATCO oracle: surfaces WITHOUT the flag were already 99.2% plane-identical,
> surfaces WITH it only 33.6%; honouring both mechanisms took the whole map from 96.2% to 99.0% of
> per-(surface,light) planes byte-identical.

Two more small facts from the same decode, for §5: the shadow ray is `UModel::LineCheck`
(`Model` vtable `+0x58` → `Engine 0x101ae4c0`), `Owner = NULL`, `End = light.Location`,
`Start = lumel`, `Extent = (0,0,0)`, any hit blocks (no `Time` threshold); and the radius test is a
strict `d2 < R2` in f32 with `R` hoisted per light. Also: an ordinary shadow ray already passes
`ExtraNodeFlags = 0x04`, so `NF_NotVisBlocking` nodes never occlude — worth stating, since treating
them as occluders cost 54157 lumels on UNATCO.

## And: may I add `spikes/2026-08-27-native-light-apply-parity/spike.md`?

The harness is already committed there (`rules/spikes.md` sanctions that). I would like to add the
write-up: the oracle-construction problem and its resolution, the four bake rules above with their
measurements, the parity table, and the three gaps that are owned elsewhere (the per-leaf region, the
`Points` f32 residual, `URender::GetVisibleSurfs`). Say the word and I will post the exact text here
for approval before writing it.

## Answer

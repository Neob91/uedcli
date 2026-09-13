+++
priority = "p2"
kind = "debug"
summary = "Island is byte-exact N=1..331 and bails at N=332: leaf 273 carries Light124 where UED22 leaves it out. Root-caused to a genuine vertex COINCIDENCE (a portal vertex shared exactly with an adjacent portal) that makes one FLinePlaneIntersection crossing land a hair below the shared point in native and a hair above it in a live editor capture -- same formula, same inputs, opposite sign of a sub-ULP residual. Not fixed. x87-vs-SSE double-rounding RULED UNLIKELY (2026-09-13a, fctrl probe). 2026-09-13b: a HEX-PRECISION live capture (not decimal) proves the crossing's INPUTS are NOT bit-identical after all -- one of the two input vertices (a Pass-B portal-quad corner, not a raw Model.Point) is 1 ULP off native's assumed grid value in the live editor. The beam-clip's own formula/precision are cleared; the divergence is upstream in Pass B portal construction. Second reproducer: unatco-n-226-leaf-12-gets-a-permeating-light157."
spikes = ["dev/docs/spikes/2026-09-07-gather-box-verdict/"]
+++

# Island N=332 — leaf 273 gets one permeating light UED22 does not

Same shape as `wanchai-n58-leaf-51-permeating-light-over-included` (`Model.Lights` region 1, one
leaf, one extra light) but a DIFFERENT, more precisely pinned mechanism — not the same cause.

## The divergence

    ladder_run.py --dx dev/games/deusex/Maps/01_NYC_UNATCOIsland.dx --from 332 --to 332 --keep-native
    -> FAIL -- BODY model model2: canonical bodies differ

    model_dump.py native_N332.dx ref_N332.dx Model2
    -> only `nodes`/`surfs`/`verts`/`zones`/`leaves` differ by the gate-excluded occlusion/orphan-vert
       masks (confirmed via parity_gate's own masking); `lightmap` (region 2, per-surf) is CLEAN
       (lightrun_diff.py: "differing runs: 0"); `lights` is 5930 vs 5929.

    leaf_perm_diff.py native_N332.dx ref_N332.dx
    leaves 421 421; Model.Lights 5930 5929
    leaf[273] zone=1/1 iVolumetric=-1/-1
        nat=(light172, light171, light249, light380, light124, light244, light109)
        ued=(light172, light171, light249, light380,          light244, light109)
        extra=[light124]

Every other leaf and light run is byte-identical (0/421 leaves differ besides this one).

## Root cause — traced to one crossing via a live capture

`Light124` (li=34 in trunk-light order, `Location=(-4528.346680,4385.676270,64.370674)`) floods from
seed leaf 157. `UEDCLI_PERM_TRACE=34` (native) vs `actor_visibility_probe.py` + `perm_flood_diff.py`
(live `Editor.dll 0x100a6d00` capture) agree on every leaf and crossing except four, all downstream
of ONE decisive crossing:

    crossings native takes and the editor does not: [(275, 272), (275, 273), (273, 280), (273, 281)]

Leaf 275 is visited 9 times by both sides (same portal graph, same DFS shape — confirmed by matching
visit counts and per-visit target sets). In 8 of the 9 visits both sides agree the 273/272 faces fail
the beam clip. In the 9th visit — entered via the `162 -> 275` crossing — **native keeps** the beam
into 273 and 272; **the editor's own capture never does** (no `AV_REC from=275 to=273`/`to=272` in
any of its 9 visits, live-verified).

### The beam clip that decides it

`UEDCLI_PERM_TRACE_EDGE=162-275` / `=275-273` (native) dumped the exact polygons:

- `162 -> 275`'s face poly (raw model geometry, `clip=None` — a depth-0 seed crossing, so this is
  byte-identical to UED22's own `Model.Points`, confirmed: `model_dump.py` reports `points SAME`):

      C0=(-4495.9995, 4080, -140.00002)  C1=(-4495.9995, 4080, 192)
      C2=(-2343.996,  4080,  192)        C3=(-3173.9976, 4080, -140)

- `275`'s face toward `273` (also raw geometry, also byte-identical):

      T0=(-3564, 3628, 192)  T1=(-4495.9995, 3628, 192)
      T2=(-4495.9995, 4080, 192)  T3=(-3564, 4080, 192)

**`T2` and `C1` are the exact same point** — leaves 162, 275 and 273 share this one BSP vertex. That
coincidence is the whole bug: clipping `275`'s face by the plane `FPlane(Light, C1, C0)` (built while
entering leaf 275 via 162) puts `T2` at `plane_dot == 0.0` EXACTLY (T2 IS one of the plane's own three
defining points), so the interpolated crossing between `T1` (clearly behind) and `T2` (exactly on the
plane) has `sc == 1.0` in real numbers and lands within one ULP of `T2` itself, on whichever side
sub-ULP rounding puts it.

Native (from `PERM_EDGE_DUMP`) computes that crossing at `y = 4079.9988` — BELOW 4080, i.e. behind the
`162->275` clip poly's own defining vertex, which then also passes the very next clip edge (`C1->C2`,
also colinear at `y=4080`) and reaches 273/272. The editor's live capture of the SAME `162->275`
output polygon (`AV_REC ... nv=5`, `--verts 8`) shows the analogous pair at `y = 4080.00073` /
`4080.00024` — ABOVE 4080 — which (not measured directly, but consistent with every other observed
crossing) evidently fails the next clip step and drops 273/272.

### Native's formula is not obviously wrong

Reproducing `permeating_lights::clip_beam`'s exact arithmetic — `Vec3::cross`/`dot` left-to-right,
`fpoly::safe_normal`'s documented f64-sqrt/f64-reciprocal-then-round-to-f32 (the routine's own doc
comment: "modelled as an f64 divide, not `safe_normal_slow`'s single-precision one" — `Core.dll
0x51090`, disassembled), `plane_w`/`plane_dot`'s exact term grouping, and `line_plane_intersection`'s
`FLinePlaneIntersection` formula (`Engine.dll 0x1506f0`) — in Python/numpy at float32 precision
reproduces native's actual `4079.9988` bit for bit. So native is not silently using a DIFFERENT
formula than documented; the documented formula, evaluated in strict single-precision at every step,
really does give `4079.9988` for these exact inputs.

A first (wrong) attempt at the same hand-check, using a naive `sqrt`-then-single-divide normalize
instead of `fpoly::safe_normal`'s real two-step f64 reciprocal, gave `4080.0012` — close to the
EDITOR's side. That is suggestive, not proof: it shows the crossing's sign is sensitive to exactly
how many extra bits of precision survive between the normalize and the final divide, which is the
signature of an **x87-vs-SSE double-rounding difference** (the editor's original ~2000-era compiled
code may keep more of this chain in the x87 80-bit stack across multiple operations than the
documented, instruction-level-verified formula assumes was rounded to f32 at each named step) — but
it is not a confirmed mechanism, only a plausible one matching the direction of the error.

## Why this isn't fixed here

- It sits at a genuine geometric coincidence (three leaves' portals sharing one exact vertex), so the
  "fix" is not a wrong formula to correct — the documented formula is disassembly-confirmed correct
  and reproduces native's real output exactly. Whatever is missing is a finer register-level effect
  (candidate: x87 extended-precision retention across `SafeNormal`'s reciprocal and the subsequent
  `FLinePlaneIntersection` divide) that needs new disassembly/live-register evidence, not a
  Python-level formula re-derivation, to pin down and reproduce faithfully.
- This is the prime-directive line in `NATIVE-MATERIALIZE.md`: a divergence from a different
  algorithm is fixed regardless of cost, but this is not yet shown to BE an algorithm difference —
  only a same-formula sub-ULP sign flip at a shared-vertex coincidence. Confirming which it is needs
  more live-register evidence (e.g., single-stepping the editor's real `SafeNormal`/
  `FLinePlaneIntersection` call through this exact vertex under `gdb`) before a fix is safe to write
  — a guess here risks moving the many now-passing near-tie cases (N=8, N19, N45, N93, N123, N153)
  that already depend on the current formula.
- No mask/exclusion was added — the gate still reports this N as a real FAIL, per
  `NATIVE-MATERIALIZE.md`'s "exclusion is a last resort" rule. This is reported, not hacked around.

## Repro

    dev/docs/spikes/2026-09-03-incremental-actor-parity/harness/ladder_run.py \
        --dx dev/games/deusex/Maps/01_NYC_UNATCOIsland.dx --from 332 --to 332 --keep-native
    dev/docs/spikes/2026-09-07-gather-box-verdict/harness/leaf_perm_diff.py \
        _scratch/actor-parity/01_nyc_unatcoisland/{native,ref}_N332.dx

    # live capture (needed once; ref/subset must exist -- actor_parity.py ... subset 332 first)
    dev/docs/spikes/2026-09-07-gather-box-verdict/harness/actor_visibility_probe.py \
        --trunk _scratch/actor-parity/01_nyc_unatcoisland/N332/maps/01_nyc_unatcoisland \
        --out <log> --verts 8

    # exact polygons at the decisive crossing
    UEDCLI_PERM_TRACE=34 UEDCLI_PERM_TRACE_EDGE=162-275 actor_parity.py --dx <island.dx> native 332
    UEDCLI_PERM_TRACE=34 UEDCLI_PERM_TRACE_EDGE=275-273 actor_parity.py --dx <island.dx> native 332

## Second reproducer + a correction to the x87-vs-SSE hypothesis (2026-09-12)

`unatco-n-226-leaf-12-gets-a-permeating-light157` is the same mechanism: a live gdb capture of that
level's `13->12` crossing shows native's `FLinePlaneIntersection` landing EXACTLY (0 ULP) on a vertex
shared between two portal faces, while the editor's own capture of the identical crossing lands about
1 ULP off that same vertex — not a tie there, but the same shape (native ties where the editor
doesn't). See that item for the full trace.

That session also flagged that this item's "suspected x87-vs-SSE double-rounding" framing conflicts
with `dev/docs/spikes/2026-07-15-native-materialize/41-fp-model-x87-vs-sse.md` — a disassembly-based,
high-confidence finding (2026-07-15) that this build's `Engine.dll`/`Editor.dll` (2022 MSVC rebuild,
`/arch:SSE2`) contain **zero** `fldcw`/`fnstcw` and near-zero x87 arithmetic anywhere in `.text`; the
CSG/geometry math is SSE2 scalar throughout with no 80-bit intermediates. So x87 extended-precision
retention is very likely NOT what's happening here — the residual is more likely an unreplicated
operation-order or register-allocation difference in the real compiled `FLinePlaneIntersection`/
`SafeNormal` chain. This does not change the "not fixed" conclusion or the next step below; it only
retires one candidate explanation so the eventual gdb single-step doesn't spend time confirming/
ruling out x87 registers specifically.

## Next step for whoever picks this up

Single-step the editor's real `FVector::SafeNormal` (`Core.dll 0x51090`) and the `FPoly` clip's
`FLinePlaneIntersection` call for this exact `162->275`/`275->273` pair under `gdb`, reading the FPU
stack/registers between the two calls, to confirm or rule out x87 extended-precision carry-over as
the actual mechanism. If confirmed, the fix is a genuine widening of the relevant intermediate(s) to
match — NOT a heuristic. Island's ladder cannot advance past N=332 until this closes; there is no
other known blocker past it (N=1..331 all byte-exact).

## 2026-09-12 (3rd pass) — narrowed to `SafeNormal`'s own FPU precision; live confirmation blocked by host disk

Full writeup in `unatco-n-226-leaf-12-gets-a-permeating-light157` (same mechanism, second
reproducer, worked in one session so it isn't duplicated here). Summary: fresh from-scratch
disassembly (not re-trusting the earlier writeup) confirms `FLinePlaneIntersection` (`Engine.dll
0x101507c0`) and the `FPlane(A,B,C)` cross-product ctor (`core.dll 0x1000b440`) are both bit-exact
with native's Rust port — no reordering bug left in either. The one function left that could
genuinely diverge is `FVector::SafeNormal` (`core.dll 0x10051090`, called from the `FPlane` ctor to
normalize the clip plane): it disassembles to real x87 (`call sqrt; fstp/fld/fld1/fdivrp/fstp`), and
a whole-`.text` census of `core.dll` and `D3D9Drv.dll` (this build's render driver) — DLLs spike 41
never covered — finds zero `fldcw`/`fnstcw` in either, same as `Engine.dll`/`Editor.dll`. So nothing
anywhere in this build ever sets the x87 precision-control field, meaning it runs at whatever the
process inherited at creation — plausibly the x87 hardware-reset default (PC=`11`, 64-bit extended),
not the PC=`10`/53-bit ("double") precision `safe_normal()`'s Rust model assumes. This is a real,
previously-unexamined candidate (distinct from the "x87 vs SSE in the CSG math" question spike 41
already answered), but still UNCONFIRMED: a probe script
(`dev/docs/spikes/2026-09-12-safenormal-fpu-precision/harness/fctrl_probe.py`, one gdb breakpoint,
reads `$fctrl` at `SafeNormal` — no single-stepping, no need to reproduce this item's exact
`162->275` crossing) is written but could not be run — this worktree has no wine-based debug-editor
image, and building one failed TWICE on this host with disk driven to 0 bytes free during the final
containerd layer-export step (from 6.0 GB and then 7.4 GB free, both times on the same step, for a
1.05 GB image) — a hard host limit, not a fixable retry. Cleaned up after each attempt; host disk
restored to ~7.4 GB free. Next step for whoever has working infra: run `fctrl_probe.py` against any
small cached subset and read `$fctrl` — `0x037f` confirms, `0x027f` refutes.

## 2026-09-13 — probe run; hypothesis REFUTED

`dx-lum-uned-dbg:latest` now exists (cached from a prior session). Ran `fctrl_probe.py` against the
cached Island N=332 subset (`_scratch/actor-parity/01_nyc_unatcoisland/N332/...`) — fixed one stale
bug first (`ROOT = Path(__file__).resolve().parents[4]` pointed at `dev/`, not the repo root; changed
to `parents[5]`). 30/30 `SafeNormal` hits report `fctrl=0x27f` — PC=`10` (double, 53-bit), the value
that refutes the hypothesis. `SafeNormal`'s real sqrt+reciprocal chain runs at exactly the precision
`fpoly.rs::safe_normal`'s Rust `f64` model already assumes; there is nothing to widen. No code change.

Full writeup: `dev/docs/spikes/2026-09-12-safenormal-fpu-precision/spike.md`. The x87-precision line of
inquiry is closed for both this item and `unatco-n-226-leaf-12-gets-a-permeating-light157`. The real
mechanism behind the sub-ULP tie is still open; it needs single-stepping the real
`SafeNormal`/`FLinePlaneIntersection` chain at the exact `162->275`/`275->273` crossing and diffing
intermediate register values against native's own trace, not another control-word read. Not fixed, no
mask; ladder still bails at N=332.

## 2026-09-13b — hex-precision live capture: the crossing's INPUTS are not bit-identical

Every prior capture (this item and its sibling) compared vertex values printed with ~9 significant
decimal digits, which is enough to round-trip an `f32` uniquely — but nobody had actually diffed the
two sides' raw bit patterns for this exact crossing's ARGUMENTS, only their formulas (disassembly)
and FPU state (the fctrl probe). Did that now: `dev/docs/spikes/2026-09-13-crossing-vertex-live-capture/`,
a live gdb capture of `FPlane::FPlane` and `FLinePlaneIntersection` dumping every argument as a raw
hex `u32`, gated on `FEditorVisibility::ActorVisibility`'s own actor match (a naive value-conditioned
breakpoint on either hot CSG primitive wedges the whole editor — see the spike for why).

Result: **the inputs are NOT bit-identical.** Native's own trace (`UEDCLI_PERM_TRACE_EDGE=162-275`,
extended with hex output this session) shows the decisive `FLinePlaneIntersection` call as
`P1=(-4495.99951171875, 3628.0, 192.0)`, `P2=(-4495.99951171875, 4080.0, 192.0)` — `P2.y` the exact
grid value `0x457f0000`. The live editor's OWN call at this exact crossing (`LPI_ENTRY hit=1120` in
the capture log, `P1`/`Normal`/`W` all matching native's trace, confirming this is the right call)
has `P2.y = 0x457f0001` — `4080.000244140625`, one ULP off the grid value native assumes.

`P2` is a **Pass-B portal-quad corner** (`zones.rs::collect_leaf_portals` → `build_infinite_fpoly` +
`make_portals_clip`), not a raw `Model.Point` — a SEPARATE reconstruction from the final saved
package's Points table that earlier sessions confirmed byte-identical (`model_dump.py`). That
confirmation says nothing about whether the transient portal vertex `ActorVisibility` actually
consumes during `MAP REBUILD` matches the final saved value, and it doesn't, here, by 1 ULP.

`make_portals_clip`'s own crossing formula (`fpoly.rs::line_plane_intersection`, the OTHER
`FLinePlaneIntersection` overload, `Engine.dll 0x1506f0`, distinct from `permeating_lights.rs`'s
own copy at `0x101507c0`) was independently disassembled fresh this session and is ALSO bit-exact
against native's Rust port. So this isn't a wrong formula in Pass B either — the same "right
formula, right precision, still a sub-ULP residual" shape recurs one level upstream of where every
prior session looked, which is new evidence for a genuinely low-level (codegen/register-allocation)
effect rather than anything specific to the permeating-light beam clip.

**Not fixed, no mask.** The root is now one level further back: whatever crossing inside Pass B's
own ancestor-plane clip loop first produces `y=4080.00024` instead of `4080.0` for this vertex, not
yet captured. Full writeup + next step: `dev/docs/spikes/2026-09-13-crossing-vertex-live-capture/spike.md`.

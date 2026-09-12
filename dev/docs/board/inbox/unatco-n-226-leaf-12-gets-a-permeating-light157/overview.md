+++
priority = "p2"
kind = "debug"
summary = "UNATCO is byte-exact N=1..225 and bails at N=226: world leaf 12's permeating-light run carries Light157, which UED22 leaves out. Root-caused (2026-09-12) to the SAME unresolved mechanism as island-n-332-leaf-273-permeating-light-vertex-tie: native's FLinePlaneIntersection lands the crossing exactly on a shared portal vertex (a true tie); a live editor capture of the identical crossing lands ~1 ULP off it. Not fixed, no mask. 2026-09-12 (2nd pass): fresh disassembly confirms FLinePlaneIntersection and the FPlane(A,B,C) cross-product ctor are bit-exact ports; the one place left that could diverge is FVector::SafeNormal's real x87 sqrt/reciprocal chain (core.dll, never covered by the Engine.dll/Editor.dll-only spike-41 census) running under an unconfirmed FPU precision-control setting. Live gdb confirmation blocked by this host's docker/containerd disk limits (see below); still open."
spikes = ["dev/docs/spikes/2026-09-07-gather-box-verdict/", "dev/docs/spikes/2026-09-12-safenormal-fpu-precision/"]
+++

# UNATCO N=226 — leaf 12 gets a permeating `Light157` UED22 leaves out

Found 2026-09-07 walking the ladder forward after the gather zone-retire fix took UNATCO from N=162
to N=225 (`oceanlab-n48-world-model2-lightbits-differ-on`).

`parity_gate.py`: one failure, `BODY model model2`.

    bbox sphere vectors points numsharedsides zones bounds leafhulls lightbits tail   SAME
    nodes surfs verts                                                                masked only
    leaves lightmap lights                                                           REAL

- Leaf 12's run is `[Light318, Light157, Light156]` in native and `[Light318, Light156]` in UED22.
  `Model.Lights` is 2953 vs 2952; every later leaf differs only by the resulting `+1` `iPermeating`
  shift, and the `LightMap` records only by the same shift.
- The per-surf half is clean: `lightbits` is byte-identical (211650 bytes) and
  `harness/lightbits_diff.py` reports **0 differing records**.

## Its two siblings are fixed; this one survived that fix (2026-09-07)

`oceanlab-n-93-leaf-96-gets-a-permeating` and `island-n-123-world-model2-leaf-permeating-light` were
the same shape and are both closed: the beam clip took its crossing vertex from
`alpha = dp/(dp-ds)` where `SplitWithPlaneFast` calls `FLinePlaneIntersection`, and a crossing
landing exactly on a grid coordinate collapsed the next hop's clip edge to zero length
(`wanchai-n45-leaf-20-permeating-light-over-included`, spike
`dev/docs/spikes/2026-09-07-gather-box-verdict/`). **Re-measured after that fix, this one is
unchanged** — leaf 12 still carries `Light157` (`Model.Lights` 2953 vs 2952, per-surf runs 0
differing), so it is a second, independent case.

The method that cracked WanChai applies directly: capture the editor's own flood with
`2026-09-07-gather-box-verdict/harness/actor_visibility_probe.py` and diff it with
`perm_flood_diff.py` to find the one crossing native takes that the editor does not — WanChai's
capture had 10 of 11 lights already identical, so the diff is narrow. UNATCO N=226 is bigger
(147 leaves) but the probe cost scales with the flood, not the level.

## Root cause (2026-09-12) — same unresolved mechanism as Island N=332, second reproducer

`perm_flood_diff.py` against a live `actor_visibility_probe.py` gdb capture of the same N=226 subset
(same method as `island-n-332-leaf-273-permeating-light-vertex-tie`) narrows it to one crossing:
`Light157` (li=6) marks leaf 12 in native and not in the editor; the one crossing native takes and the
editor does not is `(13, 12)`.

The decisive clip poly is the beam entering leaf 13 via leaf 102 (`AV_REC from=102 to=13 nv=5`). Both
sides compute a 5-vertex poly whose last two vertices should be the same shared corner
`(320.000061, -288.000153, 368)` (this vertex is a corner of BOTH leaf 13's own face poly and the
102-side clip boundary — a genuine multi-portal vertex coincidence, same shape as Island's `T2`/`C1`):

    native (UEDCLI_PERM_TRACE_EDGE=102-13): ... (320.00006, -288.00015, 368) (320.00006, -288.00015, 368)   -- EXACT duplicate, 0 ULP apart
    editor (live gdb capture, AV_REC from=102 to=13 nv=5):
        ... (320.000031, -288.000153, 368) (320.000061, -288.000153, 368)                                   -- ~1 ULP apart, NOT a duplicate

Native's `FLinePlaneIntersection` port lands the crossing bit-for-bit ON the shared vertex, collapsing
the poly's last edge to exact zero length; `clip_beam`'s `safe_normal` then reads that edge as
degenerate and skips it as "no constraint" for the next hop (`13->12`), so the beam is under-clipped
and reaches leaf 12. The editor's own capture of the identical crossing lands about 1 ULP off the same
vertex — not a tie — so it keeps a real (if tiny) constraining edge there and its flood never reaches
leaf 12 with this light. Confirmed via `UEDCLI_PERM_TRACE=6 UEDCLI_PERM_TRACE_EDGE=13-12`/`=102-13` on
native, `actor_visibility_probe.py --verts 8` on the editor.

This is the same phenomenon `island-n-332-leaf-273-permeating-light-vertex-tie` describes: a genuine
geometric near-coincidence where native's strict single-precision reimplementation of the documented
`FLinePlaneIntersection` formula reproduces its own output exactly, but the real compiled editor code
running "the same" formula lands a different residual by about 1 ULP — a register-level effect not yet
reproduced by the disassembly-derived formula. Per that item and the campaign's prime directive, this
is NOT fixed here: forcing a fix without confirming the actual mechanism risks moving the many
now-passing near-tie cases (N=8, N19, N45, N93, N123, N153, N226's own siblings) that already depend on
the current formula. No mask/exclusion added — the gate still reports N=226 as a real FAIL.

**Correction to the Island item's "x87 vs SSE" framing.** `dev/docs/spikes/2026-07-15-native-materialize/41-fp-model-x87-vs-sse.md`
(disassembly, 2026-07-15, high confidence) already established that this exact build's `Engine.dll`
and `Editor.dll` (2022 MSVC rebuild, `/arch:SSE2`) contain **zero** `fldcw`/`fnstcw` and near-zero x87
arithmetic anywhere in `.text` — the CSG/geometry math, including `FPlane::PlaneDot`, is SSE2 scalar
throughout, with no 80-bit intermediates. So "x87 extended-precision retention" is very likely NOT the
mechanism behind either this item or Island N=332's sub-ULP residual; a more likely candidate is an
unreplicated operation-order or register-allocation difference in the real compiled
`FLinePlaneIntersection`/`SafeNormal` chain (spike 41's own point 2: "the remaining parity work is
operation-order fidelity, not precision"). Confirming the actual mechanism still needs the same
register-level gdb single-stepping the Island item calls for — not done here.

## Repro

    ladder_run.py --dx dev/games/deusex/Maps/03_NYC_UNATCOHQ.dx --from 226 --to 226 --keep-native
    model_dump.py <native_N226.dx> <ref_N226.dx> Model2

    # live capture + diff (this session's finding)
    actor_parity.py --dx <unatco.dx> subset 226   # re-materialize the N226 subset scaffold
    dev/docs/spikes/2026-09-07-gather-box-verdict/harness/actor_visibility_probe.py \
        --trunk _scratch/actor-parity/03_nyc_unatcohq/N226/maps/03_nyc_unatcohq --verts 8 --out <log>
    dev/docs/spikes/2026-09-07-gather-box-verdict/harness/perm_flood_diff.py \
        <native UEDCLI_PERM_TRACE=all log> <log> --light 240.9201,-373.26294,330.79813

## 2026-09-12 (2nd pass) — the "same formula" claim re-verified by fresh disassembly; the real gap narrows to one function's FPU precision

Re-disassembled all three functions in the chain from scratch (`uned/UED22/{Engine,core}.dll`, image
base `0x10000000`), independent of the earlier session's writeup, to check the "native's formula is
disassembly-verified correct, only a register-level effect is missing" claim directly rather than
trust it secondhand.

- **`FLinePlaneIntersection`** — the real call site is `SplitWithPlaneFast`'s `call 0x101507c0`
  (`Engine.dll`, confirmed by disassembling `SplitWithPlaneFast` itself and finding this exact call
  at `0x1015214b`, args `(out, prevVertex, curVertex, Plane)` — the OTHER candidate RVA some earlier
  notes cite, `0x1506f0`, is a different 5-argument overload taking `Base`/`Normal` as separate
  vectors, not called from here). Full instruction-level decode confirms it is **bit-exact** with
  `uedcli-native/src/permeating_lights.rs::line_plane_intersection`: numerator = `W -
  ((P1.y*N.y + P1.x*N.x) + P1.z*N.z)` (note the y,x swap, then +z — matches instruction for
  instruction), denominator = `(D.x*N.x + D.y*N.y) + D.z*N.z` (plain x,y,z order) where `D = P2-P1`.
  No reordering left to find here.
- **`FPlane::FPlane(A,B,C)`** (`core.dll 0x1000b440`, `clip_beam`'s `FPlane(Light, clip[j],
  clip[jPrev])`) — decoded fully. The cross product is `(B-A) x (C-A)` with the standard formula
  (`cross.x = (B-A).y*(C-A).z - (B-A).z*(C-A).y`, etc.), which is bit-exact with
  `uedcli-native/src/model.rs::Vec3::cross`. Its normalize call is `call 0x10051090` — i.e. it calls
  **`FVector::SafeNormal`, in `core.dll`, not `Engine.dll`/`Editor.dll`**.
- **`FVector::SafeNormal`** (`core.dll 0x10051090`) — decoded fully. It is genuinely **x87**, not SSE:
  `cvtps2pd` (widen SquareSum to double) -> `call sqrt` -> `fstp dword` (round to f32) -> `fld dword`
  (reload) -> `fld1` -> `fdivrp st(1)` (1.0/root, x87) -> `fstp dword` (round to f32) -> scale x/y/z in
  SSE. This matches the pre-existing doc comment in `fpoly.rs::safe_normal` exactly (independently
  re-verified, not taken on faith).

**The correction this adds:** spike 41 (`41-fp-model-x87-vs-sse.md`) is still right about what it
actually measured — `Engine.dll`/`Editor.dll`'s CSG/geometry arithmetic (`PlaneDot`,
`SplitWithPlane[Fast]`, `CalcNormal`) is genuinely SSE2, no x87, no FMA. But that census never covered
`core.dll`, and `SafeNormal` — the one function in this whole chain that isn't pure add/mul/sub — lives
in `core.dll` and does use x87. This isn't a contradiction of spike 41, it's a gap it never claimed to
close. Re-running `fp_scan_text.py` against `core.dll` AND `D3D9Drv.dll` (this build's own render
driver, the other plausible place something could set FPU state) finds **zero** `fldcw`/`fnstcw` in
either — so now all four DLLs in the relevant code path (`Engine.dll`, `Editor.dll`, `core.dll`,
`D3D9Drv.dll`) are confirmed to never touch the x87 precision-control (PC) field.

**The hypothesis this supports:** since nothing ever sets PC, the FPU runs at whatever PC the
process/thread inherited at creation. The x87 hardware-reset default is `0x037F` — PC=`11` (64-bit
EXTENDED mantissa) — and under Wine on Linux, absent an explicit `_controlfp` call anywhere (which the
census rules out for these four DLLs), that default is very likely what persists. `safe_normal()`'s
current Rust model computes the sqrt and the `1.0/root` reciprocal each in `f64` (53-bit) and rounds
ONCE to `f32` at the very end — i.e. it assumes PC=`10`, not PC=`11`. If the real hardware state is
PC=`11`, each of those two x87 ops carries a genuinely wider (64-bit-mantissa) intermediate before its
own `fstp dword` rounds it to `f32` — a different double-rounding path than native's, and exactly the
kind of sub-ULP effect that could tip a true numerical tie one way in native and the other way in the
real editor, which is the whole shape of this divergence.

**Attempted live confirmation, blocked by host infra (not by the science).** Wrote
`dev/docs/spikes/2026-09-12-safenormal-fpu-precision/harness/fctrl_probe.py`: a single gdb breakpoint
at `SafeNormal`'s entry (`core.dll+0x10051090`) that reads `$fctrl` (gdb's x87 control-word
pseudo-register) plus the input vector, and a second at `core.dll+0x1005112f` (just before the
callee's `pop esi`, after all three output floats are stored) that reads `$fctrl` plus the output — no
single-stepping needed, and no need to reproduce this item's specific `(102,13)` crossing: the PC
field can't change mid-process (nothing ever writes it), so ANY `SafeNormal` hit during a real MAP
REBUILD settles it. Could not run it: the wine-based debug-editor image (`ued-x86-runtime` + gdb) does
not exist in this worktree, and building it **twice** failed with the host's disk driven to **0 bytes
free** during the final containerd layer-export/unpack step — once starting from 6.0 GB free, once
from 7.4 GB free, both times on the same step, despite the produced image being only 1.05 GB. That is
a hard limit of this host's rootless-docker/containerd overlay extraction, not a marginal one-off;
retrying a third time would not be expected to behave differently. Cleaned up fully after each
attempt (`docker rmi`, `docker builder prune -af`); the host disk is back to its starting ~7.4 GB
free / 88% used.

**Next step for whoever has working editor-container infra:** run `fctrl_probe.py --trunk <any cached
subset trunk>` (any small N works — e.g. an existing N=8/N=19 scaffold; N=226 does not need to be
reproduced) and read the reported `$fctrl`. `0x027f`/PC=`10` refutes this hypothesis (the residual is
something else, drop this line of inquiry); `0x037f`/PC=`11` confirms it. If confirmed, the fix is
porting `safe_normal`'s sqrt+reciprocal through genuine 64-bit-mantissa arithmetic (not a heuristic —
a real precision-model correction, e.g. an x87-equivalent extended-precision emulation) instead of
`f64`, then re-verifying it does not move any of the already-passing near-tie cases this item and
`island-n-332-leaf-273-permeating-light-vertex-tie` list (N=8, N19, N45, N93, N123, N153, and this
item's own N=226 siblings) before trusting it against N=226/N=332 themselves.

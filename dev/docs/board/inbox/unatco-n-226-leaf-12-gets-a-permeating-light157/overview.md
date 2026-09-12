+++
priority = "p2"
kind = "debug"
summary = "UNATCO is byte-exact N=1..225 and bails at N=226: world leaf 12's permeating-light run carries Light157, which UED22 leaves out. Root-caused (2026-09-12) to the SAME unresolved mechanism as island-n-332-leaf-273-permeating-light-vertex-tie: native's FLinePlaneIntersection lands the crossing exactly on a shared portal vertex (a true tie); a live editor capture of the identical crossing lands ~1 ULP off it. Not fixed, no mask."
spikes = ["dev/docs/spikes/2026-09-07-gather-box-verdict/"]
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

# Crossing-vertex live capture — the N=332/N=226 tie is an upstream INPUT mismatch, not a beam-clip rounding bug

Both `island-n-332-leaf-273-permeating-light-vertex-tie` and
`unatco-n-226-leaf-12-gets-a-permeating-light157` were blocked on one hypothesis: native's
`permeating_lights.rs::line_plane_intersection`/`safe_normal` compute a beam-clip crossing that
lands EXACTLY on a shared portal vertex (0 ULP), while a live capture of the same crossing in the
real editor lands ~1 ULP off it — same formula (disassembly-verified), same FPU precision-control
(fctrl probe, 2026-09-12), so the residual was attributed to an unidentified register-level effect
inside that one function.

This session re-verified the INPUTS first, in HEX (not the ~9-significant-digit decimal every prior
capture used) — the one check `NATIVE-MATERIALIZE.md`'s task brief flagged as cheapest and most
likely to resolve this without any single-stepping. **The inputs are NOT bit-identical.** The
decisive crossing's formula and precision were never the problem; one of its two input vertices
differs from what native assumes, and that difference originates in an earlier pass (portal
construction), not in the permeating-light beam clip at all.

## Method

`harness/crossing_probe.py`: a live gdb capture of `FPlane::FPlane(A,B,C)` (`core.dll 0x1000b440`,
confirmed via the Editor.dll import table: `??0FPlane@@QAE@VFVector@@00@Z`) and
`FLinePlaneIntersection` (`Engine.dll 0x101507c0`, the overload `permeating_lights.rs` ports),
dumping every argument and result as a raw hex `u32` bit pattern.

v1 conditioned both breakpoints directly on argument values matching native's own
`UEDCLI_PERM_TRACE_EDGE`-captured hex (see below) and wedged the live editor: a raw `E8`-opcode scan
of `Engine.dll`'s `.text` (`_scratch/find_callers.py`, not committed — trivial re-derivation) found
`FLinePlaneIntersection` has only 2 static callers, one of them `SplitWithPlaneFast`, which itself
has 3 *more* callers inside `Engine.dll` besides the permeating-light beam clip — so an always-armed
conditional breakpoint on either function pays a ptrace stop for every CSG split in the whole
332-actor subset, not just the permeating flood. Fixed by gating both breakpoints on/off via a
third, cheap, unconditional breakpoint at `FEditorVisibility::ActorVisibility`'s own entry (Editor.dll
`0x100a6edd`, the same address `actor_visibility_probe.py` already uses successfully) — enabled only
while the current flood's `Actor*` matches the target light, bounding the live window to that one
light's own traversal (~316 `ActorVisibility` hits instead of the whole `MAP REBUILD`).

v2 also removed the value-based pre-filter entirely (dumps every `FPlane`/`FLinePlaneIntersection`
call in the now-small armed window) after v1's exact-order match never fired once — turned out to be
a `printf` format-string bug (see below) that aborted the whole gdb batch after the very first hit,
not a real absence of matches.

## The target crossing (Island N=332, Light124, li=34)

Native's own `UEDCLI_PERM_TRACE=34 UEDCLI_PERM_TRACE_EDGE=162-275` trace (hex-extended this session,
`permeating_lights.rs` `PERM_PLANE`/`PERM_CROSS` prints) gives the decisive computation exactly:

    PERM_PLANE j=1 light=(c58d82c6,45890d69,4280bdc9) a=(c58c7fff,457f0000,c30c0001)
      b=(c58c7fff,457f0000,43400000) normal=(3f7e941b,3dd784f6,00000000) w=c57c9ae2
    PERM_CROSS prev=(c58c7fff,4562c000,43400000) cur=(c58c7fff,457f0000,43400000)
      dp=c23e4340 ds=00000000 normal=(3f7e941b,3dd784f6,00000000) w=c57c9ae2
      -> crossing=(c58c7fff,457efffb,43400000)   [y = 4079.998779296875]

i.e. `P1 = (-4495.99951171875, 3628.0, 192.0)`, `P2 = (-4495.99951171875, 4080.0, 192.0)` (`P2.y` is
the exact grid value `0x457f0000`), plane `Normal = (0.9944474101066589, 0.1052340716123581, 0.0)`,
`W = -4041.68017578125`.

## The live capture — `logs/crossing-probe.log`, `LPI_ENTRY hit=1120`

    LPI_ENTRY hit=1120 out=0x145b8e8
      P1=(c58c7fff,4562c000,43400000) [-4495.99951,3628,192]
      P2=(c58c7fff,457f0001,43400000) [-4495.99951,4080.00024,192]
      Normal=(3f7e941d,3dd78502,00000000) [0.994447529,0.105234161,0]
      W=(c57c9ae2) [-4041.68018]

`P1`, `Normal`, and `W` all match native's trace (the sign of `Normal`/`W` on the matching
`FPLANE_ENTRY hit=1053` differs because that capture's `B`/`C` args land in the opposite order from
what `permeating_lights.rs`'s doc comment assumes — `FPlane(A,B,C)`'s cross product negates under a
`B`/`C` swap, and a plane's `Normal`/`W` negating together leaves `FLinePlaneIntersection`'s `t`
parameter algebraically UNCHANGED (both the numerator and denominator flip sign), so this ordering
mixup is cosmetic, not the bug — confirmed by `LPI_ENTRY`'s own `Normal`/`W` matching native's
sign once the ordering settles for the actual `FLinePlaneIntersection` call).

**`P2` does not match.** Native assumes `P2.y = 0x457f0000` (`4080.0` exactly — the grid-aligned
value). The live editor's own `P2.y` at this exact call is `0x457f0001` (`4080.000244140625`) — one
ULP off the grid value, in the SAME direction that produces the editor's ~1-ULP-nonzero crossing
(vs. native's exact 0-ULP tie) the two board items describe.

## What this means

- The divergence is **not** in `FLinePlaneIntersection`/`SafeNormal`'s own arithmetic — both are
  re-confirmed bit-exact via a *fresh* disassembly this session (independent of the two board items'
  prior passes), and now also empirically: given matching inputs, they would produce matching
  outputs, and the one input that doesn't match isn't computed by these functions at all.
- `P2` is a **portal-quad corner**, not a raw `Model.Point` — it comes from
  `zones.rs::collect_leaf_portals` (Pass B: `build_infinite_fpoly` + `make_portals_clip`), which is a
  SEPARATE reconstruction from the final, saved `Model.Points` array. The board items' earlier claim
  that "162->275's face poly...is byte-identical to UED22's own `Model.Points`" checked the *final
  saved package's* Points table (via `model_dump.py`) — it says nothing about whether the LIVE,
  transient portal vertex `ActorVisibility` actually consumes during `MAP REBUILD` matches that final
  value bit-for-bit. It doesn't, by 1 ULP, at least for this vertex.
- `zones.rs::make_portals_clip` calls `fpoly.rs::split_with_plane` → `fpoly.rs::line_plane_intersection`
  (the OTHER `FLinePlaneIntersection` overload, `Engine.dll 0x1506f0`, 5-argument
  `Base`/`Normal`-separate form — distinct from `permeating_lights.rs`'s own copy at `0x101507c0`).
  This overload was independently disassembled fresh this session and is ALSO bit-exact against
  `fpoly.rs`'s Rust port, instruction for instruction (same `(Base-P1)·N / (P2-P1)·N` grouping,
  same summation order once accounted for IEEE-754 addition's exact commutativity over two operands).
  So Pass B's own crossing formula isn't wrong either — the same "right formula, right precision,
  still a sub-ULP residual" shape recurs here, one level upstream of where every prior session
  looked.

**This is new, actionable evidence, not a new independent bug class**: the same unexplained
register-level residual the two board items already flag as the final open question
(`FVector::SafeNormal`'s FPU precision was checked and refuted, 2026-09-13) evidently isn't confined
to `permeating_lights.rs`'s own beam clip — it recurs at (at least) two independently-verified-correct
call sites that both ultimately compute a line/plane crossing. That argues more strongly for a
genuinely low-level (codegen/register-allocation) effect over anything specific to the permeating-
light module, and narrows where a future register-level single-step session should look: Pass B's own
`SplitWithNode`/`FLinePlaneIntersection` chain for the SAME y≈4080 wall plane, not (only) the
permeating-light flood's beam clip.

## What this does NOT do

- It does not identify the actual mechanism (still needs single-stepping the real compiled
  `FLinePlaneIntersection`/`SafeNormal`/`SplitWithNode` chain at the Pass-B crossing that PRODUCES
  this `P2` vertex — one level further upstream than this session traced; `P2` at `y=4080.00024` is
  itself almost certainly the output of an earlier crossing inside `make_portals_clip`'s own
  ancestor-plane clip loop, not a raw stored point).
- It does not propose or apply a fix. No plausible faithful fix is evidenced yet (per
  `NATIVE-MATERIALIZE.md`'s prime directive: measure and report, don't guess).
- Both board items' ladders remain blocked at Island N=332 / UNATCO N=226; no ceiling moved.

## Bug found and fixed in the harness itself

v1's `FPLANE_EXIT` breakpoint had `printf "FPLANE_EXIT  this=%#x "` with a `%#x` placeholder and NO
argument — gdb's `-batch` mode aborts the whole script on a malformed `printf`, which is why the
first (value-conditioned) run captured exactly one `FPlane` hit and then silently detached with no
further output. Fixed in the same commit that removed the value pre-filter.

## Next step for whoever picks this up

Capture Pass B's own crossing computation for this SAME vertex (probe `fpoly.rs::line_plane_intersection`
at `Engine.dll 0x1506f0`, called from `FPoly::SplitWithNode` inside `MakePortalsClip`, Editor.dll
`~0xa9970`) with the SAME hex-precision method, to find which ANCESTOR-PLANE crossing first produces
`y=4080.00024` instead of `4080.0` in the live editor. That is the actual root, one level further back
than this session traced. If that crossing's own inputs (its own P1/P2/plane) turn out to be
bit-identical to native's, THEN single-stepping is the only remaining option (as both board items
already conclude) — but it should be done at THAT crossing, in Pass B, not in the permeating-light
beam clip this session's capture clears of blame.

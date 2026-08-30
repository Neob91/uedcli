+++
priority = "p2"
kind = "debug"
summary = "Confirmed line_clear (not lumel_axes) causes Wanchai's bits-only shadow divergence. Round 3 found the round 1-2 target function (target+0x5b0) was wrong; round 4 pinned the real crossing formula (t'=de/(de-ds)) and measured it regressing both levels when grafted onto native's alternating recursion -- reverted. Round 5 explains why: point2 (the query's lumel_pos) stays bit-identical across 4 successive genuine crossings. Round 6: full disassembly of the real walker (0x17ce190) fully resolves the recursion shape (one genuine near-recursion replacing point1, tail-loop far-continuation replacing point2) AND finds a real, live-confirmed +/-0.001 epsilon band (not 0.0). Round 7: pinned the full state-machine (near-call incoming state, far-continuation state) via live capture of a CLEAR ray, verified perfectly (122/122 mechanical checks, 4/4 real rays incl. exact node-path replication) -- then found, via a broad offline sweep against real golden bits, a large-scale regression (81-92%, well below the ~99% baseline) that the earlier small-sample verification missed entirely. A FRONT/BACK state-formula swap only partially helps one region and hurts another (ruling out a simple sign error); the leading hypothesis (an unmodeled zone-transform branch gated on a context pointer) was LIVE-TESTED and REFUTED same round (edx=0 for all 4 sampled rays of the broken light, same as the working one). Root cause still open. Reverted cleanly -- linecheck.rs untouched, git diff empty, 90/90 tests green."
depends-on = ["getvisiblesurfs-wanchai-run-gap-root-cause"]
spikes = ["dev/docs/spikes/2026-08-29-unatco-repart-live-diff/"]
+++

# line_clear shadow-ray algorithm gap: found real editor function, not fully decoded

Resumes `native-light-apply-bake-where-it-stands-and` gap 2 / `getvisiblesurfs-wanchai-run-gap-root-
cause`'s "still open" note: the "bits differ, run+grid+pan/scale all agree" bucket (255 Wanchai
records) survived after `lumel_axes` was chased and REFUTED (2026-08-30, same day, earlier). This
round investigated `linecheck::line_clear` (`uedcli-native/src/linecheck.rs`) as the next suspect,
per the coordinator's task.

## Result 1 (offline, decisive): `line_clear` does NOT reproduce the editor's real bit even when fed
## the editor's own real tree and real ray endpoints -- confirms a genuine algorithm gap, not a
## geometry residual

New harness `dev/docs/spikes/2026-08-29-unatco-repart-live-diff/harness/line_clear_algorithm_check.py`.
Method (no live gdb needed for this part -- the editor's real per-lumel BSP tree is already serialized
into the lit golden `.dx`, since `LIGHT APPLY` never rebuilds BSP):

1. Ported `linecheck::line_clear` verbatim into Python, f32-rounding every op like
   `lumel_axes_live_check.py` already does.
2. For "bits-only" records (grid+run+pan/scale match, bits differ), recomputed the exact ray
   endpoints (`p`, `light.location`) from the golden's own surface/record data -- the inputs
   `bits_only_input_check.py` already showed are bit-identical between native and golden for this
   bucket.
3. **Self-consistency control (mandatory before trusting anything else):** ran the Python port
   against NATIVE's own tree/inputs and compared to native's own real stored bit (the real Rust
   `line_clear`'s real output). **40/40 agree** -- the port is a faithful, bug-free translation.
4. **The actual test:** ran the SAME Python port against the GOLDEN's own real tree/inputs (parsed
   straight from `_scratch/wanchai-relight-2026-08-29/golden.dx`, confirmed-provenance per the
   findings ledger) and compared to the golden's own real stored bit. **20/40 sampled mismatches
   disagree** (16/20 in the direction "line_clear says BLOCKED, editor says CLEAR"; 4/20 the reverse).

Conclusion: `line_clear`, exactly as coded and verified faithful to native's own real output, does
**not** reproduce the editor's real per-lumel decision even given the editor's exact real BSP tree.
This rules out "it's just native's own slightly-different geometry" and confirms a genuine algorithm
gap in `line_clear` itself (or the position walk feeding it) -- not the tracked Points/geometry
residual.

Rebuilt native fresh on the current tree first (`light_spotcheck_wanchai.py`,
`dev/docs/spikes/2026-08-29-unatco-repart-live-diff/logs/light-spotcheck-wanchai-native.dx`):
3297/4530 (72.8%) byte-identical, matching the ledger's last measurement exactly -- confirms no
drift since the last round.

## Result 2 (live gdb, current build): found and disassembled the REAL editor function; REFUTES the
## old epsilon-tolerance hypothesis; does NOT explain the traced exemplar; full formula not decoded

Manually traced one concrete mismatch (`rec=14 light=Light42 v=3 u=0`, native/golden both computed
from the SAME confirmed-bit-identical inputs) through the Python `line_clear` port: the ray origin
`p=(1760.0, 1148.125, 191.875...)` sits ~0.0002uu off BSP node 4156's splitting plane (`x=1760`,
axis-aligned). `line_clear`'s strict `ds >= 0.0` test reads this as a "crossing" (ds=-0.0002,
de=+112.39), descends the tiny near-zero `[start,mid]` sub-segment first, and that sub-segment hits a
solid terminal -> BLOCKED, which short-circuits the whole ray to blocked even though the far segment
is genuinely clear. The pre-2026-08-14 (thus owner-flagged untrusted) doc
`spikes/2026-07-15-native-materialize/re-raw-zones/linecheck-oracle.md` claims the real editor's
zero-extent `LineCheck` uses a **±0.001 epsilon tolerance band** for this classification (`front when
both dists > -0.001`), which would have avoided this spurious split -- a plausible, concrete
hypothesis.

**Live-checked directly, per the owner's "verify freshness" instruction, rather than trusted:**

- New harness `dev/docs/spikes/2026-08-29-unatco-repart-live-diff/harness/linecheck_target_disasm.py`.
  Live gdb, current `uned/UED22` image, real Wanchai `LIGHT APPLY`, attached during a genuine run.
- Fresh static disasm (`rdis.py dis Editor 0x100a5900 0x160`, this session) located the real call
  site inside `illuminateSurf`'s per-lumel loop: `ecx = Level->Model; eax = Model's vtable; call
  dword ptr [eax+0x58]` -- independently re-derives the "Model vtable slot +0x58" claim from
  `sections/20-lighting-bake.md` §5 (also pre-2026-08-14, also now independently confirmed).
- Live-captured the REAL resolved call target: `target=0x17ce4c0` (this build's actual, relocated
  in-memory address -- confirms Editor.dll loads unrelocated at its file base 0x10000000, so this
  differs from any prior doc's RVA scheme, which used a different binary/base).
- Disassembled `0x17ce4c0` (the outer `UModel::LineCheck` dispatcher: NaN guards, resets a global at
  `0x18fbbb4`, branches on box-vs-zero-extent, ends up calling an inner function via `call
  0x17ce190`... **correction, see below** -- actually calls `0x17ce190` for extent-prep, then the
  REAL recursive walker is reached differently, see next) and the actual recursive per-node walker at
  `target+0x5b0` (`0x17cea70`, confirmed self-recursive: `call 0x17cea70` at `0x17ceb45`).

**Finding A -- REFUTES the epsilon-tolerance hypothesis.** The recursive walker's front/back
classification (`0x17ceaf1`/`0x17ceafc`, `comiss` + `setae`) is a **strict `>= 0.0`** compare with
**no epsilon band** -- bit-identical in kind to native's own `ds >= 0.0` test. The old doc's ±0.001
claim does not hold for this build's actual zero-extent shadow-ray classification. (The old doc may
be describing a genuinely different function/binary -- game `Engine.dll` collision `LineCheck`, not
the editor's `LIGHT APPLY` bake path -- or may itself be stale; either way it is REFUTED as the
mechanism for THIS bug, live, on the current tree.)

**Finding B -- ruled out for the traced exemplar, not eliminated in general.** The plane-dot itself is
computed via an SSE horizontal dot product with **pairwise summation** (`(a·x + b·y) + (c·z − w)`,
tree-reduced via `shufps`/`addps`/`movhlps`/`addss`), differing in **association** from native's
**left-to-right** scalar sum (`((a·x + b·y) + c·z) − w`). IEEE754 addition is not associative, so
these can differ at the ULP level near a boundary for an oblique plane. For the traced exemplar the
plane is axis-aligned (`b=c=0`), so the two association orders reduce to the identical two operands
and are provably bit-identical there -- this does NOT explain that specific case, but was not
re-checked against the other 19 sampled mismatches (some may hit oblique planes where this DOES
matter). Concrete, cheap next step: extend `line_clear_algorithm_check.py` to report each mismatch's
plane and flag which are axis-aligned vs oblique, then re-test the association-order hypothesis only
on the oblique subset.

**Finding C -- structural cross-validation.** The live-disassembled node layout matches the existing
`model.rs`/`bspcsg.rs` assumptions exactly: `FBspNode` stride confirmed 0x40, children at `+0x20`
(engine `iFront`)/`+0x24` (engine `iBack`), `NodeFlags` at `+0x37` (single byte) -- independently
re-derives, live, facts this codebase already assumed from other (some pre-2026-08-14) sources.

**Finding D -- NOT fully decoded, and this is where the round stopped.** The per-node "child selected
+ threaded state byte" logic (`0x17ceb02`-`0x17ceb7b`) uses a compact XOR/AND bit formula
(`new_state = ((front_flag XOR incoming_state) AND node_flags_byte) AND 1) XOR front_flag`) to
combine an incoming carried byte with the CURRENT node's raw `NodeFlags`. Algebraically this only
ever tests **bit 0** of `NodeFlags` (`NF_NOT_CSG = 0x01`) -- the `AND node_flags_byte` followed by
`AND 1` collapses to testing just that one bit, because the left operand is always a clean 0/1 value.
That leaves an **open, unresolved question**: native's own `is_csg` ORs THREE bits into the mask
(`NF_NOT_CSG | NF_NOT_VIS_BLOCKING(0x04, gated by extra_flags) | NF_IS_NEW(0x20)`), but this
compiled per-node formula as read appears to test only bit 0 -- so either (a) `NF_NotVisBlocking`/
`NF_IsNew` gating happens somewhere else in this function I have not located (the outer function, a
different branch, or a pre-filter on which nodes even enter this walk), or (b) my read of the
compiled logic has an error (SSE register reuse in this function is dense and error-prone to hand-
trace statically -- `ecx`/`dl`/`dh` get reloaded from different stack slots at several points and I
did not single-step to verify). **Did not attempt to resolve this further this round** -- per the
"log clearly and stop" guidance when one more static-read pass is unlikely to land it cleanly; the
reliable next step is a live, single-step gdb trace of the SAME known-mismatching ray
(`rec=14 light=Light42 v=3 u=0` on the current Wanchai golden, already isolated by
`line_clear_algorithm_check.py`) through this exact function, logging each call's
`(node_index, front0, front1, node_flags, incoming_state, selected_child, computed_new_state)` and
diffing against `line_clear_py`'s own trace for the identical input -- mechanical value comparison
instead of further hand-decoding of SSE-optimized asm.

## Round 2 (2026-08-30): static formula pinned, live single-step attempted and abandoned as too slow

Continuation task: a live single-step gdb trace of the exact known-mismatching ray (`rec=14
Light42 v=3 u=0`) through the recursive walker, to mechanically pin Finding D instead of hand-reading
more disassembly. Two outcomes:

**1. A from-scratch static hand-decode of the already-committed `linecheck-target-disasm.log`
independently reproduces Finding D's bit formula exactly, AND finds a new, likely-relevant
divergence Finding D didn't cover.** Full line-by-line SSE trace (every `shufps`/`movhlps`/`addps`
semantics worked out by hand) plus a fresh disasm of the CALLER (`illuminateSurf`'s call site,
`rdis.py dis Editor 0x100a5900 0x160`) to pin the argument convention: the call is
`Model->vtbl[0x58](extra_flags, lumel_pos, light_loc, 0, &out)`, `ecx`=Model, `extra_flags`∈{4,0x14}
matching `VIS_EXTRA_FLAGS`/`VIS_BRIGHT_CORNERS` exactly.

- **Bit formula**: `new_state = (((incoming_state XOR front_start) AND NodeFlags_byte) AND 1) XOR
  front_start` -- same as Finding D, independently re-derived (not copied from the prior entry).
- **NEW: the crossing-point `mid` uses a different, non-bit-identical formula.** Native computes
  `t=ds/(ds-de)`, `mid=start+(end-start)*t`. The editor instead computes `t'=de/(de-ds)` (a SEPARATE
  division) then `mid=end+t'*(start-end)` -- algebraically `t'≡1-t` (equal at both `ds=0`/`de=0`
  endpoints) but NOT bit-identical, since the two are independently-rounded divisions, not a computed
  `1-t`. For the traced exemplar (`ds`≈-0.0002, `de`≈112.39), native's `t=ds/(ds-de)` is dominated by
  the tiny, noise-sensitive `ds` (`t≈1.78e-6`), while the editor's `t'=de/(de-ds)` is dominated by the
  large, well-conditioned `de` (`t'≈0.9999982`) -- a real, structural reason the two engines could
  land on different `mid` points from the SAME `ds`/`de` pair, precisely in the near-zero-crossing
  regime this whole investigation is about. **Not live-confirmed.**

**2. The live single-step attempt hung and was killed -- the shared per-ray call site is hit too
often for a breakpoint-based approach to reach one specific ray in bounded time.** New harness
`linecheck_singlestep_rec14.py`: one gdb session, a conditional breakpoint at the fixed outer call
site (`0x100a5a04`) gated on the pushed lumel position matching the target ray, arming two further
breakpoints (`+0x92` for `ds`/`de`/flags per node, `+0xd5` for the computed `mid`) only once matched.
Ran 25 minutes with the log still stuck at `ORACLE_ATTACHED` (zero hits logged); `ps` inside the
container showed `gdb` at 99.6% CPU / 24:45 accumulated CPU-time and `unrealed.exe` actively running
at 53.6% -- confirming `LIGHT APPLY` genuinely ran and the breakpoint genuinely fired repeatedly, just
never yet on a match, because that call site is hit once per shadow-ray BIT computed across the WHOLE
level (order 10^5-10^6 for a level this size), each hit costing a full ptrace round-trip through
Docker. Killed (`docker kill`/`rm`) per the standing background-work rule rather than let it run
indefinitely. **Concrete next step, not attempted:** gate the fine-grained breakpoints behind a much
less-frequent checkpoint -- e.g. `illuminateSurf`'s own per-surface entry (~4530 hits total for
Wanchai, not per-bit), conditioned on the target surf's `iLightMap` index, arming the per-node
breakpoints only for that one surface's processing window.

## Round 3 (2026-08-30): the surf-gate WORKED -- and revealed round 1-2's target function was wrong

Implemented round 2's own proposed fix: gate the ray-level breakpoint behind `illuminateSurf`'s
per-surface entry (`Editor.dll 0x100a5010`, located fresh via a backward int3-padding scan, confirmed
live to take `iSurf` at `[ebp+0xc]`), armed only once `iSurf==4556` (the surf for record 14). This cut
the run from round 2's 25-minute hang to under a minute, reliably, across five reruns.

**The target ray reached neither of the two paths examined in rounds 1-2.** A 20-ray survey of the
same surface (no per-ray filter, logging every ray's outcome) showed ALL 20 sampled rays -- both
`result=0` and `result=1` cases -- take the SAME branch: `early_exit_0x17ce867`, reached via
`call 0x17ce190` returning non-zero, which the dispatcher then returns directly. `target+0x5b0` (the
function rounds 1-2 spent a whole round hand-decoding) is real, reachable code -- round 1's un-gated
capture did land inside it -- but is demonstrably NOT the path real per-lumel shadow rays for this
surface take. **This means round 2's `mid`-formula analysis, while a real and carefully-derived
static decode, was performed on a function not shown to be the one producing this bug -- an important
correction to the round's own premise, not a refutation of the analysis on its own terms.**

**Found and live-confirmed the actual recursive walker: `0x17ce190`.** Disassembled live (`x/500i`,
straight from process memory) and confirmed genuinely recursive (self-call at `0x17ce3b4`), with the
same near/far crossing-detection shape as `line_clear`. Captured live, for the target ray's
ROOT-level call: `point1=light_loc`, `point2=lumel_pos` (both bit-exact matches to the known target
ray, confirming the capture is on-target), `A=-39.1334839` (plane-dot of point1), `B=26.8858643`
(plane-dot of point2), crossing fraction `t=A/(B-A)=-0.592757821` (live-verified to 9 significant
figures against the formula). Confirmed via disassembly `mid = point1 + t*(point2-point1)`.

**Open, not resolved this round:** the exact mapping from this `t` to native's `t_native=ds/(ds-de)`
needs the per-recursive-level start/end role (which alternates near/far as the walk descends) --
only the root call was captured. A naive mapping gives `editor_t = t_native - 1` for this one data
point (real and reproducible, but a `t-1` shift is a more surprising relationship than a simple
`1-t` complement, and isn't disambiguated by one data point). Did not capture the resulting `mid`
point's own coordinates to check it lands between the two endpoints -- the natural next step for a
future round.

## Round 4 (2026-08-30): formula pinned cleanly with real mid coordinates, implemented + TDD'd,
## but the lighting re-measurement shows a SEVERE REGRESSION -- reverted

Extended the round-3 harness (`linecheck_singlestep_rec14_v2.py`) with a breakpoint at `0x17ce190`'s
own entry (reads incoming `point1`/`point2` for every call, including recursive ones) and one where
the computed `mid` local gets read for the recursive call's own argument setup. Captured the target
ray's root-level crossing `mid=(1647.60632,1147.82886,246.166962)` -- verified offline, exact f32
arithmetic, to match `lerp(start=lumel_pos, end=light_loc, t')` where `t'=de/(de-ds)` (native's own
convention) to FULL FLOAT32 PRECISION. This is exactly `1-t` where `t=ds/(ds-de)` is native's
original formula (`t+t'=1.0000000` to 7 decimal places) -- confirms round 2's ORIGINAL static
hypothesis, derived that round on the wrong function, turns out to be exactly the right formula for
the right one. (Round 3's tentative `editor_t=t_native-1` guess was based on a mislabeled algebraic
role and is superseded by this cleaner result.)

**Implemented via TDD.** Refactored `linecheck.rs`'s inline `t = ds/(ds-de)` into a named
`crossing_fraction(ds,de) -> f32 { de/(de-ds) }`, with a test pinning the live-captured numbers.
Confirmed genuinely RED before the fix and GREEN after (a first RED attempt used an overly broad
`sed` that also broke the test itself, giving a misleading result -- caught and redone with a scoped
edit before trusting it). `bin/test -k linecheck`: 88/88. Full `bin/test`: exit 0. `regression_gate.py`:
UNATCO/Wanchai both still node/surf/leaf-EXACT (geometry untouched by a lighting-only change, as
expected).

**But the actual gate -- the lighting re-measurement -- shows regression, not improvement:**

| level | before | with the fix |
|---|---:|---:|
| Wanchai byte-identical | 3297/4530 (72.8%) | 1355/4530 (29.9%) |
| UNATCO byte-identical | 2692/3345 (80.5%) | 1414/3345 (42.3%) |

The damage concentrates in the `run` bucket (which lights a surface's run even includes) -- a metric
the per-lumel occlusion formula should have no business touching, which is the clearest sign this
isn't simply "closer to the editor." **Reverted** (`git checkout -- uedcli-native/src/linecheck.rs`):
confirmed `bin/test -k linecheck` back to 87/87 and both levels' lighting measurements reproduce the
exact baseline numbers above, so the regression was real, not a measurement artifact.

**Why a live-verified-correct formula still regressed:** the capture only verified `de/(de-ds)` for
ONE genuine crossing (the root level of one ray) -- the depth-2 trace found no second crossing to
cross-check. `0x17ce190`'s own recursion (captured this round) always keeps `point2` fixed and only
ever replaces `point1` with `mid`, which doesn't obviously match `line_clear`'s `seg_clear`/`descend`
structure (which alternates which of `start`/`end` gets replaced, depending on near-vs-far side).
Blanket-substituting the formula everywhere `ds`/`de` are used, without first confirming it holds for
BOTH sides of a crossing and across recursion depth, was not "replicating the editor's real
algorithm" -- it was applying one live-verified fact more broadly than it was actually verified to
hold, and the regression is the direct evidence of that gap.

## Round 5 (2026-08-30): the recursion-structure question is ANSWERED -- `point2` staying fixed is a
## genuine structural invariant, not a one-ray artifact, and it explains round 4's regression

New harness `linecheck_multicrossing_survey.py`: drops the single-ray filter from rounds 3-4 (whose
`0x17ce190`-relative breakpoint offsets were already confirmed stable across several editor restarts)
and instead logs full recursion structure for the first 12 rays of whichever surface comes first
(`iSurf=1`). Completed in under a minute, same fast technique as rounds 3-4.

**Result: every one of the 12 sampled rays shows 4 genuine crossings before resolving, and in every
one, `point2` is bit-identical across all 4 physical recursive calls -- only `point1` ever changes,**
shrinking from `light_loc` through each successive `mid` toward `point2` (the lumel/query point).
Example (ray 1's `CALL_ENTRY` lines):

    point1=(1574.90796,-705.968018,179.389343) point2=(1462.90857,-1500.60205,4)
    point1=(1552.3092,-866.30603,144)          point2=(1462.90857,-1500.60205,4)
    point1=(1542.09204,-938.796997,128)        point2=(1462.90857,-1500.60205,4)
    point1=(1514.29736,-1136,84.4739227)       point2=(1462.90857,-1500.60205,4)

This is not a coincidence of one ray -- the identical shape (point2 frozen, point1 shrinking) repeats
across all 12 rays sampled, different surfaces/coordinates, same invariant. (Caveat logged in the
findings ledger: the harness's own `$depth` counter is unreliable as a call-stack-depth indicator --
`EARLY_RETURN_A`/`_B` mark an internal per-node LOOP continuing within one physical frame, not a
returning call; the `CALL_ENTRY` count, not `$depth`, is what "4 crossings" is based on.)

**This directly explains round 4's regression.** The real editor algorithm does not alternate which
endpoint gets replaced (the way `seg_clear`/`descend` visits `[start,mid]` then `[mid,end]`, swapping
which original endpoint survives each call) -- it always keeps the query's original `start`-equivalent
point fixed and only ever shrinks the other end. Round 4's fix grafted the (correct) formula onto the
(differently-shaped) existing recursion; the formula alone was never going to reproduce the real
algorithm's behavior population-wide, because the RECURSION SHAPE itself differs, not just the number
computed at each step.

**Not attempted this round:** a full recursion-structure port. What's still needed: understanding the
loop/child-selection mechanics (what determines the next node tested within one physical frame) and
whether the single-recursive-call structure ever needs a genuine second branch (matching native's
`&&`-combined near+far) or is provably a single-direction walk for this zero-extent case -- a
distinct, larger task, not safely attempted blind per the standing rule. No `linecheck.rs` change;
`bin/test`/`regression_gate.py` not re-run (nothing that could regress changed).

## Not shipped

No change to `linecheck.rs`, `light.rs`, or any other production code survives across all five
rounds -- round 4's fix was implemented, tested, and measured, but reverted after the lighting
re-measurement showed regression rather than the required real improvement; round 5 explains why
(recursion-shape mismatch) but does not yet know enough to safely port the real shape (per the
standing rule, 2026-08-30: replicate the real algorithm, verified, not a formula that merely happens
to match one traced case). `git diff` on `linecheck.rs` is empty.

## Files

- `dev/docs/spikes/2026-08-29-unatco-repart-live-diff/harness/line_clear_algorithm_check.py` (round
  1, the offline algorithm cross-check -- reusable for a future round's re-test)
- `dev/docs/spikes/2026-08-29-unatco-repart-live-diff/harness/linecheck_target_disasm.py` (round 1,
  the live vtable-target resolver + disassembler)
- `dev/docs/spikes/2026-08-29-unatco-repart-live-diff/harness/linecheck_singlestep_rec14.py` (round
  2, the targeted live single-step attempt that hung on the shared-call-site volume problem)
- `dev/docs/spikes/2026-08-29-unatco-repart-live-diff/harness/linecheck_singlestep_rec14_v2.py` (round
  3, iterated further in round 4 -- the surf-gated single-ray trace; accumulates the dispatcher
  disasm, the `0x17ce190` disasm, the `A`/`B`/`t` capture, and (round 4) the `CALL_ENTRY`/`MID`/
  `EARLY_RETURN_A`/`EARLY_RETURN_B` breakpoints -- reusable for a deeper future trace)
- `dev/docs/spikes/2026-08-29-unatco-repart-live-diff/harness/linecheck_singlestep_rec14_v3.py` (round
  3, the 20-ray outcome survey that found the `target+0x5b0` misidentification)
- `dev/docs/spikes/2026-08-29-unatco-repart-live-diff/logs/light-spotcheck-wanchai-native.dx`,
  `light-spotcheck-unatco-native.dx` (round 4, fresh native rebuilds of the REVERTED tree, used to
  confirm the clean-baseline numbers in the before/after table above)
- `dev/docs/spikes/2026-08-29-unatco-repart-live-diff/logs/linecheck-target-disasm.log` (round 1, the
  live capture + disassembly -- round 2's static decode is a from-scratch re-read of this same file)
- `dev/docs/spikes/2026-08-29-unatco-repart-live-diff/logs/linecheck-singlestep-rec14-v2.log`,
  `linecheck-singlestep-rec14-v3.log` (rounds 3-4, the live capture logs the facts above are drawn
  from)
- `dev/docs/spikes/2026-08-29-unatco-repart-live-diff/harness/linecheck_multicrossing_survey.py`
  (round 5, new -- the multi-ray, no-filter recursion-structure survey)
- `dev/docs/spikes/2026-08-29-unatco-repart-live-diff/logs/linecheck-multicrossing-survey.log`
  (round 5, the 12-ray capture the `point2`-fixed finding is drawn from)

## Round 6 (2026-08-30): full static disassembly of the REAL walker resolves the recursion shape
## completely, AND finds a genuine ±0.001 epsilon band (not 0.0) governing the whole-segment/crossing
## classification -- a major, concrete, live-confirmed new fact. State-threading (`edi`) and terminal
## polarity are NOT yet resolved with enough confidence to port safely; no code change made.

Continuation task: finish round 5's open question (the per-node loop/child-selection mechanics) via
live capture, then rewrite `line_clear`'s recursion to match, port the confirmed `t` formula, and
verify no regression -- with the explicit instruction to verify the shape thoroughly BEFORE porting,
learning from round 4's blind-swap regression.

**Method.** Two new harnesses, both reusing the proven surf-gated attach technique (rounds 3-5):
`linecheck_walker_full_disasm.py` (a live `x/400i 0x17ce190` dump straight from process memory --
no RVA/base translation needed, the address is directly breakpointable and has been stable across
every restart since round 3) captured the WHOLE function body (`0x17ce190`-`0x17ce441`, plus the
caller context through `0x17ce4c0`+); `linecheck_walker_state_trace.py` then placed ~20 breakpoints
at every branch/state-transition point identified in the disasm and traced 6 real rays end-to-end
(node index, D1/D2, branch kind, `edi` before/after, recursive-call args, terminal path, final
result), cross-referencing the live register values against round 3-4's already-known raw numbers to
catch hand-decoding sign errors (which the first pass of static reading DID make once -- see below --
caught and corrected before trusting the result).

**Finding 1 -- the recursion shape, fully resolved.** `0x17ce190` is a LOOP over whole-segment
(no-crossing) nodes -- `descend`ing without any function call, just overwriting the current node
index and jumping back to the loop top (`0x17ce425`->`0x17ce1c0`) -- with exactly ONE genuine
recursive call (`call 0x17ce190` at `0x17ce3b4`) per crossing. Argument-slot analysis (which FVector
lands at which stack offset, independent of any sign/FP reading -- the most reliable part of this
trace) proves: the near recursive call always **replaces point1 with `mid`, leaves point2
unchanged**, and descends into whichever child point1's OWN plane-dot (`D1`) selects (not point2's,
correcting an earlier mid-trace guess this round). Once that call returns, if clear, the SAME frame
continues via the loop (not a second call) into the OTHER child, this time with **point2 replaced by
`mid`, point1 left unchanged** -- exactly the "near recursion, far tail-loop" pattern predicted by
round 5's `point2`-stays-fixed observation, now explained structurally: `point2` only changes at the
far-continuation step, which is why a chain of NEAR recursions (round 5's 4-crossing example) never
touches it. This closes round 5's exact open question: the near/far split IS a genuine two-way
`descend(...) && descend(...)` test (short-circuits on the near call returning blocked, `0x17ce439`),
it is simply implemented with the far half as a compiler-tail-call-eliminated loop rather than a
second stack frame -- behaviorally equivalent to native's own shape, but with DIFFERENT roles: native
always treats its first argument (`start`) as the one that shrinks toward `mid` first; the real editor
always shrinks POINT1 (which round 3 established, live, is `light_loc` -- native's `end`, not
`start`) toward `mid` first, anchoring on POINT2 (`lumel_pos`, native's `start`) until the
far-continuation step.

**Finding 2 -- a genuine ±0.001 epsilon band governs classification, live-read from process memory,
not assumed.** The two float constants gating the FRONT/BACK/crossing three-way split
(`0x183761c`, `0x182293c`) were previously unknown/unread (rounds 1-2 refuted a **different**
epsilon hypothesis for the WRONG function, `target+0x5b0`). Read directly via `x/f *addr` this round:
**CONST1 = -0.001, CONST2 = +0.001** (bit-exact float32 encodings of 0.001, not 0.0). Re-deriving the
boundary logic with these values: FRONT-whole requires `D1 > -0.001 AND D2 > -0.001`; BACK-whole
requires `D1 < 0.001 AND D2 < 0.001`; anything else is a crossing. This means a node whose D1 (or D2)
is only *slightly* on the "wrong" side of 0 (within 0.001) still gets swept into the SAME
classification as its partner, avoiding a spurious crossing split. This is DIRECTLY the mechanism
round 1's original traced exemplar needed: a ray origin sitting ~0.0002uu off a splitting plane
(`ds`≈-0.0002) would, under native's strict `>=0.0` test, register as a crossing and descend the
tiny near-zero sub-segment first -- exactly the false-block bug round 1 found. Under the REAL
±0.001 band, that same tiny-negative value falls inside the epsilon and gets absorbed into the
SAME-side classification as its partner instead. **Round 1's original epsilon hypothesis was right in
spirit -- it was examining the wrong function; the real function genuinely has one.**

**Finding 3 -- the crossing formula re-confirmed with corrected point roles.** `t = D1/(D2-D1)`
(register-derived, matches round 3's raw captured `t=-0.592757821` for its traced ray EXACTLY once
D1/D2 are correctly identified as point1/point2's own dots via a live memory read at the CROSS_ENTRY
breakpoint -- an earlier attempt this round had D1/D2 swapped from mis-reading x87-pending-store
timing, caught by cross-checking against round 3's already-known live numbers before trusting
anything further). `mid = point2 + t*(point2 - point1)`, algebraically consistent with round 4's
independently live-verified `mid` coordinates (`t = -t'` where `t'` is round 4's `de/(de-ds)`, an
EXACT floating-point negation, not an approximation, so no contradiction).

**Finding 4 -- a real, non-obvious CSG-mask asymmetry, NOT yet reconciled.** Every whole-segment
CSG-classification site strips `NF_BrightCorners` (`0x10`) from `extra_flags` before testing against
`NodeFlags` (`and al,0xef; or al,0x21`), matching the existing `is_csg` helper exactly. The
far-continuation's OWN classification site (`0x17ce3d5`-`0x17ce3da`, live-confirmed present and
reachable) does NOT strip that bit (`or al,0x21` only) -- a real, disassembly- and live-trace-
confirmed difference from `is_csg`'s formula, not yet understood or reconciled with the existing
model. If real and load-bearing, this means the far-continuation step cannot simply reuse the
existing `is_csg` helper unmodified for a NF_BrightCorners-flagged surface.

**Not resolved -- why no port was attempted this round.** The `edi`/"state" thread's full semantics
(what it represents, and its value on every whole-segment AND far-continuation branch) and the
terminal-handling return polarity were traced live for 6 real rays (`linecheck-walker-state-trace.log`)
and are CONSISTENT with `eax=1`/`edi`-nonzero meaning CLEAR (cross-validated against the terminal
path that matches the EXISTING, already-tested `NF_BrightCorners`-suppression semantics in
`linecheck.rs` exactly: solid terminal + `NF_BrightCorners` + `seen_empty`-equivalent global still 0
-> returns 1/clear, precisely matching `bright_corners_reports_clear_when_the_ray_starts_in_solid`).
But the exact `edi` bit-formula for EVERY branch (whole-segment CSG/non-CSG on both FRONT and BACK,
which use different AND/OR combinations that are not yet fully explained semantically -- see the
raw disasm) and how it composes across nested near-recursions is not yet confidently enough
understood to port without real regression risk, matching the standing rule and round 4's own
lesson. Six sampled rays all returned the same outcome (all-blocked, a plausible shadowed row), so
this trace did not exercise the CLEAR-return / non-solid-terminal paths at all -- a real gap in
validation coverage, not just in derivation.

**Not shipped.** No `linecheck.rs` change this round; `git diff` on it is empty.
`bin/test -k linecheck` and `regression_gate.py` not re-run (nothing that could regress changed --
only new committed spike harnesses/logs were added).

## Concrete next step for a future round

Round 6 fully resolved the recursion SHAPE and found the real ±0.001 epsilon band (both now safe to
port with confidence). What remains before a safe port: (1) trace rays that return CLEAR and hit a
non-CSG or empty terminal, to pin the `edi` state-formula's semantics across every branch (the 6
rays this round were all-blocked and never exercised those paths); (2) resolve Finding 4's CSG-mask
asymmetry -- confirm it's real (not a mis-read) and work out what it implies for a NF_BrightCorners
surface; (3) only then port the full recursion (shape + epsilon + formula + resolved state machine)
via TDD, and re-run the FULL lighting comparison (not a sample) on UNATCO and Wanchai before/after,
per the standing gate.

## Files (round 6)

- `dev/docs/spikes/2026-08-29-unatco-repart-live-diff/harness/linecheck_walker_full_disasm.py` (new
  -- live `x/400i` dump of the real walker's whole body, no RVA translation needed)
- `dev/docs/spikes/2026-08-29-unatco-repart-live-diff/logs/linecheck-walker-full-disasm.log` (the
  captured disassembly Findings 1-3 above are read from)
- `dev/docs/spikes/2026-08-29-unatco-repart-live-diff/harness/linecheck_walker_state_trace.py` (new
  -- ~20-breakpoint live state trace of 6 real rays, plus a direct memory read of the two epsilon
  constants)
- `dev/docs/spikes/2026-08-29-unatco-repart-live-diff/logs/linecheck-walker-state-trace.log` (the
  6-ray capture Finding 2/4 and the "not resolved" section are drawn from)

## Round 7 (2026-08-30): the state machine is fully pinned and passes every targeted check --
## then a broad offline sweep against real golden bits reveals a large-scale regression the
## targeted checks never exercised. Root cause not found; reverted cleanly.

Continuation task, exactly as scoped by round 6: trace CLEAR-returning rays (round 6's 6 rays were
all-blocked) to pin the `edi` state formula and terminal polarity, resolve the `NF_BrightCorners`
CSG-mask asymmetry, then attempt the port with TDD + the full regression gate.

**Found a CLEAR ray offline, not by brute-force live scanning.** A live outcome-only scan
(`linecheck_find_clear_ray.py`) proved too slow (30 rays into one shadowed surface, 30+ still
blocked, no live per-ray filtering by outcome is possible without huge ptrace overhead per hit --
same class of problem round 2 hit and fixed by surf-gating). Instead: parsed `golden.dx` directly
(no live capture) to find a real (surf, light, u, v) with a stored CLEAR bit --
`isurf=1060, light=Light624`, a small 2x2-lumel surface (4 total shadow rays for the whole surface,
1 light in its run) -- then targeted the existing surf-gated live-trace harness at that exact
`isurf`. Deep-traced all 4 of its rays plus 2 incidental rays from the next surface LIGHT APPLY
processed next: **3 CLEAR, 3 BLOCKED** -- the first genuine mix this investigation has captured.

**Root-caused a live-capture-confirmed transcription error from round 6's own initial reading**,
caught via the SAME cross-check discipline this investigation has used throughout (self-consistency
before trusting a result): live-recapturing `D1`/`D2` at node 310 for two different rays sharing one
light showed `[ebp-0x8]` VARIES per-ray (tracks the query/lumel point) while `[ebp-0xc]` stays
constant (tracks the light) -- the OPPOSITE of round 6's original labels. Fixed: `t = D2/(D1-D2)`,
`mid = point2 + t*(point2-point1)`, near-side keyed on `D2`'s (not `D1`'s) sign. Algebraically
consistent with round 4's independently-verified `mid` formula (`t = -t'` is an exact float
negation, not an approximation, so the two facts don't conflict).

**Found and fixed a second real gap while validating end-to-end: the near-recursive call's own
incoming state is NOT the caller's `edi` passed through** (what round 6 assumed) **-- it's a
separate computation** (`0x17ce306`-`0x17ce35e`, decoded fresh this round after a live ray4
end-to-end mismatch exposed the gap: real terminal showed `edi=0` where the "pass edi through"
assumption predicted `edi=1`). It mirrors the far-continuation formula's shape (same `OR`-on-FRONT /
`AND-NOT`-on-BACK pattern, algebraically simplified to one reusable `combine_state(side, state,
csg)` helper covering all three sites: whole-segment update, near-call incoming state, and
far-continuation update). Also found a real side effect round 6 missed: the terminal handler's
`edi != 0` fast-return path also SETS the shared `seen_empty`-equivalent global (`0x17ce4ae`) before
returning -- caught only by re-grepping the disasm a second time.

**Verified extensively before attempting a port, learning round 4's lesson:**
- 122 individual live-captured state transitions (whole-segment FRONT/BACK x CSG/non-CSG, both
  far-continuation branches, terminal polarity) replayed mechanically against real `edi`/`NodeFlags`
  read straight from `golden.dx` -- **0 mismatches**.
- 4/4 real rays (isurf=1060) replayed end-to-end with the real light location + real lumel
  positions + real BSP tree -- **exact final result match for all 4, and exact node-by-node visited
  PATH match for 3/4** (the 4th wasn't checked for path, only result).

**Then a broad, unbiased offline sweep (not cherry-picked records) against real golden bits found a
severe regression the targeted checks never exercised:** `line_clear_v2_algorithm_check.py`
(no native.dx needed -- tests the ported algorithm purely against golden's own stored bits) over
2,000,000 real (surf, light, lumel) shadow-bit computations each on Wanchai and UNATCO:
**Wanchai 92.36%, UNATCO 88.81%** -- both well below the current ~99% shadow-bit baseline the
EXISTING (un-fixed) `line_clear` already achieves on grid+run-matched records. Direction is
one-sided: every sampled mismatch is `golden=blocked, algorithm=clear` (never the reverse) --
systematic under-blocking, not noise.

**Ruled out the obvious hypothesis (a FRONT/BACK state-polarity swap) as NOT a clean fix.** Tested
directly: swapping which side's CSG encounter sets vs. clears `state` gives 97.04% on one
problem light (`Light24`, up from 81.34%) but is a genuine REGRESSION elsewhere (a different,
working light/surface pair drops from 100% to a much lower rate when swapped -- not reported
exactly, but confirmed strictly worse in aggregate testing). A uniform swap is provably not the
right fix; the bug is something more localized/context-dependent than a single global sign error.

**Live-verified example (`isurf=1060`) was a false positive for FULL fidelity, not a false
finding -- a real, important lesson.** The isolated ray checks were genuinely solid (matching real
disassembly, real registers, real final outcomes) but happened to sample only cases where the
extra mechanism below (probably) doesn't apply, so they could not catch this gap. This is exactly
why the task's own standing instruction to re-run the FULL lighting comparison (not a sample)
before shipping exists -- and why it wasn't skipped here.

**Leading hypothesis (an un-modeled zone-transform branch) was LIVE-TESTED THE SAME ROUND AND
REFUTED.** Every dot-product computation in the walker is gated on `edx` (loaded from `[ebp+0x10]`,
a pointer argument constant across the whole recursion, confirmed by re-tracing the arg-slot
layout): `test edx,edx; je <plain-dot-path>` -- when non-null, the point is first passed through an
indirect call (`call *0x1819988`) before the dot product is computed (`0x17ce1d3`-`0x17ce213`).
Every port this round (Python and the reverted Rust) always takes the "edx is null" plain-dot path.
New harness `linecheck_edx_zone_check.py`, surf-gated on UNATCO record 22 / `isurf=2810` (a small,
single-light `Light24`-only surface, chosen offline to reach it fast without waiting through
`Light70`'s own 3248-lumel block first): **`edx=0x0` for every single one of the 4 sampled rays**
(2 returning result=0, 2 returning result=1) -- identical to the working case. This RULES OUT the
zone-transform branch as the cause for this specific problem light: the "always take the plain-dot
path" assumption every port made this round is confirmed correct here, not the bug.

**So the root cause remains genuinely open after this round's full effort.** What's ruled out: a
uniform FRONT/BACK state-polarity swap (helps one region, hurts another); the zone-transform branch
(edx is null in the tested broken case, same as the working one). What's NOT yet tried: single-
stepping the SPECIFIC short mismatch case live (this round's debugging was offline/Python only,
after the initial live captures -- the previous two rounds' lesson, that offline hand-tracing
repeatedly produces subtle sign/register errors a live capture catches, was not re-applied to this
NEW regression before time ran out). The bug could still be a further transcription error in the
already-decoded formula (unlikely given 122/122 + 4/4 exact-path checks, but not impossible), or a
genuinely new mechanism neither round 6 nor round 7 has looked at yet (e.g. something in the
un-examined portions of the terminal-handling block past `0x17ce464`, which writes output-struct
fields this investigation has never needed until now, or a subtlety in how `MAX_DEPTH`/recursion
interacts with real trees far deeper than the ~30-node examples checked so far).

**Not shipped -- reverted cleanly.** `git checkout -- uedcli-native/src/linecheck.rs`: `git diff` on
it is empty. `bin/test -k linecheck`: 90/90 (the previous 89 plus one degenerate synthetic-scenario
concern surfaced mid-round, `a_not_vis_blocking_node_does_not_occlude`, which the pre-existing code
already passes and the revert restores unchanged -- not itself resolved or explained, folded into
the same unresolved-mechanism bucket above rather than chased further). No `regression_gate.py`
re-run needed (no shipped code changed). `dev/docs/native-materialize-findings.md` carries the
condensed version of this entry.

## Concrete next step for a future round

1. **Live single-step the shortest available real mismatch, not another offline hand-trace.** Round
   7's own debugging (once the initial live captures were done) reverted to offline Python
   reasoning and hit the same sign/register-confusion trap earlier rounds already learned to avoid
   with live cross-checks. Use the proven surf-gate technique to attach at a KNOWN mismatching
   (light, surface, u, v) -- e.g. re-derive one via `line_clear_v2_algorithm_check.py` against
   UNATCO's `Light24`/record-22 surface (already isolated as broken this round, and already fast to
   reach live, per `linecheck_edx_zone_check.py`'s own targeting) -- and log the SAME breakpoint set
   `linecheck_walker_state_trace.py` already has (D1/D2, branch kind, `edi` before/after, terminal
   path) for that EXACT ray, then diff node-by-node against the Python port's own trace on the same
   inputs. This is the same technique that found and fixed round 7's two real gaps (the D1/D2 label
   swap, the near-call incoming-state gap) -- apply it to the NEW regression before any more static
   reading or hypothesis-guessing.
2. Do not re-attempt a Rust port without re-running the SAME 2,000,000-bit-per-level offline sweep
   (`line_clear_v2_algorithm_check.py`) first -- the isolated 4-ray check that looked complete this
   round was demonstrably not sufficient on its own, and should not be trusted alone again.
3. If the single-step trace doesn't resolve it either, consider whether the un-examined tail of the
   terminal-handling block (`0x17ce464`+, which writes `FCheckResult`-style output fields this
   investigation has never needed for a pure boolean test) or a deeper-than-tested recursion could
   be involved -- both flagged as untested above, neither chased this round.

## Files (round 7)

- `dev/docs/spikes/2026-08-29-unatco-repart-live-diff/harness/linecheck_find_clear_ray.py` (new --
  cheap outcome-only live scan across many rays/surfaces; superseded by the offline-lookup approach
  for finding a specific clear ray, but kept as a reusable coarse survey tool)
- `dev/docs/spikes/2026-08-29-unatco-repart-live-diff/harness/linecheck_walker_state_trace.py`
  (extended this round: `--isurf` targeting, corrected `DOTS` breakpoint reading both `D1`/`D2`
  explicitly instead of a placeholder)
- `dev/docs/spikes/2026-08-29-unatco-repart-live-diff/logs/linecheck-walker-state-trace.log`
  (overwritten each run -- the isurf=1060 6-ray capture this round's findings are drawn from; not
  independently preserved per-run, a reusability gap for a future session to fix if needed)
- `dev/docs/spikes/2026-08-29-unatco-repart-live-diff/harness/line_clear_v2_algorithm_check.py` (new
  -- the full candidate port in Python, plus the offline large-scale golden-bit validator; kept
  committed since it's the fastest way to re-test any future fix before touching Rust)
- `dev/docs/spikes/2026-08-29-unatco-repart-live-diff/harness/linecheck_edx_zone_check.py` (new --
  the targeted `edx`/zone-transform live check; refuted the hypothesis, kept as a reusable tool in
  case a future round wants to re-check it against a different (light, surface) pair)
- `dev/docs/spikes/2026-08-29-unatco-repart-live-diff/logs/linecheck-edx-zone-check.log` (the 4-ray
  `edx=0x0` capture the refutation above is drawn from)

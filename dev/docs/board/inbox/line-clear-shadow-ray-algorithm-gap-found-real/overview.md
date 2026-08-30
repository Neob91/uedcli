+++
priority = "p2"
kind = "debug"
summary = "Confirmed line_clear (not lumel_axes) causes Wanchai's bits-only shadow divergence. Round 3: a surf-gated live trace (fixing round 2's hang) found the function rounds 1-2 analyzed (target+0x5b0) is NOT the one real shadow rays use; located and live-captured the actual recursive walker (0x17ce190) and its crossing formula for one ray's root call, but the full sign/role mapping to native's t=ds/(ds-de) is still open -- no fix, logged per the no-speculative-fix rule."
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

## Not shipped

No change to `linecheck.rs`, `light.rs`, or any other production code across all three rounds -- per
the standing rule (owner, 2026-08-30): the real mechanism is not yet confidently known (round 3 found
the RIGHT function but has not fully pinned its formula), so no speculative fix, tolerance, or
rounding tweak was attempted. `regression_gate.py`/`bin/test` were not re-run since nothing that could
regress them changed.

## Files

- `dev/docs/spikes/2026-08-29-unatco-repart-live-diff/harness/line_clear_algorithm_check.py` (round
  1, the offline algorithm cross-check -- reusable for a future round's re-test)
- `dev/docs/spikes/2026-08-29-unatco-repart-live-diff/harness/linecheck_target_disasm.py` (round 1,
  the live vtable-target resolver + disassembler)
- `dev/docs/spikes/2026-08-29-unatco-repart-live-diff/harness/linecheck_singlestep_rec14.py` (round
  2, the targeted live single-step attempt that hung on the shared-call-site volume problem)
- `dev/docs/spikes/2026-08-29-unatco-repart-live-diff/harness/linecheck_singlestep_rec14_v2.py` (round
  3, new -- the surf-gated single-ray trace; iterated in place across several reruns to add the
  dispatcher disasm, the `0x17ce190` disasm, and the final `A`/`B`/`t` capture)
- `dev/docs/spikes/2026-08-29-unatco-repart-live-diff/harness/linecheck_singlestep_rec14_v3.py` (round
  3, new -- the 20-ray outcome survey that found the `target+0x5b0` misidentification)
- `dev/docs/spikes/2026-08-29-unatco-repart-live-diff/logs/light-spotcheck-wanchai-native.dx` (round
  1, fresh native rebuild used that round)
- `dev/docs/spikes/2026-08-29-unatco-repart-live-diff/logs/linecheck-target-disasm.log` (round 1, the
  live capture + disassembly -- round 2's static decode is a from-scratch re-read of this same file)
- `dev/docs/spikes/2026-08-29-unatco-repart-live-diff/logs/linecheck-singlestep-rec14-v2.log`,
  `linecheck-singlestep-rec14-v3.log` (round 3, the live capture logs the facts above are drawn from)

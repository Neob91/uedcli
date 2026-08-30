+++
priority = "p2"
kind = "debug"
summary = "Confirmed line_clear (not lumel_axes) causes Wanchai's bits-only shadow divergence; live-disassembled the real editor function on the current build but did not fully decode its per-node state formula -- no fix, logged per the no-speculative-fix rule."
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

## Not shipped

No change to `linecheck.rs`, `light.rs`, or any other production code this round -- per the standing
rule (owner, 2026-08-30): the real mechanism is not yet confidently known (finding D above is an open
question, not a resolved fact), so no speculative fix, tolerance, or rounding tweak was attempted.
`git status` confirms zero production-code diffs; only two new harness scripts and their log/dx output
were added (`dev/docs/spikes/2026-08-29-unatco-repart-live-diff/harness/line_clear_algorithm_check.py`,
`linecheck_target_disasm.py`). `regression_gate.py`/`bin/test` were not re-run since nothing that
could regress them changed.

## Files

- `dev/docs/spikes/2026-08-29-unatco-repart-live-diff/harness/line_clear_algorithm_check.py` (new,
  the offline algorithm cross-check -- reusable for a future round's re-test)
- `dev/docs/spikes/2026-08-29-unatco-repart-live-diff/harness/linecheck_target_disasm.py` (new, the
  live vtable-target resolver + disassembler -- reusable for a single-step follow-up)
- `dev/docs/spikes/2026-08-29-unatco-repart-live-diff/logs/light-spotcheck-wanchai-native.dx` (fresh
  native rebuild used by this round)
- `dev/docs/spikes/2026-08-29-unatco-repart-live-diff/logs/linecheck-target-disasm.log` (the live
  capture + disassembly)

+++
priority = "p1"
kind = "implement"
summary = "Per-surface texture verbs — STEP 5 (catalog + one-tile + scale --to); steps 2-4 shipped"
+++

# Per-surface texture verbs — STEP 5 (steps 2-4 shipped)

**STEPS 2-4 SHIPPED** (branch `worktree-poly-align-steps-2-4`, squash-merged): step 2 `align`
flags→`wall|floor|run` subcommands + `--fresh-frame` deleted + BRUSH:idx stdout; step 3 `wall`/`floor`
rewritten to the editor's `WALLX`/`WALLY`/`FLOOR` projection family (pinned against `measured.json`);
step 4 `align run` general connected run + `--turn` + the `--fit-perimeter` guards. `rationale/polyalign.md`
records the run algorithm's agent choices. **Only STEP 5 remains** — catalog plumbing, the
`--fit-perimeter` whole-**tile** fix, `one-tile`, and `scale --to` (all need the texture catalog).
Consider splitting `one-tile` out (its own frame math). See `align-flag-rename-left-dev-docs-refs-stale`
for the stale dev-docs refs the rename left, awaiting the owner's yes.

Spec: board item `the-per-surface-verb-split`.
**Spec gate: PASSED** — at its ceiling; every round's findings are folded into the sections
themselves. **Step 1 is BUILT** (2026-07-26 — `brush poly pan|rotate|scale`; see
board item `per-surface-texture-verbs-step-1-of-5`); these are the four steps after it, and the spec's §4.4 sequences them under
one rule: *no step introduces a flag, a subcommand or a deletion whose behaviour arrives in a later
step.*

**Plan them SEPARATELY, in order — do not write one plan for all four.** §4.4 splits them because
they differ in kind, and the review rounds repeatedly found defects at the seams between them:

- **step 2 — flags → subcommands.** `align wall|floor|run|one-tile` replaces the mutually-exclusive
  flag group. One atomic CLI change plus `usage.md` and the recipes. Note the two interim states the
  spec requires documenting *in this step*: `run` still has ring-only semantics until step 4, and
  `--fit-perimeter` still rounds whole texels (so `usage.md`'s "an exact meet at the closing seam"
  must be corrected here, not later).
- **step 3 — `wall`/`floor` adopt the editor's projection family.** World-axis anchor, `|proj|`
  density, `|N.A| > 0.05` guard replacing `_check_orientation`. This is the step with an editor
  golden to check itself against (`spikes/2026-07-26-unrealed-texalign-semantics/measured.json`), so
  the parity pins are nearly free — and it deletes the coplanarity and co-orientation guards, which
  is one of the two narrowings in §7.
- **step 4 — `align run` + `--turn` + the `--fit-perimeter` tile fix.** The frame math, reviewed
  alone: the pre-walk, the derived root and walk direction, terminal faces, the across-run sign, and
  the whole-tile rounding. `--fit-perimeter`'s closed-run and quarter-turn guards belong HERE, with
  `--turn`, not with the catalog work.
- **step 5 — catalog plumbing + `one-tile` + `scale --to`.** Introduces a project/catalog dependency
  on a verb that is pure model-side today, so it is the riskiest step. Consider splitting `one-tile`
  out again: it is a new mode with its own frame math (Gram-Schmidt basis, min-corner anchor) and
  `CLAUDE.md` "Split a batch when it stops being reviewable" applies.

**Read §4.1 before planning any of them** — it carries a per-test verdict for all 39
`test_polyalign.py` tests (5 deleted, 14 changed, 20 surviving) plus the tests outside that file
which go red, by step. Relaxing one of those to make it pass is how a shipped capability gets lost
quietly.

**Two `[OWNER — decide]` items are parked on [`board/inbox/`](../../inbox/)** and both change how EXISTING
content renders — a plan should not assume either answer: the `wall`/`floor` guard deletion (a
double-sided wall that errors today will succeed, mirrored on its back face) and `run`'s V-flip
(re-aligning any existing cylinder wrap flips its texture vertically). A third, `rotate`'s turn
direction on a subtractive brush, affects step 1 and is filed separately.

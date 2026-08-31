+++
priority = "p3"
kind = "docs"
summary = "grid caption \"major = 8x drawn\" is imprecise once --grid-size escalates -- confirmed, resolved by removal"
+++

# grid caption "major = 8x drawn" is imprecise once `--grid-size` escalates

**Resolved, 2026-08-30.** Owner confirmed by pixel measurement: at `--grid-size 32` escalating once to
a drawn 64, majors measured 32px apart (every 4th drawn line, every 256 uu) against a caption reading
512 — matching this item's bit-math exactly. Spec §6 was updated to drop the major field outright
(reports `set`/`visible` only, never `minor`/`major`) rather than correct it to `max(drawn, 8*set)`.
Left here, un-actioned further — the analysis below is the record of why.

Found while building `add-visual-grid-for-2d-views-in-level-actor`. Originally recorded as non-blocking
— the caption followed the spec's THEN-explicit, twice-stated instruction (§3.3, §6: "majors are
`8 × drawn`"). The underlying tier formula (§3.1, adopted verbatim) never matched that statement once
escalation (`shift > 0`) happened; the section above is the resolution.

**The tier test is `((i << shift) & 7) == 0`, not `(i & 7) == 0`.** Working through the bit math: a line
is major iff `world` is a multiple of `8 * step` (the ORIGINAL/requested step — §3.2's own words: "the
major lines stay pinned to multiples of `8 · GridY`... as the grid escalates"), not `8 * drawn` (the
step actually rendered, `= step << shift`). The two coincide only when `shift == 0` (no escalation),
where `drawn == step`.

Concretely: at `shift == 1`, majors land every 4th DRAWN line (spacing `4 * drawn == 8 * step`), not
every 8th. At `shift >= 3`, `8 * step <= drawn`, so EVERY drawn line is "major" — the minor/major split
vanishes entirely once escalated three doublings past the requested step.

**Why this doesn't block the current change:** the AUTO step (`--grid-size` omitted) is chosen to put
only ~1-2 lines in the pane, so `count` stays far under `limit` and `shift` is 0 in every realistic
case — the caption's `8 * drawn` is then exactly right. The discrepancy only shows up when a user passes
an EXPLICIT `--grid-size` fine enough to force real escalation (`shift >= 1`), which the spec's own §9
test list calls out as a case to cover ("a step too fine for the pane doubles..."). In that case the
caption's printed `major` value (`8 * drawn`) is technically not the on-screen major-line spacing
(`8 * step`, i.e. `max(drawn, 8*step)` in general) — the LATTICE itself is still drawn correctly (per
the literal, disassembly-verified formula), only the caption's summary number can read a bit
misleadingly finer or coarser than what a careful pixel count would show.

**Options if this gets picked up:**
- Leave it — the caption already tells you the DRAWN minor step, which is enough to reconstruct the
  world grid; the "major" field is a convenience, not load-bearing.
- Change the caption's major field to `step * max(1 << shift, 8)` (the actual on-screen major spacing),
  which matches `8 * drawn` exactly when unescalated and the true spacing when escalated.

No test currently locks in `8 * drawn` as the ONLY acceptable caption formula, so a follow-up isn't
constrained by test debt — just the spec text.

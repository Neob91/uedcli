+++
priority = "p3"
kind = "implement"
summary = "`brush poly align` still prints touched brush NAMES while `set`/`pan`/`rotate`/ `scale` now print `BRUSH:idx` selectors — the two halves of one verb family disagree"
+++

# `brush poly align` still prints touched brush NAMES while `set`/`pan`/`rotate`/ `scale` now print `BRUSH:idx` selectors — the two halves of one verb family disagree

Step 1
(built 2026-07-26) converted the four per-face mutators to per-face stdout, per the owner ruling
that a bare brush name would hand the next verb in a pipe a wider set than was edited. `align` is
covered by the same ruling but is **out of step 1's scope** — its own restructure (modes →
subcommands, `wall`/`floor` world-space, `run`, `one-tile`) is steps 2–5 and is not planned yet.

**The consequence, measured, is a LOUD break and not a silent widening** — an earlier version of
this item claimed the latter and was wrong. Step 1 also narrowed the per-face verbs' target grammar
to `BRUSH:SELECTOR` only, so `align`'s bare name is rejected outright:
`brush poly align WALL:4 --floor | brush poly rotate -` exits 2 with
`surface selector must be BRUSH:SELECTOR, got 'WALL'` (same for `set`/`pan`/`scale`). So the two
narrowings cover each other: no wrong face is ever edited, the pipeline simply does not compose.

**Dropped p2 → p3 on that correction.** It is a composition gap with a working one-verb workaround
(`brush poly find` between the two), it fails visibly rather than corrupting anything, and
`docs/usage.md` "Output streams for mutators" now states it plainly, so nobody meets it as a trap.

Fold the conversion into whichever align step lands first rather than doing it standalone — the
mechanism already exists (`surface.resolve_targets` + `dispatch._print_poly_selectors`), but
`align`'s target grammar also accepts bare brush names, so it needs its own resolver pass.

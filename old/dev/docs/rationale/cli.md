# CLI mechanics — why the argument surface is built this way

Engineering decisions about `uedcli/cli/main.py` and `uedcli/cli/dispatch.py`. The conventions they serve are
the owner's, in [`../direction/conventions.md`](../direction/conventions.md); this doc is the
machinery.

## Deleting a migration shim can silently re-open a prefix-abbreviation hole

`argparse` expands any unambiguous prefix of a defined option. A migration-error shim therefore also
occupies its own name, blocking that name from abbreviating into a surviving flag. Delete the shim
and the abbreviation resolves elsewhere.

While the `--class` shim existed, `--class` was defined and errored helpfully. Deleting it — correct
under the no-back-compat rule — let `--class` abbreviate into `--class-exact`, so an invocation that
used to fail loudly silently meant exact-match only.

Fix: rename the survivor (`--class-exact` → `--exact-class`) so the prefix no longer collides.

After deleting any option, check the built parser, not the reasoning: whether a prefix is ambiguous
depends on the full set of options on that subparser, which the diff does not show.

**Rejected:**

- **`allow_abbrev=False` globally** — kills the whole class of hazard in one line, but changes
  behaviour across every flag and removes abbreviations that work today, to fix one collision.
- **Keeping the `--class` shim** so the name stays occupied — a shim retained for a side effect is
  still a shim, and the next person to tidy it up re-opens the hole with no warning.
- **Accepting the new abbreviation** and documenting it — it silently changes what an existing
  invocation means, the one outcome the no-back-compat rule prevents.

**Refs:** `../direction/conventions.md` "No back-compat cruft" · `uedcli/cli/main.py`

## `Decimal` is never an argparse `type=`; one `parse_decimal` validator owns every scalar number

`argparse` converts only `ValueError` and `TypeError` raised by a `type=` callable into a clean
parser error. `decimal.Decimal("abc")` raises `decimal.InvalidOperation`, an `ArithmeticError`, so
`type=Decimal` lets a typo escape as a raw Python traceback, breaking "no Python exception ever
reaches the user". Separately, `Decimal` constructs `"nan"`, `"snan"` and `"inf"`: those parse, then
misbehave downstream (a NaN coordinate compares false against everything, an infinite one matches
every actor on an axis, a signaling NaN raises from inside later arithmetic instead of at parse
time).

So `parse_decimal` is the single scalar-number validator: it wraps the construction and rejects
both the non-numeric and the non-finite spelling with `ArgumentTypeError` (clean message naming the
value, exit 2). Every Decimal-valued argument routes through it — `brush clip --offset` directly,
and `parse_coord` / `parse_bbox` per component, so the finite check cannot be present in one
coordinate parser and missing from the next (it was: `parse_bbox` had it, `parse_coord` did not).

`parse_pan` deliberately does not route through it: pan is int-valued (`model.Polygon.pan` is
`tuple[int, int]`) and `int()` already rejects every non-finite spelling with a `ValueError`
argparse converts cleanly. A test pins this.

The validator guarantees the spelling, not the range. `Decimal` has arbitrary exponent range, so
`1e999999999` is a finite `Decimal` that passes the check; it becomes `inf` only when a
computed-geometry module converts it to `float`. Closing that overflow means bounding coordinates to
what a float can represent — a decision about where range may be lost, not another `is_finite()`
call. Deferred and logged (`dev/docs/board/inbox/`, "`parse_decimal` admits an INFINITY by another
spelling", 2026-07-26); nothing observable breaks today, since such a value ends as a clean no-op or
a clean `GeometryError`.

**Rejected:**

- **Catching `ArithmeticError` in the dispatch guard** — turns the traceback into a clean exit, but
  only after the flag's value was already accepted as valid; the non-finite half of the bug is not
  an exception at all.
- **A per-flag `.is_finite()` check at each use site** — exactly the arrangement that let
  `parse_coord` drift out of step with `parse_bbox`.
- **Keeping `--coord` as an alias of the renamed `--offset`** — no back-compat cruft; the new
  spelling is the only spelling (`../direction/conventions.md`).

**Refs:** `../direction/conventions.md` "No silent half-answers, and no fallbacks" ·
`uedcli/cli/parsers/_arguments.py` (`parse_decimal`/`parse_coord`/`parse_bbox`/`parse_pan`) ·
`uedcli/tests/test_cli.py`

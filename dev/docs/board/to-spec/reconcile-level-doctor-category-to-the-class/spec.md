# Reconcile `level doctor --category` to the `class show --category` shape

**Draft — pre-spec.** A consistency fix: two verbs expose a `--category` flag that parses and fails
differently. Make `level doctor --category` match the shape `class show --category` settled on
(2026-07-18): repeatable-append, case-insensitive, exit-2-with-listing on a bad value.

## Goal

One `--category` grammar across the CLI. A user who learned `class show --category Movement
--category Lighting` should be able to write `level doctor --category watertight --category convex`
and have it parse and fail the same way. Behaviour of the doctor's lint itself does not change — only
how the display-filter flag is spelled and validated.

## Current state

Two same-named flags, opposite on every axis.

**`class show --category` (the target shape):**
- parser `uedcli/cli/parsers/classes.py:83-88` — `action="append"`, `dest="categories"`,
  `default=[]`, `metavar="NAME"`; help says "repeat to OR several. Exact, case-insensitive."
- handler `uedcli/cli/commands/classes.py:684-693` — casefolds; validates each value against the
  available set; the FIRST value matching nothing raises `CommandError` (exit 2) naming it and
  listing what is available: `no category 'X' on <fqcn>; available: A, B, …`.
- Its available set is DERIVED per class (the class's own editable categories).

**`level doctor --category` (to migrate):**
- parser `uedcli/cli/parsers/level.py:152-154` — a single `default=None` string; help says
  "comma-separated categories to show".
- handler `uedcli/cli/commands/level.py:563-569` — comma-splits (`args.category.split(",")`);
  case-SENSITIVE membership test against `doctor.CATEGORIES`; on a bad value does a bare
  `print(...; file=sys.stderr); return 2` reporting the FULL set of unknown values.
- Its valid set is a FIXED enum: `doctor.CATEGORIES = ("degenerate", "watertight", "convex",
  "planar", "solidity", "csg_order", "scale")` (`uedcli/doctor.py:70-71`).

The divergence is a deliberate, recorded wart: the `class show` spec picked the better shape and
boarded this item to migrate the doctor rather than copy the doctor's older shape. `CommandError` is
the exit-2 carrier used throughout `level.py` (`uedcli/cli/errors.py:14`).

## Scope — what does and does not reconcile

The two flags are NOT the same kind of thing, and only the surface grammar reconciles:

- `class show --category` narrows AND changes the render (expands, sets unlimited depth). `level
  doctor --category` is a pure DISPLAY filter over `Finding.category` and stays one — there is no
  "expand" or "depth" concept for lint findings. Do not import that behaviour.
- `class show`'s available set is per-class; the doctor's is the fixed `doctor.CATEGORIES`. The
  listing on a miss lists `doctor.CATEGORIES` (already the case), just sorted for stable output.

So the reconciliation is exactly three axes: append (not comma-split), case-insensitive, and
`CommandError`-with-listing naming the first offender (not `print`+`return 2` naming all offenders).

## Design

Change `level doctor --category` to:

```
ldoc.add_argument("--category", dest="categories", action="append", default=[], metavar="NAME",
                  help="show ONLY findings in this category (degenerate, watertight, convex, "
                       "planar, solidity, csg_order, scale); repeat to OR several. Exact, "
                       "case-insensitive. Filters DISPLAY only — the exit code always reflects "
                       "all findings. An unknown category exits 2, listing the valid categories.")
```

Handler (`_level_doctor`, replacing `uedcli/cli/commands/level.py:563-569`):

```
if args.categories:
    valid_cf = {c.casefold(): c for c in doctor.CATEGORIES}
    for v in args.categories:                 # first value matching nothing is named (all-or-nothing)
        if v.casefold() not in valid_cf:
            raise CommandError(f"no category {v!r}; valid: {', '.join(sorted(doctor.CATEGORIES))}")
    wanted = {v.casefold() for v in args.categories}
    shown = [f for f in findings if f.category.casefold() in wanted]
else:
    shown = findings
```

`--severity` filtering and the exit-code-over-all-findings rule are untouched.

**Drop comma-split outright, no alias** (owner, 2026-08-02). The overview floated "keep accepting
comma-lists for back-compat if cheap"; the ruling overrides it. Per `direction/conventions.md` ("No
back-compat cruft — uedcli is unreleased") the append spelling is the only spelling: `--category A
--category B`, and a comma inside a value (`--category watertight,convex`) fails validation naming the
token `'watertight,convex'`. No dual-format comma-splitter.

## Edge cases

- Empty `--category` list (flag absent) → all findings shown, unchanged.
- Mixed good + bad values (`--category watertight --category bogus`) → exit 2 naming `'bogus'`,
  nothing printed, consistent with `class show` and multi-`--set` all-or-nothing.
- Case: `--category WATERTIGHT` matches `watertight` and filters correctly.
- `--json` + `--category` → the JSON list is the filtered `shown` set (unchanged wiring).
- A valid category that matched zero findings → clean empty report (not an error): the category is
  valid, it just has no findings, distinct from an unknown category.

## Tests

In the doctor CLI test module (alongside the existing `level doctor` tests — confirm location, likely
`test_dispatch.py` / a doctor test):
- `--category watertight` shows only watertight findings; a second `--category convex` OR-combines.
- `--category WATERTIGHT` (wrong case) filters the same as lowercase.
- unknown `--category bogus` → exit 2 naming `'bogus'` + the sorted valid list; nothing on stdout.
- good + bad mix → the FIRST bad value named, exit 2.
- a comma value `--category watertight,convex` → exit 2 naming the whole token `'watertight,convex'`
  (proves comma-split is gone).
- exit code still reflects ALL findings even when `--category` hides the ERROR ones (the existing
  invariant, re-pinned under the new flag).

## Docs to update on build

- `docs/usage.md` — the `level doctor --category` line (now repeatable + case-insensitive).
- No `architecture.md`/`direction/` change: the grammar is already documented for `class show`; this
  only removes a divergence.

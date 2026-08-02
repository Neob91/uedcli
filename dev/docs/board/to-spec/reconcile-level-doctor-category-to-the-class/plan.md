# Plan — reconcile `level doctor --category` to the `class show` shape

Build in a worktree (`andrzej/p3/doctor-category-append`). One merged commit. Pure CLI parse/validate
change; the doctor lint itself is untouched.

## Slice 1 — parser

Replace `uedcli/cli/parsers/level.py:152-154` (`--category` single string) with the append form:
`action="append"`, `dest="categories"`, `default=[]`, `metavar="NAME"`, help per spec (repeat to OR;
exact, case-insensitive; display-only, exit code always reflects all findings; unknown → exit 2
listing valid categories). Matches the `class show --category` grammar
(`uedcli/cli/parsers/classes.py:83-88`).

## Slice 2 — handler

Replace `uedcli/cli/commands/level.py:563-569`. Read `args.categories` (was `args.category`):

    if args.categories:
        valid_cf = {c.casefold(): c for c in doctor.CATEGORIES}
        for v in args.categories:                 # first miss named, all-or-nothing
            if v.casefold() not in valid_cf:
                raise CommandError(f"no category {v!r}; valid: {', '.join(sorted(doctor.CATEGORIES))}")
        wanted = {v.casefold() for v in args.categories}
        shown = [f for f in findings if f.category.casefold() in wanted]
    else:
        shown = findings

Uses `CommandError` (exit-2 carrier, `uedcli/cli/errors.py`) in place of the bare `print`+`return 2`.
`--severity` filter and the exit-code-over-all-findings rule (`level.py:561`, `572-574`) unchanged.

## Slice 3 — update existing + new tests

`uedcli/tests/test_doctor.py`:
- `_doctor_args` default (`test_doctor.py:334-335`): `category=None` → `categories=[]`.
- rewrite `test_dispatch_doctor_rejects_unknown_category` (`test_doctor.py:371-374`): pass
  `categories=["bogus"]`, assert exit 2 and the new message `no category 'bogus'; valid: …` on stderr.
- new: `categories=["watertight"]` shows only watertight; adding `"convex"` OR-combines.
- new: `categories=["WATERTIGHT"]` (wrong case) filters same as lowercase.
- new: good + bad mix `["watertight","bogus"]` → exit 2 naming `'bogus'`, nothing on stdout.
- new: comma token `categories=["watertight,convex"]` → exit 2 naming `'watertight,convex'` (proves
  comma-split is gone).
- new: valid category matching zero findings → clean empty report, exit still reflects all findings.

`uedcli/tests/test_dispatch.py:1703` parser-baseline row: `category=None` → `categories=[]` in the
expected namespace (append default).

Regenerate the parser-baseline fixtures with `python -m uedcli.tests.parser_baseline` and commit
`tests/fixtures/parser_baseline/{action_tree.json,help.json,argv_corpus.json}` — any parser-surface
change (here `--category` moving to `action="append"`, `dest="categories"`) reddens
`test_action_tree_matches_baseline` / `test_help_screens_match_baseline` (`test_parser_baseline.py`)
otherwise.

## Slice 4 — docs

`docs/usage.md` `level doctor --category` line: now repeatable + case-insensitive; drop any
comma-separated phrasing.

## Verify

`bin/test` green; formatter/linter/type-checker on touched files. Exercise:
`uedcli level doctor --category watertight --category convex` filters; `--category watertight,convex`
→ exit 2 naming the token; exit code still non-zero when `--category` hides the ERROR findings.

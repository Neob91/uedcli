# Composable `actor find` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give `actor find` an optional stdin name-set (`-`) that restricts the search to those actors (the grep/universe model), with `--exclude` inverting the predicate — enabling AND/OR/NOT queries by pipe composition.

**Architecture:** `find` already prints matching names to stdout. Add: when the trailing positional `-` is present, read a newline name-list from stdin, strict-resolve it to canonical names (the piped set `P`, the "universe"), and after the full filter chain produces `names`, keep `names ∩ P` (default) or `names ∖ P` (`--exclude`), preserving in-tree order. Pure read-path change in the `find` handler; no model/trunk change.

**Tech Stack:** Python 3.12, argparse (`_CoordArgumentParser`), pytest via `bin/test`. Spec: `dev/docs/specs/2026-07-24-composable-find.md`.

**Decisions locked (spec §7):** grep/universe model; `--exclude` spelling; keep `find -`; unknown piped names are a STRICT all-or-nothing exit 2.

---

## File Structure

- `uedcli/cli.py` — the `find` subparser gains a `-`-only trailing positional (`dest="restrict"`) and `--exclude`.
- `uedcli/dispatch.py` — the `find` handler (`if args.cmd == "actor" and args.sub == "find":`, ~line 3124) gains the universe restriction, applied to the final `names` (after the `--prop` block, before the print at ~line 3199), plus the `--exclude`-requires-`-` guard.
- `uedcli/tests/test_find_compose.py` — NEW: the grep-model behavior tests.
- `docs/usage.md` — the `find` reference gains the `-`/`--exclude` grammar + a boolean-queries example.

Reuse (do NOT reimplement): `_resolve_target_names(["-"])` (reads stdin, strips, drops blanks, empty→`[]`, `dispatch.py:148`); `query.resolve_actor_names(level, raw)` (canonical, case-insensitive, all-or-nothing — raises `KeyError("Actors not found: …")`, `query.py`).

---

## Task 1: CLI — add the `-` restrict positional and `--exclude` to `find`

**Files:**
- Modify: `uedcli/cli.py` (the `find = asub.add_parser("find", …)` block — add after its last filter argument, immediately before the `_tree_flag(find)` call)
- Test: `uedcli/tests/test_find_compose.py` (NEW)

- [ ] **Step 1: Write the failing test**

```python
# uedcli/tests/test_find_compose.py
from __future__ import annotations
from uedcli.cli import build_parser


def test_it_parses_find_restrict_and_exclude():
    p = build_parser()
    ns = p.parse_args(["actor", "find", "--group", "A", "--exclude", "-"])
    assert ns.restrict == "-"
    assert ns.exclude is True


def test_it_defaults_restrict_none_and_exclude_false():
    p = build_parser()
    ns = p.parse_args(["actor", "find", "--group", "A"])
    assert ns.restrict is None
    assert ns.exclude is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/human/src/dx_lum/Tools/uedcli && bin/test uedcli/tests/test_find_compose.py -x`
Expected: FAIL — `AttributeError: 'Namespace' object has no attribute 'restrict'` (the flags don't exist yet).

- [ ] **Step 3: Add the argparse entries**

In `uedcli/cli.py`, inside the `find` subparser block, just before `_tree_flag(find)`, add:

```python
    find.add_argument(
        "restrict", nargs="?", default=None, metavar="-",
        help="the single token - reads a newline-separated actor-name list from stdin and uses THAT "
             "set as the universe `find` searches (the filters become a predicate over it): "
             "`actor find --group A | actor find --group B -` = A AND B. Omit to search the whole tree.")
    find.add_argument(
        "--exclude", action="store_true",
        help="with -, keep the piped actors that do NOT match the filters instead of those that do "
             "(set difference): `find --group A | find --group B --exclude -` = A but not B. "
             "Requires -.")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/human/src/dx_lum/Tools/uedcli && bin/test uedcli/tests/test_find_compose.py -x`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git commit -m 'find: add `-` restrict positional + `--exclude` flag' -- uedcli/cli.py uedcli/tests/test_find_compose.py
```

---

## Task 2: Dispatch — the universe restriction + `--exclude` guard

**Files:**
- Modify: `uedcli/dispatch.py` (the `find` handler — insert the guard near its top, and the restriction immediately before the print: after the `if args.prop:` block ends with `names = matched`, before `if getattr(args, "json", False):`, ~line 3199)
- Test: `uedcli/tests/test_find_compose.py`

- [ ] **Step 1: Write the failing tests** (append to the test file; add the imports + helper at the top)

```python
import io
from types import SimpleNamespace
from unittest import mock

from uedcli.dispatch import dispatch
from uedcli.model import Actor, Level


def _lv(*names):
    lv = Level()
    for n in names:
        lv.actors[n] = Actor(name=n, cls="Engine.Brush", location=None, props=[])
    lv.order = list(names)
    return lv


def _find_args(**over):
    base = dict(cmd="actor", sub="find", name=None, cls=[], subclass_of=[], group=None,
                prop=[], folder=[], no_folder=False, kind=None, json=False, tree=None,
                restrict=None, exclude=False)
    base.update(over)
    return SimpleNamespace(**base)


def _run(args, level, stdin=""):
    src = mock.Mock(); src.load.return_value = level
    out = io.StringIO()
    with mock.patch("uedcli.dispatch._resolve_level_source", return_value=src), \
            mock.patch("sys.stdin", io.StringIO(stdin)), \
            mock.patch("sys.stdout", out):
        rc = dispatch(args)
    return rc, out.getvalue()


def test_it_intersects_the_piped_universe_with_the_filters():
    lv = _lv("A1", "A2", "B1")           # find all, restricted to the piped {A1, B1}
    rc, out = _run(_find_args(restrict="-"), lv, stdin="A1\nB1\n")
    assert rc == 0
    assert out.splitlines() == ["A1", "B1"]


def test_it_excludes_the_matches_from_the_universe_when_exclude():
    lv = _lv("A1", "A2", "B1")           # universe {A1,A2,B1}; predicate = name A2; exclude → drop A2
    rc, out = _run(_find_args(name=["A2"], restrict="-", exclude=True), lv,
                   stdin="A1\nA2\nB1\n")
    assert rc == 0
    assert out.splitlines() == ["A1", "B1"]


def test_it_keeps_in_tree_order_regardless_of_piped_order():
    lv = _lv("A1", "A2", "A3")
    rc, out = _run(_find_args(restrict="-"), lv, stdin="A3\nA1\n")
    assert out.splitlines() == ["A1", "A3"]        # tree order, not piped order


def test_it_resolves_piped_names_case_insensitively():
    lv = _lv("Wall_N")
    rc, out = _run(_find_args(restrict="-"), lv, stdin="wall_n\n")
    assert out.splitlines() == ["Wall_N"]


def test_it_errors_exit2_on_an_unknown_piped_name():
    lv = _lv("A1")
    rc, out = _run(_find_args(restrict="-"), lv, stdin="A1\nNope\n")
    assert rc == 2
    assert out == ""                                # nothing printed on error


def test_it_is_a_clean_noop_on_empty_stdin():
    lv = _lv("A1", "A2")
    rc, out = _run(_find_args(restrict="-"), lv, stdin="")
    assert rc == 0
    assert out == ""


def test_it_errors_exit2_when_exclude_without_dash():
    lv = _lv("A1")
    rc, out = _run(_find_args(exclude=True), lv)
    assert rc == 2
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd /home/human/src/dx_lum/Tools/uedcli && bin/test uedcli/tests/test_find_compose.py -x`
Expected: FAIL — the restriction isn't implemented, so intersection/exclude/strict-error don't happen.

- [ ] **Step 3: Implement the guard + restriction**

In `uedcli/dispatch.py`, in the `find` handler, right after `level = src.load()` (currently ~line 3132), add the guard:

```python
        if getattr(args, "exclude", False) and getattr(args, "restrict", None) != "-":
            raise _SelectionExit("--exclude requires - (a piped name-set to exclude from)")
```

Then, immediately before the print block (after the `if args.prop:` block, before `if getattr(args, "json", False):`), add:

```python
        # Composable-find grep/universe model (spec 2026-07-24-composable-find): `-` makes the piped
        # name-set the universe; the filters above are the predicate; --exclude negates it. Applied to
        # the FINAL `names` (post --prop), in-tree order preserved.
        if getattr(args, "restrict", None) == "-":
            raw = _resolve_target_names(["-"])
            try:
                universe = set(query.resolve_actor_names(level, raw))   # strict, all-or-nothing
            except KeyError as e:
                print(e.args[0], file=sys.stderr)
                return 2
            matched_set = set(names)
            keep = universe - matched_set if getattr(args, "exclude", False) else universe & matched_set
            names = [n for n in names if n in keep]
```

- [ ] **Step 4: Run to verify they pass**

Run: `cd /home/human/src/dx_lum/Tools/uedcli && bin/test uedcli/tests/test_find_compose.py -x`
Expected: PASS (all tests, including Task 1's).

- [ ] **Step 5: Run the whole suite (no regressions)**

Run: `cd /home/human/src/dx_lum/Tools/uedcli && bin/test -k find`
Expected: PASS — existing `find` tests unaffected (the restriction is inert when `restrict` is None).

- [ ] **Step 6: Commit**

```bash
git commit -m 'find: apply stdin name-set universe restriction (grep model) + --exclude guard' -- uedcli/dispatch.py uedcli/tests/test_find_compose.py
```

---

## Task 3: Docs — `find` reference

**Files:**
- Modify: `docs/usage.md` (the `actor find` section)

- [ ] **Step 1: Update the `find` docs**

In `docs/usage.md`, in the `actor find` section, add a subsection documenting the `-` universe input and `--exclude`, with the boolean-queries block from the spec §2:

```markdown
**Boolean queries — `find <filters> -`:** with a trailing `-`, `find` reads a newline actor-name list
from stdin and searches ONLY that set (the "universe"); the filters are the predicate. `--exclude`
keeps the non-matches instead. This composes into full boolean logic:

    actor find --group A | actor find --group B -            # A AND B
    actor find --group A | actor find --group B --exclude -  # A but NOT B
    { actor find --group A; actor find --group B; } | sort -u | actor find -   # A OR B (re-normalized)

Unknown piped names are a hard error (exit 2). `find -` with no filters echoes the piped set (a strict
validator).
```

- [ ] **Step 2: Verify the doc renders and matches behavior**

Read the edited section; confirm the three examples match the tests in Task 2.

- [ ] **Step 3: Commit**

```bash
git commit -m 'docs: composable `find` (-/--exclude) boolean queries' -- docs/usage.md
```

---

## Self-review checklist (run before handoff)

- Spec §2 (grep model), §3 (semantics: universe, `--exclude`, in-tree order, empty-stdin no-op, `--tree`-agnostic), §3.1 (strict unknowns), §7 (resolved sub-choices) — all covered by Tasks 1–3.
- No placeholders; every step has real code/commands.
- Type/name consistency: `restrict`/`exclude` arg names match between cli.py, the handler, and the test `_find_args` helper. `_resolve_target_names`/`resolve_actor_names` used with their real signatures.

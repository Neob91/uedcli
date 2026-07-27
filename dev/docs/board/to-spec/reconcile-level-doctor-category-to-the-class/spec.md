# `class show --category` — filter to specific editor categories

**Status:** BUILT 2026-07-18 (folded into `architecture.md` "class show" bullet + `decisions.md`
2026-07-18 10:03 UTC; this ephemeral spec may be pruned). A small extension to `class show` (the class-discovery verb,
`specs/2026-07-17-class-discovery-and-author-validation.md`): let the caller narrow the output to one
or more editor **categories** (`Movement`, `Lighting`, `AI`, …), so "what Movement properties does
this class have?" is a direct query rather than eyeballing the whole grouped dump.

**Why a flag and not `class show <C> --all | grep`** (this IS a filter flag, against the project's
"verbs compose; don't sprinkle filter flags" rule — so it needs a real justification): grep
fundamentally can't do it. (a) In the DEFAULT view a category's inherited props are collapsed to a
`(+N inherited …)` COUNT — `grep Movement` returns the count line, never the props. (b) A property
line carries no category label; the category appears ONLY in the `\n<Category>:` section header, so
grep matches the header but not the props under it, and slicing a multi-line section by hand is
fragile. `--category` changes the *render* (expands + narrows) — an accepted, narrow, one-flag
exception to the compose rule (the non-goals below hold the line: no filtering by kind/name/regex).

Decisions (+ rejected alternatives) are recorded in [`decisions.md`](../../../decisions.md) 2026-07-18; this
spec is ephemeral scratch.

## Recap of what `class show` produces today
`class show <Package.Class>` prints editable properties grouped by editor category (a prop's
`Prop.category`, decoded from the `.u`; non-editable plain `var` props have no category and are
hidden). DEFAULT lists the class's OWN props per category with inherited props collapsed to
`(+N inherited, from M superclasses)` counts; `--all` expands (own + inherited per category, inherited
tagged `← Package.Class`); `--depth N` limits superclass hops.

## The filter

**`--category NAME` — repeatable, exact, case-insensitive, OR-combined** (Andrzej 2026-07-18):
`class show Engine.Actor --category Movement --category Lighting` shows only those two categories.
Repeatable-append is the majority filter pattern in this CLI — genuinely repeatable (`action="append"`,
argument-on-the-flag) precedents are `actor find --class/--group/--name` and `texture search --tag`.
*Rejected:* a comma-list `--category A,B`; substring/fuzzy matching (a short token silently matching
several categories).

**Divergence from the existing `level doctor --category` — acknowledged, and reconciled by a
follow-up (review fix).** `level doctor` ALREADY has a `--category` flag, but it is **comma-split,
case-sensitive**, and its unknown-value path is a bare `print(...); return 2`. This spec deliberately
picks the OPPOSITE on every axis (repeatable-append, case-insensitive, `_SelectionExit`-with-listing)
because that shape is better and matches the majority pattern above — but shipping two same-named
flags that parse/fail differently is a real wart. So this spec does NOT copy `level doctor`'s shape;
instead it BOARDS a follow-up to migrate `level doctor --category` to the same append + case-insensitive
+ listing shape (a separate, backward-compatible-ish change — comma-lists still work if the migration
also accepts them). Until then the two differ, and the decision records why.

**A `--category` renders the matched categories EXPANDED, at unlimited depth by default.** Precisely
(the milder framing the review clarified): `--category` (a) narrows to the matched categories AND (b)
sets the view to the **expanded** rendering (own + inherited props, inherited FQCN-tagged — the `--all`
Style-C form) rather than the collapsed `(+N inherited …)` count, AND (c) sets the default superclass
depth to **UNLIMITED**. Rationale: if you asked for a category you want to *see* its properties, not a
count — and for a derived class a category is often entirely inherited (`ScriptedPawn --category
Movement` is all from `Engine.Actor`, so a count shows nothing). So `--category X` is the *selective*
form of `--all` (expand only X).
- `--depth N` still overrides (superclass hops from the class, own = 0): `--category Movement --depth 1`
  = the class's own + immediate-parent Movement props.
- **Budget difference from bare `--all`, called out (review fix):** unfiltered `--all` auto-truncates
  its depth at the ~60-line budget; `--category` defaults to unlimited depth (a single category is
  narrow, so the budget is unhelpful). The `kshow` help + decisions.md state this so it isn't
  surprising ("`--category` sets the depth default to unlimited").
- **The "omitted superclass levels" trailer is recomputed for the filter (review fix):** the existing
  `(+N more superclass level(s) omitted — --depth M …)` note uses `max_hop` over ALL editable props;
  under `--category` it must be recomputed over the WANTED categories only (`max(hop(p) for p in
  editable if p.category.casefold() in wanted)`), so it never reports levels that hold no wanted-
  category props. With the unlimited default it usually won't fire at all (only when `--depth N`
  clips a wanted category).
- `--all --category X` = `--category X` (the `--all` is subsumed; harmless — there is no distinct
  "expand every category but print only X").
- No `--category` → today's behavior is unchanged (default collapsed counts / `--all` / `--depth`).

**Matching set = the class's actual categories.** The categories eligible for matching (and listed on
a miss) are the distinct `Prop.category` values across the class's editable props (own + inherited, all
depths) — i.e. exactly the section headers the unfiltered `--all` would print. NB these include the
`var()` class-name pseudo-categories (a `var()` prop's category is its *declaring class name*, so
`available` for `Engine.Actor` lists `Actor`/`Pawn`/… alongside true editor groups like `Movement`);
that's intended (`--category Actor` selects that class's ungrouped section) — an implementer must not
"fix" it out.

**The missing-ancestor degrade path REJECTS `--category` (review fix).** The show handler falls back
from `resolve_class_properties` to `own_class_properties` when an ancestor package is unresolvable —
in which case `editable` is OWN props only, so "available = all depths" is a lie and a genuine
*inherited* category would be mis-reported as unknown. So when that degrade happens AND `--category`
was given, exit 2 with `cannot filter by category: inherited schema unavailable (<pkg> missing)` —
never a false "unknown category" or a silently-own-only filter.

**Unknown category → exit 2, listing the class's categories** (Andrzej 2026-07-18): a `--category` that
matches none of the class's categories is a clean `_SelectionExit` naming the offending value and
listing what IS available, e.g.
`no category 'Movment' on Engine.Actor; available: Advanced, Collision, Display, Lighting, Movement, …`
(sorted). *Rejected:* empty output + a stderr hint (a typo would silently yield nothing on stdout —
against the tool's no-silent-miss stance). If SEVERAL `--category` values are given, the FIRST that
matches nothing is named (all-or-nothing — consistent with multi-`--set` in `actor prop`). **A class
with NO editable categories** (`available == []` — e.g. an abstract class whose only props are
non-editable plain `var`) gives `class show <C> has no editable categories` (exit 2), not a dangling
`available: ` (review fix).

## Discoverability (review fix — small change to the EXISTING default view)
To use `--category X` you must know X. Today the default view's truncation trailer says only `(+N more
own categories hidden — use --all)` WITHOUT the names, so for a class whose own categories overflow the
~60-line budget you can't see the category names to filter by (the only complete source is the unknown-
category error message — a backwards discovery path). Fix: make that trailer **list the hidden own-
category names** (`(+N more own categories hidden: Foo, Bar, … — use --all)`) — names are short, and
the budget concern is prop LINES, not headers. This makes `class show <C>` (default) a complete
category listing, so `--category` is discoverable without `--all` or a deliberate typo. (Also keep the
tail `(+TOTAL inherited, in K more categories: …)`, which already lists names.)

## Non-goals
- Filtering `class list` by category (categories are a property-of-props concept, not a class concept).
- Filtering by property KIND (BoolProperty/…) or by name/regex — out of scope; `class show <C> | grep`
  covers ad-hoc text filtering, and category is the meaningful structural axis.
- A "show non-editable internals" escape — plain `var` props stay hidden (they carry no category, so
  a category filter can't reach them anyway).

## Implementation sketch
In `dispatch._dispatch_class`'s `show` branch (all model-side; `classindex`/`uprops` already provide
the data):
- Add `--category` (`action="append"`, `dest="categories"`, default `[]`) to `cli.py`'s `kshow`.
- After building `editable`, if `args.categories`:
  - If the `resolve_class_properties` DEGRADE fired (own-props-only fallback) → exit 2 "cannot filter
    by category: inherited schema unavailable (<pkg> missing)" (don't compute a false `available`).
  - `available = sorted({p.category for p in editable})`. If `available == []` → exit 2 "class <C> has
    no editable categories".
  - `avail_cf = {c.casefold(): c for c in available}`. For each `--category` value (in order), the
    FIRST whose casefold ∉ `avail_cf` → `_SelectionExit` naming it + `available` (sorted). Then
    `wanted = {v.casefold() for v in args.categories}`.
- **Make the expanded branch also trigger on `--category`:** its guard is `if show_all or depth is not
  None:` — change to `if show_all or depth is not None or args.categories:`, else a bare `--category X`
  falls through to the DEFAULT collapsed branch.
- In `render(eff)`, filter the category loop by `cat.casefold() in wanted` when `wanted` is set (compare
  casefolded; still print the canonical `cat` header). Default `eff = max_hop` for the wanted set unless
  `--depth` given; recompute the omitted-levels trailer over the wanted set (see above).

## Tests / verify
Offline, in `test_ingest_validation.py` (where the other `class show` tests live — mock
`resolve_class_properties` / a fake `ClassIndex`):
- `--category Movement` shows only the Movement section, EXPANDED (own untagged + inherited
  `← Package.Class`); other categories absent; no collapsed `(+N inherited …)` lines. The header +
  `super:` line still print (they're unconditional).
- Two `--category` values → both sections, OR-combined; case-insensitive (`--category movement` matches
  `Movement` and prints the canonical `Movement:` header).
- `--all --category X` produces output identical to `--category X` (the equivalence, asserted).
- `--category X --depth 0` → own props of X only; `--depth 1` adds the immediate parent's; the omitted-
  levels trailer (if any) counts only X's superclass levels, not the whole class's.
- An unknown `--category Bogus` → exit 2 naming `Bogus` + the sorted `available`; a mix of good+bad →
  the FIRST bad value named, nothing printed.
- A class with NO editable categories + `--category X` → exit 2 "has no editable categories".
- The missing-ancestor DEGRADE path + `--category X` → exit 2 "inherited schema unavailable", not a
  false "unknown category".
- A category that is entirely inherited (no own props) still shows its (inherited) props under
  `--category` (the motivating case) — not just a count.
- The default-view discoverability change: the `(+N more own categories hidden: …)` trailer now LISTS
  names.
Live: `class show Engine.Actor --category Movement` and `class show DeusEx.ScriptedPawn --category AI`
show the expected focused, expanded sections.

## Docs to update on build
- `architecture.md` (the `class show` line) — note the `--category` filter + the default-view trailer
  now listing names. (The durable home; the sibling 2026-07-17 spec is ephemeral, so editing its
  bullet is optional.)
- `cli.py` `kshow` help for `--category` (note it expands + defaults to unlimited depth).
- `decisions.md` — the 2026-07-18 entry this spec links to.
- `board/inbox.md` — the follow-up to reconcile `level doctor --category` to the append + case-
  insensitive + listing shape.

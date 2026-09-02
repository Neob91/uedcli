# Spec: orthogonalize `class list` / `class show` flags — kill the overloaded `--all`

**Status:** BUILT + landed in `7b7664a67` (2026-07-19) — source, migrated tests (green), and the
`decisions.md` entry all shipped in that commit. `--depth all` is uncapped (Andrzej, 2026-07-24).
Decision ledger: `decisions.md` 2026-07-19 entry. **Ephemeral** — durable bits are in `decisions.md` +
the CLI help; this file is kept only for reference and may be pruned.

## Problem

`--all` is overloaded and its *name* misleads. Empirically (measured on the DX path), `class list
--all` bundles **three unrelated effects**, and — the crux — the name promises the one it does NOT
reliably deliver (depth):

| Effect | Where it applies | Triggered today by |
|---|---|---|
| **E1 — reroot** `Engine.Actor` → `Core.Object` (adds the non-Actor world: `Object`, `Texture`, `Sound`, field/property classes) | tree + flat | `--all` |
| **E2 — drop the placeable filter** (adds abstract / non-placeable classes) | `--flat` drill (`--subclass-of`), `--package` flat | `--all` |
| **E3 — full depth**, no `(N)` collapse / no ~60-line budget | tree render depth | ONLY `--all --flat`; tree `--all` is still collapsed (107 lines, not the full 2034) |

So a user typing `--all` expecting "see every nested class" (E3) instead gets E1+E2 and a *still-
collapsed* tree. Same word means a *different* thing on `class show` (`--all` = expand all inherited
props / unlimited depth), compounding the confusion.

Decision (Andrzej, 2026-07-18): split the scope effects into their own flags and let *depth* be
expressed as depth — the same spelling on **both** verbs.

## Target model

### The depth knob — `--depth N | all` (both `class list` and `class show`)

`--depth` accepts a non-negative integer **or** the literal keyword **`all`** (= unlimited / ∞).
`--depth all` is the whole thing: the full class tree with no `(N)` collapse and no line budget
(`class list`), or the entire super-chain of inherited props (`class show`). Internally `all` is
carried as a sentinel (`math.inf`); `--depth` is the SOLE depth control on both verbs.

- Rejected: a separate boolean (`--all` / `--full` / `--recursive`). A depth *value* reads as exactly
  what it is ("depth = all"), needs no new flag, and is automatically consistent across the two verbs
  (both already have `--depth`). Rejected keyword synonyms (`max`, `inf`): one spelling, `all`.

### `class list` — two new scope flags replace `--all`

`--all` is **removed** (hard rename, pre-release, no alias — as `--isa`→`--subclass-of`). The two
scope effects become independent, single-purpose flags:

- **`--include-non-actor`** → E1. Reroots the default tree/flat root from `Engine.Actor` to
  `Core.Object`, so the non-Actor class world is in scope. No-op when `--subclass-of X` is given
  (that sets the root explicitly). This is the ONLY way to reach non-Actor classes short of
  `--subclass-of Core.Object`.
- **`--include-abstract`** → E2. In the views that filter to placeable (the `--subclass-of` `--flat`
  drill and `--package` `--flat` list), stop hiding abstract / non-placeable classes. The **tree view
  is unaffected** — it already shows abstract classes as branch-points (marked `*`); this flag is a
  no-op there. Likewise a no-op for the bare depth-1 category view (which already lists abstract
  categories like `Engine.Light`).

### `class show` — drop `--all`, use `--depth all`

`--all` is **removed**. Unlimited inherited-prop depth is `--depth all`. `--depth all` and
`--category` both expand the whole chain (as today for `--category`); `--depth N` clips to N hops. The
no-flag DEFAULT (collapsed own-props + inherited counts) is **unchanged**.

## Behavior preservation (defaults do NOT shift)

The new flags only ADD what `--all` used to bundle; every current default output is preserved:

- `class list` (bare tree): unchanged — `Engine.Actor` root, depth auto-fits ~60 lines, abstract `*`,
  `(N)` collapse.
- `class list --flat` (bare): unchanged — the ~40 depth-1 categories.
- `class list --subclass-of X --flat`: unchanged — placeable leaves (add `--include-abstract` for the
  abstract ones).
- `class list --depth N`: the structural browse to N levels — **fully unchanged.** (Design review F1:
  `--depth` today already sets `placeable_only=False`; it is NOT changed here. `placeable_only` stays
  a per-branch decision — the ONLY edit is the `--subclass-of` drill branch `not include_all` →
  `not include_abstract`, plus `--package` honoring `--include-abstract`. The default category view
  and the `--depth` browse keep `placeable_only=False`, so their output is byte-identical and
  `--include-abstract` is correctly a no-op there.)
- `class show` (bare / `--depth N` / `--category`): unchanged except `--all` → `--depth all`.

## Migration map (old → new)

| Old | New |
|---|---|
| `class list --all` (tree, Core.Object root) | `class list --include-non-actor` |
| `class list --all --flat` (literally every class, 2034 incl. `Core.Object`) | `class list --subclass-of Core.Object --include-abstract --flat` (F2: `--subclass-of` disables the `d==0` root-skip so `Core.Object` is included; `--include-non-actor` alone would drop the root) |
| `class list --subclass-of X --all --flat` (drill incl. abstract) | `class list --subclass-of X --include-abstract --flat` |
| `class list --subclass-of Engine.Actor --all --flat` (all Actor descendants incl. abstract) | `class list --subclass-of Engine.Actor --include-abstract --flat` (F4: the old form was NOT placeable-filtered) |
| `class show C --all` | `class show C --depth all` |

**Note (F2):** `--include-non-actor` reroots the flat list at `Core.Object` but the `d==0` root-skip
(classindex.py:290, so `Engine.Actor` never appears in its own placeable list) still fires ⇒ the flat
`--include-non-actor` list EXCLUDES `Core.Object` itself, and classes whose super-chain truncates
(unparseable/missing ancestor package) are unreachable from any root. The faithful "every fqcn on the
path" dump is `--subclass-of Core.Object --include-abstract --flat`. The old bare-`--all` early-return
(`return self._sorted(cands)`, classindex.py:274) is REMOVED — there is no longer an unrooted path.

## Implementation surface

- `cli.py`: a `--depth` type function `depth_value(s) -> int | float('inf')` (accepts `all`), applied
  to both `klist` and `kshow`. Remove both `--all` (`include_all`) args. Add `klist`
  `--include-non-actor` (`include_non_actor`) and `--include-abstract` (`include_abstract`). Rewrite
  the three `class list` / `class show` help strings + the `class list`/`class show` parser help.
- `classindex.py` `list_classes(...)`: replace the `include_all` param with `include_non_actor` +
  `include_abstract`; `depth` now `int | inf | None`. Root = `subclass_of or (CORE_OBJECT if
  include_non_actor else ENGINE_ACTOR)`. `placeable_only` driven by `include_abstract` only (decoupled
  from depth). `depth is inf` ⇒ unlimited (`eff = None`).
- `dispatch.py` `_class_tree(...)`: `include_all` → `include_non_actor` for the root pick; `depth` inf
  ⇒ render full (no budget auto-grow, no `(N)` collapse where depth permits). `_dispatch_class`
  `show`: `show_all`/`--all` gone; `depth == inf` drives the unlimited expanded view; keep
  `--category` unlimited.
- Tests: update `test_class_discovery.py` (`include_all=True` call sites → new params), add coverage
  for `--depth all` (both verbs), `--include-non-actor`, `--include-abstract`, and the migration-map
  equivalences. Update any `test_cli`/`test_dispatch` arg-parsing expectations.
- Docs: `decisions.md` entry (supersedes the `--all` points in the 2026-07-17 `class` entry, the
  10:56 `class list` entry, and the 10:03 `--category` entry); reconcile `direction.md` only if it
  names `--all` (it does not today); help text is the primary user-facing doc.

## UX-review resolutions (cold review 1, adopted)

- **`--depth` metavar `N` → `N|all`** on both verbs, so `-h`/usage advertises the keyword (else it's
  invisible). This is the load-bearing discoverability fix. (`all`-as-a-value is already CLI
  vocabulary here — `brush poly set Wall1:all` — so it's consistent, not novel.)
- **Removing `--all` emits a TARGETED hint, not opaque `unrecognized arguments`.** Because `--all`
  split three ways, keep a hidden `--all` arg on both verbs whose handler raises a clean exit-2 error
  pointing at the replacements: `class list: --all was split — use --include-non-actor (non-Actor
  classes), --include-abstract (abstract/non-placeable), and/or --depth all (full depth).` (show:
  `--all → --depth all`.) A legible removal, NOT a zombie alias.
- **`--include-abstract` scopes its help to where it acts** and **prints a one-line stderr note when
  passed in a context where it is a no-op** (tree / bare category), so it never reads as broken.
  Help: "in the `--flat` drill and `--package` flat list, also show abstract / non-placeable classes
  (hidden there by default). No effect on the tree — it already shows abstract branch-points (`*`)."
- **`--include-non-actor` help states the default scope first:** "also list non-Actor classes
  (`Object`, `Texture`, `Sound`, field/property classes) by rerooting at `Core.Object`. Default scope
  is Actor subclasses only. No-op with `--subclass-of`."
- **Reword the STALE `--all` cross-refs inside OTHER flags' help** — `class show`'s `--depth` and
  `--category` help both currently say "like `--all`" / "Like `--all`"; retarget to `--depth all`.
- **`depth_value` type fn**: accept a non-negative int OR case-insensitive `all` (→ `math.inf`); on a
  bad token raise `argparse.ArgumentTypeError` naming it (`invalid depth 'als': expected a
  non-negative integer or 'all'`) — never an int-parse traceback (tool convention: errors name the
  offending value). `--depth 0` = root only (valid, tested). Negative rejected.
- **Decision-entry wording:** `--depth` is *analogous*, not identical, across the verbs (list = descend
  levels; show = superclass hops + flips to expanded view). Don't claim full symmetry.

## Design-review resolutions (cold review 2, adopted)

- **F1 (critical):** do NOT globalize `placeable_only`. `list_classes` keeps its per-branch
  `placeable_only`: the `depth` branch and the default category branch stay `False` (so their output
  and `test_list_classes_default_is_the_category_view` / `test_list_classes_depth_is_a_structural_browse`
  are unchanged); only the `--subclass-of` drill flips `not include_all` → `not include_abstract`, and
  `--package` becomes `True and not include_abstract`. `--depth` is unchanged.
- **F2/F4:** migration map corrected above (every-class dump = `--subclass-of Core.Object
  --include-abstract --flat`; the `--subclass-of Engine.Actor --all` row was not placeable-filtered).
  The bare-`--all` early-return in `list_classes` is removed with `include_all`.
- **F3:** `test_ingest_validation.py` is ALSO in the test surface — it uses `include_all` at ~7 sites
  and a `_run_class_cap` helper (line ~408) hardcoding `include_all=False, flat=False, depth=None,
  categories=[]` on the Namespace. Dispatch reads `args.include_all` **directly** (not `getattr`) in
  the `class list` branch, so every constructed Namespace + `list_classes(...)` call there must move to
  `include_non_actor`/`include_abstract` or it `AttributeError`s.
- **F5:** `depth_value(s)`: strip + casefold; `all` → `math.inf`; else `int(s)` and REJECT `< 0` with
  `argparse.ArgumentTypeError(f"invalid depth {s!r}: expected a non-negative integer or 'all'")`.
  `--depth 0` is valid (root only; bare flat `--depth 0` is legitimately empty). `list_classes` maps
  `depth == inf → eff = None` (unlimited) explicitly.
- **F6:** `math.inf` verified safe in `_class_tree` (`max(0, inf)`, only `d >= maxd`/`d > eff`
  comparisons) and `class show` (`min(inf, max_hop)` → the int `max_hop`). No `range`/slice/`%d` on the
  depth sentinel.
- **F7 (stale help to rewrite, exact sites):** `klist` parser help "rooted at Engine.Actor …
  --depth to go deeper" (cli.py ~817-820); `klist --depth` help (document `all`, ~831-834); `kshow`
  parser help "--all lists every inherited prop too" (~842-843); `kshow --all` (removed → hint);
  `kshow --depth` "(like --all)" (~852-853); `kshow --category` "Like --all this expands the whole
  chain" (~858). All `--all` mentions retargeted to `--depth all` / the split flags.

## Open questions for review
1. The `--depth`-decouples-from-placeable change (above) — any caller / test / doc relying on the old
   `--depth ⇒ unfiltered` coupling?
2. Should `--depth all` cap anything for safety (Core.Object full tree ≈ 2034 lines), or is the
   firehose the explicit intent of `--depth all`? (Proposed: no cap — the user asked for all.)
3. `--depth 0` on `class list` — the root only (no children)? Confirm it's meaningful / not an error.

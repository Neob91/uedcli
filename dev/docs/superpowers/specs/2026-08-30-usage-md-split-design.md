# `usage.md` split — design

Owner-directed brainstorm, 2026-08-30. Follows the same-day docs-structure review (two independent
agents) and the `docs/superpowers` → `dev/docs/superpowers` move.

## Problem

`docs/usage.md` is a single topic key serving 139,080 bytes (~34,770 tokens) for *any* lookup,
even a two-line command like `cache clear`. Measured effects:

- `docs show usage` always costs ~35k tokens regardless of what's needed.
- `docs search` is a literal-substring match over one giant blob; two real, implemented verbs
  (`music classify {set,unset,status,tags}`, `prefab list`/`prefab drop`) return **zero hits**
  because their exact phrasing never appears together in the text (board item
  `docs-search-cannot-find-music-classify-or`).
- Heading taxonomy breaks down partway through the file (duplicate `## Actors` anchor, H1 siblings
  that silently stop nesting under the `Query verbs` / `Mutating verbs` split) — board item
  `usage-md-is-a-single-2001-line-topic-key-with`.
- `docs/leveldesign/**` and `usage.md` are barely cross-linked (2 links in, 0 out) — board item
  `leveldesign-and-usage-md-are-barely-cross-linked`.
- `docs/README.md` under-enumerates capabilities (omits class/sound/music catalogs, level
  import/reimport/doctor, event graph, folders/labels, movers, measure relation, substrate/cache)
  — board item `docs-readme-md-under-enumerates-uedcli`.

This design resolves all four board items above. It does **not** address
`no-quickstart-first-level-walkthrough-exists-in` (separate, additive work) or build the
argparse→markdown generator (explicitly deferred — see Non-goals).

## Goals

- An agent gets **cursory awareness of every capability cheaply**, and pays for **detail only when
  it fetches a specific page**.
- Every fact lives at exactly one file — no generated/duplicated content, no drift risk beyond
  what the existing dead-link lint already catches.
- The structure mirrors the CLI's own organization (parser modules, and their own sub-verb
  groupings for the largest families) so it stays obviously correct as the CLI grows, with no
  separate taxonomy to keep in sync by hand.

## Non-goals (explicitly deferred, not forgotten)

- **argparse → markdown generator.** Real, separable engineering (format design, generation
  script, CI drift-guard — same shape as the deferred `bundle-the-user-facing-docs-into-the-wheel`
  board item). Measured that generation timing doesn't change token economics — the split alone
  delivers the reduction — so this is a fast-follow, not a blocker. File a board item for it
  after this ships.
- **Literal content inclusion/transclusion** (a family page containing its leaf pages' full text).
  Would need the same kind of generator + drift-guard. Family pages are plain links instead.
- **A CLI-verb documentation-completeness lint.** Explicitly rejected by the owner earlier the same
  day — the dead-link lint (`test_the_real_docs_tree_has_no_dead_links`) is the only automated
  guard; it structurally can't miss a *linked* page going stale, but doesn't (and won't) assert
  that every CLI verb has a page.
- **The quickstart walkthrough** (board item `no-quickstart-first-level-walkthrough-exists-in`) —
  unrelated, additive content, not a restructuring byproduct.

## Architecture

Three tiers, entirely plain markdown + links — no new code in `userdocs.py`:

```
docs/README.md                         topic "index"     — top-level orientation + capability table
docs/usage/<family>.md                 topic "usage/<family>"          — flat, for small families
docs/usage/<family>/README.md          topic "usage/<family>"          — index, for large families
docs/usage/<family>/<command>.md       topic "usage/<family>/<command>" — leaf content
```

The large-family case relies on `userdocs.py`'s existing README-folding rule (a `README.md` folds
to its containing directory's topic key) — already exercised by `docs/leveldesign/`. No new
serving logic. The existing duplicate-topic-key hard-error (`direction/conventions.md`'s
ambiguous-served-set ruling, filed earlier the same day) is the safety net if a family ever
accidentally got both a flat file and a directory.

**Rule for flat vs. directory:** a family's total current content, roughly:
- **> ~10,000 bytes → directory**, split along the family's own natural sub-verb groupings
  (mirroring its own argparse subparsers where it has them).
- **≤ ~10,000 bytes → flat file**, no split.

Measured sizes (today's `usage.md`, by future family):

| Family | Bytes | Treatment |
|---|---:|---|
| actor (CRUD, no preview) | 22,858 | directory |
| actor preview | 17,661 | *(own leaf under `actor/`, see below)* |
| brush (poly/vertex/core/intersect) | 21,363 | directory — **not** 22,762: that figure (from the raw 260–309/548–734/1019–1126 line ranges) still includes the 1,399-byte `--tree` block, which goes to `docs/README.md` (see below) |
| brush build (generators) | 13,357 | *(own leaf under `brush/`)* |
| level (doctor/import/reimport/materialize/preview) | 18,422 | directory — **not** 19,417: that figure still includes `event graph`'s 995 bytes, which goes to its own page (see below). `create`/`list`/`status` were never in this figure — they're front matter (see below) |
| class | 13,216 | directory — over the 10,000-byte threshold, no need to leave this open |
| mover | 4,508 | flat |
| sound+music | 4,070 total | **two** flat files (`sound.md`, `music.md` — separate parser modules; do not merge) |
| stash+prefab | 3,615 total | **two** flat files (`stash.md`, `prefab.md` — separate parser modules) |
| texture | 3,620 | flat |
| docs | 2,978 | flat |
| cache+substrate | 975 | flat, one file each (tiny; do not force a directory) |
| event | 995 | flat — see "Content that doesn't move cleanly" below, this is a paragraph *extracted from inside* `level`'s content, not a free-standing move |
| project | 234 | flat, `project show` only (lines 109–111) — see below, the rest of the `uedcli.toml` section is front matter, not this page |

Front matter — composability rules, level selection, stdin/exit-code conventions — folds into
`docs/README.md`, which becomes the sole entry point. The `usage` topic key retires entirely: no
stub, no redirect (no-back-compat-cruft convention). `docs/usage/` itself has **no** `README.md` —
it's a pure namespace prefix, so the retired `usage` key can never be accidentally resurrected.

### Content that doesn't move cleanly (two rounds of independent spec review caught these)

Four pieces of content don't have a single obvious destination, because they're embedded inside a
*different* family's prose block in today's file rather than living in their own section. Resolved
explicitly here so no implementer has to re-derive it. (Round 1 caught that these four had no
stated destination; round 2 caught that fixing the destinations didn't yet fix the byte totals
above, or the table's own `import`/`reimport` rows — both are fixed in this pass, with every figure
below recomputed directly against `git show 91e4bbf:docs/usage.md`, not estimated.)

- **`uedcli.toml` project config** (lines 62–112, 3,530 bytes) is a *concept* (how projects/games
  are configured), not a command — it stays in `docs/README.md`'s front matter, same as today.
  **`project show`** (the CLI verb — lines 109–111, 234 bytes, a bolded block, not a parenthetical;
  the parenthetical at line 107 is a passing mention, not the verb's own text) is a *command* — it
  gets pulled out into its own tiny `docs/usage/project.md` leaf. Same underlying section, two
  different destinations for two different kinds of content; not a duplication.
- **`event graph`** (lines 366–380, exactly 995 bytes) is embedded inside "Level lint & trigger
  wiring," directly after `level doctor`'s prose, with no heading separating them — that whole
  block is what today counts toward `level`'s raw 19,417-byte figure (corrected to 18,422 above).
  Moving `event graph` out is a **paragraph-level extraction from the middle of `level`'s content**,
  not a same-shape move to a same-size neighbor like `cache`/`substrate` — flagging this explicitly
  so the implementer doesn't go looking for it near the file's tail (where `cache`/`substrate`
  actually sit) and conclude it's missing.
- **The "Choosing a level" table** (lines 129–135) has five rows, not three: `create`, `import`,
  `reimport`, `list`, `status`. Only `create`/`list`/`status` (lines 131, 134, 135 — exactly 700
  bytes, not the 1,240 an earlier pass claimed, which accidentally summed all five rows) need a new
  home: they **move** (not duplicate) into a combined `docs/usage/level/` leaf, one small leaf per
  the existing "small subgroup" precedent (matches `actor/prop.md`, `actor/folder.md`). The
  `import`/`reimport` rows (262 + 241 = 503 bytes) are **not** part of this move — they're already
  short cross-references into the full `level import`/`level reimport` H1 sections (already counted
  in `level`'s figure); they stay as two rows in `docs/usage/level/README.md`'s own index, same
  pattern as every other family README. The surrounding concept prose (lines 113–128, 841 bytes —
  what `UEDCLI_LEVEL` is, why there's no `level select` verb) stays in `docs/README.md`.
- **`` `--tree KIND/NAME` ``** (lines 716–734, 1,399 bytes) sits inside brush's mutating-verb line
  range by accident of file position, but its own text says it rides `actor`, `brush`, `mover key`,
  and `level materialize`/`preview` alike — it's cross-cutting, not brush-specific. It goes in
  `docs/README.md`, next to the level-selection front matter, not under `brush/`.

With these resolved, `docs/README.md`'s front-matter total is: 9,303 (today's lines 1–138) − 700
(`create`/`list`/`status`, moves out) − 234 (`project show`, moves out) + 1,399 (`--tree`, moves
in) = **9,768 bytes** before the capability table is added. See the `docs/README.md` budget below.

Ten intra-file `#anchor` links in today's file become **cross-file** links once their targets move
to different pages — no `usage.md`-path grep finds these (same failure shape as the retiring `usage`
topic-key test, generalized): `#documentation--read-the-docs-from-the-cli` (line 21),
`#movers--animated-brush-actors-doors--lifts--gears` (94), `#level-import--read-an-existing-map-file`
(132), `#level-reimport--fold-editor-changes-back-into-the-trunk` (133), `#projects-uedclitoml`
(**five** occurrences: 363, 368, 991, 1024, 1355), and
`#brush-intersect--brush-deintersect--csg-merge-a-brush-set-into-one-brush` (1363). The dead-link
lint (`test_the_real_docs_tree_has_no_dead_links`) catches any of these left broken, but rewiring
them is real step-1 work, not an automatic byproduct of moving text. **Constraint this puts on step
2:** five links point at `#projects-uedclitoml`, so `docs/README.md` must keep the heading
`` ## Projects: `uedcli.toml` `` **verbatim** (that exact text is what the GitHub-style slugifier
turns into that anchor) — rewording it while folding in the front matter would silently break five
links that the dead-link lint would then catch, but only after the fact.

### Worked example: `actor/`

```
docs/usage/actor/
  README.md   topic "usage/actor"          — index: one row per command, links out
  find.md     topic "usage/actor/find"
  show.md
  add.md
  delete.md
  duplicate.md
  move.md
  rotate.md
  order.md
  prop.md      (get/set/unset together — small subgroup, mirrors sound/music's classify shape)
  bbox.md
  build.md
  folder.md    (get/rename/set/unset together)
  label.md     (add/remove/clear/get together)
  preview.md   topic "usage/actor/preview"  — was going to be a top-level actor-preview.md; a
                                                sibling leaf here instead (17,661 bytes alone)
```

`README.md` example shape:

```markdown
# Actors

Query, mutate, and organize actors. See also [preview](preview.md) for rendering,
[brush](../brush/README.md) for per-surface geometry once an actor is a brush.

| Command | Query/mutate | What it does |
|---|---|---|
| [`actor find`](find.md) | query | print matching actor names, one per line, for piping |
| [`actor show`](show.md) | query | print named actors' full canonical T3D blocks |
| [`actor add`](add.md) | mutate | write a T3D snippet into the trunk as new actors |
...

*query — model-side, instant, no editor; mutate — model-side, rewrite the trunk.*
```

Leaf example (`find.md`) is the real content moved verbatim from today's `usage.md` (Actors query
section + the `actor find` filter reference + its worked pipe examples), with a trailing "See
also" pointing at sibling leaves (`folder.md`, `label.md`, `bbox.md`).

**Leaf title convention:** every single-verb leaf's H1 is its full verb path — `# actor find`, not
`# Find` and not the bare fallback `find`. For a leaf covering a small subgroup of verbs
(`actor/prop.md`, `actor/folder.md`, `actor/label.md`, `brush/core.md`), the H1 names the group
(`# actor prop`) and the **first body line lists every verb it covers** (`get / set / unset`), so a
query for any one of them still lands a title-adjacent hit for the shared prefix, which is most of
the value even without a per-verb title. `docs search` scores a title match 10× a body-line match
(`uedcli/userdocs.py`'s `search()`), so this convention is the highest-leverage lever *within the
four directory families* (`actor/`, `brush/`, `level/`, `class/`) for keeping the "verb exists, but
its two words never appear title-adjacent" bug from recurring there. It does **not** reach the
other 11 (flat-file) families — `music`, the board item's own motivating case, is one of them; that
family's fix is the explicit `set`/`unset`/`status`/`tags` block below, not this convention. Between
the two, every family is covered, by different mechanisms depending on its shape.

**Query vs. mutating verbs:** today's file separates these with top-level `# Query verbs` /
`# Mutating verbs` H1s. Splitting by family (not by query/mutate) means e.g. `brush/poly.md` draws
from both — that axis doesn't disappear, it just can't be a file boundary anymore. Each family's
`README.md` table carries a one-word marker per row instead (`query` / `mutate`), and a one-line
legend at the top of any family README that mixes both: "*query* — model-side, instant, no editor;
*mutate* — model-side, rewrite the trunk." This is metadata moving from a heading to a table
column, not content getting dropped.

### Worked example: `brush/`

```
docs/usage/brush/
  README.md    topic "usage/brush"
  poly.md      (poly list/find/set/pan/rotate/scale/move/align)
  vertex.md    (vertex list/move)
  measure.md   (measure relation)
  build.md     (cube/cylinder/cone/sheet/staircase/spiral/extrude/revolve)
  intersect.md (intersect/deintersect)
  core.md      (clip/snap/replace/scale/apply-transform — small subgroup, the leftover
                 top-level brush verbs that don't belong to poly/vertex/measure/build)
```

`level/`'s exact leaf boundaries are the one thing left to implementation-time judgment: `create`/
`list`/`status` combine as one small leaf (per "Content that doesn't move cleanly" above); `doctor`,
`import`, `reimport`, `materialize`, `preview` are each substantial enough (40–70 lines apiece) to
stand alone, and are cheap to confirm with the text in hand. `class/` is **not** left open — at
13,216 bytes it's over the directory threshold, so it's a directory, full stop.

## `docs/README.md` budget

This is the one page every lookup pays for, so unlike every other page it's explicitly exempted
from the "≤10,000 bytes → flat" framing (it was always going to be flat — there's nowhere else for
the top-level index to live). Budget: 9,768 bytes of front matter (measured above) + a capability
table. The capability table must use **terse rows** — one line per family, not the 200–380-byte
rows today's "Choosing a level" table uses — e.g.:

```markdown
| Family | Covers |
|---|---|
| [`usage/actor/`](usage/actor/) | find/add/delete/move/rotate/prop/build, folders, labels |
| [`usage/actor/preview.md`](usage/actor/preview.md) | the brush/actor viewer |
```

The worked examples above already list two rows for `actor/` alone (the family index plus
`preview`); a realistic count across all 17 pages (15 families, with `actor` and `brush` each
contributing 2 rows for their split-out large sub-pages) is **~18–20 rows**, not 15. At ~90 bytes a
row that's ~1,700 bytes — landing `docs/README.md` around **11.5 KB (~2,850 tokens)**, still a ~12×
reduction from today's ~35k-token `usage` lookup.

Because the split multiplies basename collisions (`build` exists under both `actor/` and `brush/`;
`preview` under `actor/` and `level/`; `list`/`show`/`search`/`classify` repeat across every
catalog family — `find_doc` deliberately refuses bare-basename resolution, so `docs show preview`
alone won't resolve), the capability table's links use full paths, and a one-line note near the top
of `docs/README.md` says so explicitly: topic keys are full paths (`usage/actor/preview`, not
`preview`).

## Content fixes folded into the move (not deferred)

- **`music classify`** gets its own explicit `set`/`unset`/`status`/`tags` block on
  `docs/usage/music.md`, mirroring `sound.md`'s, instead of "mirrors sound" prose — makes it
  literally matchable by `docs search`.
- **`prefab list`/`prefab drop`** get a plain, unbroken mention on `docs/usage/prefab.md` (today's
  `usage.md` interleaves `[--prefab-dir DIR]` between noun and verb, breaking substring search).

**Convention going forward** (so this class of bug doesn't reappear on the next new verb, given
this spec explicitly declines to build a completeness lint): every synopsis line is written
noun-verb-adjacent — optional flags go *after* the verb, never between the noun and the verb.

## Cross-linking with `docs/leveldesign/`

Each new leaf/family page gets a short "See also" into the relevant `leveldesign/` page(s) where
one exists (e.g. `brush/README.md` → `leveldesign/general/geometry-and-bsp.md`). Existing
`leveldesign/` links that today point at the whole `usage.md` get repointed to the specific family
or leaf page they actually mean — often landing on a much smaller, more precise target than before.

## Migration mechanics

1. Create `docs/usage/` tree per the layout above; move content out of `docs/usage.md` verbatim
   per the mapping (no rewriting beyond what's needed to split cleanly — this is a reorganization,
   not a rewrite of prose), including the four "doesn't move cleanly" extractions above.
2. Extend `docs/README.md` with the front matter, the `--tree`/level-selection content, and the
   full capability table (all families, one row each — this is what fixes the under-enumeration
   board item). Apply the budget and row-format above.
3. `git rm docs/usage.md`.
4. **Update the code that references the retiring `usage` key**, not just links:
   `uedcli/tests/test_docs_command.py`'s `test_docs_run_in_a_bare_checkout_with_no_project_level_or_games_config`
   (around line 676) asserts `"usage" in out.out.split()` and `_run(["docs", "show", "usage"]) == 0`
   against the **real, unmocked** docs tree — this is a bare topic-key string literal, so no
   link-grep finds it. Point it at a surviving key (e.g. `usage/actor`). Also fix the stale
   docstring on the `_heading_slugs()` helper (around line 458 — a helper function, not a test)
   that explains anchor slugs as "matching the anchors already written into `usage.md` by hand,"
   and `uedcli/userdocs.py`'s own module docstring (line 4), which names `docs/usage.md` as *the*
   CLI reference. **Do not touch** `test_docs_command.py`'s synthetic-fixture uses of the literal
   string `"usage.md"` (its `_write` calls building fake `tmp_path` trees, e.g. around lines 53,
   78, 95, 99, 123, 203) — those are arbitrary fixture filenames, unrelated to the real file, and
   are correct as they stand.
5. Grep the whole repo for references to the old path/anchors (`usage.md`, and the ten intra-file
   `#anchor` forms named above) and repoint every one that's a **live, resolving reference** — same
   discipline as the `docs/superpowers` move earlier today, with scope notes measurement surfaced:
   - **Exclude `dev/docs/board/**`, `dev/docs/superpowers/{specs,plans}/**`, and
     `dev/docs/spikes/**`.** A live grep finds ~300 hits repo-wide; ~250 sit under the first two,
     and `dev/docs/spikes/` adds another ~15 (including a `usage.md:882`-style line-number citation
     that's unrepointable by construction, since line numbers won't survive the split). All three
     are prose that merely *names* `docs/usage.md` as a past or future edit target
     (`` `docs/usage.md`: the two verbs... ``) — historical prose, not a resolvable link.
     `dev/docs/rules/documentation.md` itself classifies `spikes/` as "durable evidence," same as
     the board. Rewriting any of them falsifies the record; leave them.
   - **`dev/docs/direction/documentation.md` has one live reference** (its `Refs:` line). Per
     `CLAUDE.md`, nothing under `dev/docs/direction/` gets written without the owner's explicit yes
     — flag this one for a quick confirm rather than repointing it as part of the mechanical sweep.
   - **Four references are standing rules, not links, and need a rewrite, not a path swap:**
     `CLAUDE.md`'s Documentation section has two ("Keep the user-facing docs current... update
     `docs/usage.md`," and separately "documenting how a uedcli tool behaves (verbs, flags, output
     in `docs/usage.md`)"); `dev/docs/rules/documentation.md` and `dev/docs/rules/reviewer-brief.md`
     each have one ("Behaviour changes must land in the user docs in the same change —
     `docs/usage.md`..."). Rewrite all four to "the matching `docs/usage/<family>` page" — a
     literal path substitution would leave the *shape* of the obligation wrong (there's no longer
     one file to update) even though the sentence would parse. Treat any other hit inside
     `CLAUDE.md` or `dev/docs/rules/**` the same way — this is the category, not an exhaustive list.
6. Run `uedcli/tests/test_docs_command.py::test_the_real_docs_tree_has_no_dead_links` — it walks
   the whole served set and will catch anything missed in step 5 *within* `docs/`, structurally,
   with no new test code needed. It cannot see anything outside `docs/` (`README.md`, `CLAUDE.md`,
   `dev/docs/**`, shell scripts, `.py` docstrings/comments) — step 5 is the only guard for those;
   treat it as such, not as a step 6 will catch armor.
7. Full suite (`bin/test`) green before merge — this is where step 4's fix gets verified, and
   where anything step 5 missed outside `docs/` would surface as an unrelated-looking failure
   elsewhere (a docstring or comment mismatch won't fail a test, so step 5's completeness there
   matters more, not less, for that category).

## What this resolves

Board items `docs-search-cannot-find-music-classify-or`,
`usage-md-is-a-single-2001-line-topic-key-with`, `leveldesign-and-usage-md-are-barely-cross-linked`,
`docs-readme-md-under-enumerates-uedcli` — move all four to `done/` once merged, each noting this
spec.

## Rejected alternatives

- **Single file + TOC only** (no split) — doesn't fix the "any lookup costs ~35k tokens" problem,
  which measurement showed is the dominant cost.
- **9-page grouping by conceptual weight** (an earlier draft of this design) — coarser than the
  final shape; superseded once real byte measurements showed `actor` (with preview folded in)
  would have been the single biggest page, bigger than any brush sub-page, contradicting the
  goal it was meant to serve.
- **One page per literal CLI leaf command, no subgrouping at all** — would produce 100+ files;
  small, tightly-coupled sub-verbs (`prop get/set/unset`, `folder get/rename/set/unset`) are kept
  together as one leaf, matching the `sound`/`music classify` and `brush build` precedent already
  in the current file.

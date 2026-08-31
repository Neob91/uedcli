# `usage.md` split — design

Owner-directed brainstorm, 2026-08-30/31. Follows the same-day docs-structure review (two
independent agents) and the `docs/superpowers` → `dev/docs/superpowers` move. Revised after merge:
the original single-tree design (everything under `docs/usage/`) is replaced by a two-tree split —
`docs/usage/` (task-oriented guides) and `docs/reference/` (dry per-command reference) — per the
owner's explicit direction.

**Baseline pin, and a real caveat about it.** Every line number and byte figure below is measured
against `git show 91e4bbf:docs/usage.md` (2,001 lines / 139,080 bytes). `docs/usage.md` is a live
file in a fast-moving shared repo and has already drifted twice during this spec's own lifetime —
by implementation time it will not be at 91e4bbf. All drift observed so far sits at or after line
1127 (inside `# actor preview`); everything at or before line 1126 has stayed byte-identical across
every revision checked. **Locate content by heading/bullet text, not by trusting a line number
verbatim** — treat every line citation below as a hint pointing at 91e4bbf, re-derive the real range
against HEAD before cutting. Two citations are already known-stale as of this writing (a third, the fifth `#projects-uedclitoml` occurrence at line 1355, is stale in exactly the same way but not flagged inline below — treat every citation at or after line 1127 as suspect) and are
flagged inline where they occur (`actor preview`'s size, and "CSG-combining a stash"'s location).

## Problem

`docs/usage.md` is a single topic key serving ~139,000 bytes (~35,000 tokens, drifting slightly
upward over time — see baseline-pin note above) for *any* lookup, even a two-line command like
`cache clear`. Measured effects:

- `docs show usage` always costs tens of thousands of tokens regardless of what's needed.
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
- Task-oriented content (the mover keyframe workflow, the door-mover flow, CSG-combining a stash)
  is stranded inside a single family's reference prose today, with no home that doesn't force an
  arbitrary "whose page is this really" choice — surfaced during this same brainstorm, not a board
  item, but the reason the design has two trees instead of one.

This design resolves all four board items above. It does **not** address
`no-quickstart-first-level-walkthrough-exists-in` (a natural future home is `docs/usage/`, but
writing that content is separate, additive work) or build the argparse→markdown generator
(explicitly deferred — see Non-goals).

## Goals

- An agent gets **cursory awareness of every capability cheaply**, and pays for **detail only when
  it fetches a specific page**.
- **Reference answers "what does verb Y take, and how does it work"** (that verb's own mechanism,
  flags, exit behavior) — dry, one command (or small subgroup) per page. **Usage answers "how do I
  accomplish X"** — free to mix commands on one page, the way a real workflow does.
- Every fact lives at exactly one file **within each tree** — no generated/duplicated content
  inside `docs/reference/` or inside `docs/usage/`, no drift risk beyond what the existing
  dead-link lint already catches. Overlap *between* `docs/usage/` and `docs/leveldesign/*/recipes/`
  is accepted, not a violation of this goal — see "Accepted overlap with `docs/leveldesign/`
  recipes" below.
- The reference tree mirrors the CLI's own organization (parser modules, and their own sub-verb
  groupings for the largest families) so it stays obviously correct as the CLI grows, with no
  separate taxonomy to keep in sync by hand.

## Non-goals (explicitly deferred, not forgotten)

- **argparse → markdown generator.** Real, separable engineering (format design, generation
  script, CI drift-guard — same shape as the deferred `bundle-the-user-facing-docs-into-the-wheel`
  board item). Measured that generation timing doesn't change token economics — the split alone
  delivers the reduction — so this is a fast-follow, not a blocker. File a board item for it
  after this ships. (Generation, if built later, only ever targets `docs/reference/` — the
  mechanical layer. `docs/usage/`'s workflow prose is inherently hand-authored.)
- **Literal content inclusion/transclusion** (a family page containing its leaf pages' full text).
  Would need the same kind of generator + drift-guard. Family pages are plain links instead.
- **A CLI-verb documentation-completeness lint.** Explicitly rejected by the owner earlier the same
  day — the dead-link lint (`test_the_real_docs_tree_has_no_dead_links`) is the only automated
  guard; it structurally can't miss a *linked* page going stale, but doesn't (and won't) assert
  that every CLI verb has a page.
- **Writing the quickstart walkthrough** (board item `no-quickstart-first-level-walkthrough-exists-in`)
  — unrelated, additive content. `docs/usage/` gives it a home; this design doesn't write it.
- **An exhaustive audit of every remaining workflow-shaped paragraph in `usage.md`.** Three pieces
  of content are identified and precisely located below (the mover keyframe workflow, the
  door-mover flow, CSG-combining a stash) because they were already found during this brainstorm.
  Anything else workflow-shaped that surfaces during implementation gets the same treatment
  (extract to `docs/usage/`, note it in the theme it fits), on the same "cheap to confirm with the
  text in hand" basis already used for `level/`'s leaf boundaries — this isn't a closed list.

## Architecture

Four tiers, entirely plain markdown + links — no new code in `userdocs.py`:

```
docs/README.md                              topic "index"                — top-level orientation, points into both trees below
docs/usage/README.md                        topic "usage"                — task-guide index, grouped by theme
docs/usage/<task>.md                        topic "usage/<task>"         — flat, one workflow per page, mixes commands
docs/reference/<family>.md                  topic "reference/<family>"          — flat, for small families
docs/reference/<family>/README.md           topic "reference/<family>"          — index, for large families
docs/reference/<family>/<command>.md        topic "reference/<family>/<command>" — leaf content
```

Both `docs/usage/README.md` and every `docs/reference/<family>/README.md` rely on `userdocs.py`'s
existing README-folding rule (a `README.md` folds to its containing directory's topic key) —
already exercised by `docs/leveldesign/`. No new serving logic. The existing duplicate-topic-key
hard-error (`direction/conventions.md`'s ambiguous-served-set ruling, filed earlier the same day)
is the safety net if a family ever accidentally got both a flat file and a directory.

**`docs/reference/` deliberately has no `README.md` of its own — no topic key `reference`.** The
capability table lives in `docs/README.md` instead, which is already the one top-level index — a
second one at `reference` would just be a redundant hop. (`docs show reference` exits 2; `suggest`'s
prefix-match hint is capped at 6 results, so it surfaces a handful of `reference/actor/*` entries,
not "the family keys" — that's not a reason to skip a `reference/README.md`, just a real limitation
worth knowing rather than leaning on as the justification.) This is intentional asymmetry with
`docs/usage/README.md`, which does exist, folding to `usage`.

Unlike the superseded single-tree draft, the `usage` topic key is **not** retired — it's
repurposed. `docs/usage/README.md` genuinely exists and is served at topic `usage`, with different,
better content than today's monolith. (This incidentally means the real-tree test flagged in an
earlier review round —
`test_docs_run_in_a_bare_checkout_with_no_project_level_or_games_config`, which asserts
`"usage" in out.out.split()` and `docs show usage == 0` — needs **no code change**: both
assertions keep passing naturally, because `usage` stays a valid, populated topic key.)

**Rule for reference flat vs. directory:** a family's total current content, roughly:
- **> ~10,000 bytes → directory**, split along the family's own natural sub-verb groupings
  (mirroring its own argparse subparsers where it has them).
- **≤ ~10,000 bytes → flat file**, no split.

**This rule governs families, not individual leaves — a leaf with no sub-verb axis to split along
stays one file regardless of size.** `actor/preview.md` (~22 KB on a current checkout, up from the
17,661-byte 91e4bbf baseline — the file's only significant drift, see the baseline-pin note) and
`brush/build.md` (13,357 bytes) are both well over the 10,000-byte threshold and both ship as a
single leaf anyway: `actor preview` is one verb with zero `##`/`###` sub-headings in its whole
244-line run, so there's nothing to split along. Splitting a leaf further only happens when the
*leaf itself* has an internal sub-verb structure to mirror (which is exactly how `brush/poly.md`
etc. already got split out from `brush` as a whole) — size alone doesn't trigger it a second time
within an already-split family.

Measured sizes (against the 91e4bbf baseline — re-verify against HEAD before cutting, per the
baseline-pin note above; `brush`, `mover`, `stash+prefab` and `actor` are corrected below to
exclude content that moves to `docs/usage/` or `docs/README.md`; see "Workflow content" and
"Content that doesn't move cleanly" for exactly what and why):

| Family | Bytes | Treatment |
|---|---:|---|
| actor (CRUD, no diagram) | 22,638 | directory — **not a clean cut, same shape as `class` below**: raw ranges 141–259 (query, opens with a shared 6-verb command table) + 381–406 (`## Folders`) + 407–445 (`## Labels`) + 446–450 (`# Mutating verbs` preamble) + 451–547 (mutating) + 929–953 (`## \`actor build\``) = 22,858; **minus** the 220-byte preamble (446–450, goes to `docs/README.md`) = **22,638**. Neither `## Actors` section has a single `###` sub-heading — splitting these 22 KB into 11 leaves is authoring against a shared table, not cutting along pre-drawn lines, the same effort class as `class`'s shared fence below. |
| actor diagram | ~22,056 on a current checkout (91e4bbf baseline was 17,661; this section is the file's only significant drift — re-measure `# \`actor diagram\`` against HEAD before cutting either way) | *(own leaf under `actor/`, not split further — see the family-vs-leaf threshold note above)* |
| brush (poly/vertex/measure/core/intersect) | 21,006 | directory — **not a clean cut**: `## Brush surfaces & geometry` (260–309) opens with its own shared 4-row command table feeding `poly.md`/`vertex.md`/`measure.md`, no sub-headings of its own either. Derivation: raw ranges 260–309 + 548–734 + 1019–1126 = 22,762; **minus** the 1,399-byte `--tree` block (inside 548–734, goes to `docs/README.md`) = 21,363; **minus** the 357-byte "door-mover flow" (inside 1019–1126, goes to `docs/usage/`) = **21,006**. Two separate subtractions from two disjoint sub-ranges — do not apply either twice. |
| brush build (generators) | 13,357 | *(own leaf under `brush/`)* |
| level (doctor/import/reimport/materialize/photo, **+create/list/status as three small leaves**) | 18,422 | directory — the "Choosing a level" table (all five rows: `create`/`import`/`reimport`/`list`/`status`) moves into `level/README.md`'s own index; the `import`/`reimport` rows link to the existing `import.md`/`reimport.md` leaves, and `create`/`list`/`status` **each get their own tiny new leaf** (`create.md`/`list.md`/`status.md`, ~176/218/306 bytes respectively) rather than being index-row-only text with nowhere to link — this makes `level/` the one family whose README genuinely indexes all eight of its verbs, none left as an orphaned row. None of the five rows' bytes were ever counted in the 18,422 figure (see below); the three new leaves' ~700 bytes come from the table itself, not from this row. |
| class | 13,216 | directory — over the 10,000-byte threshold. **Six** leaves, matching `uedcli/cli/parsers/classes.py`'s six sub-verbs and the file's own `### class preview` / `### class classify` / `### class search` / `### class prewarm` sub-headings (`list` and `show` have no sub-heading of their own — they're the section's opening, unheaded, sharing one fence with the other four's synopses): `list.md`, `show.md`, `preview.md`, `classify.md`, `search.md`, `prewarm.md`. Not a clean cut — like `sound`+`music` below, this needs light authoring to split the one shared synopsis fence six ways, not just moving pre-separated sections. |
| mover | 3,372 | flat — the `# Movers` section is 4,508 bytes total; minus the 1,136-byte keyframe-authoring worked example (goes to `docs/usage/`) = **3,372** |
| sound+music | 4,070 total | **two** flat files (`sound.md`, `music.md` — separate parser modules; do not merge). **Not a clean cut**: the section is one interleaved narrative with shared intro prose and paired fenced examples (`sound list` / `music list` on adjacent lines) — producing two independent pages is light authoring, not a byte-preserving split. The two pages will read as near-duplicates of each other — both currently expose the identical `list`/`show`/`search`/`classify` surface (`preview`/`prewarm` are deferred phase-(b) work absent from *both* today, not a `sound`-only feature; there is no `--similar` flag on either), differing mainly in `music`'s extra title/format output fields — accepted, same as the leveldesign overlap, rather than merged into one file (they're separate parser modules per the "never merge" rule). |
| stash+prefab | 3,414 total | **two** flat files (`stash.md`, `prefab.md` — separate parser modules) — the combined section is 3,615 bytes; minus 201 of the 281-byte "CSG-combining a stash" bullet (the technique/pipeline moves to `docs/usage/`; the bullet's opening ~80 bytes, "**CSG-combining a stash** is not a stash verb," stays on `stash.md` per "Workflow content" below — **not verbatim**, since as-written it trails off into the pipeline that's leaving; needs a one-clause rewrite so the sentence stands alone, e.g. "there is no `stash intersect`/CSG-combine verb") = **3,414**, which still includes a 639-byte shared intro (explaining stash/prefab/level share one on-disk format) with no single-family home — paraphrase it briefly onto both `stash.md` and `prefab.md`, light authoring not a verbatim move. |
| texture | 3,620 | flat |
| docs | 2,978 | flat |
| cache+substrate | 975 | flat, one file each (tiny; do not force a directory) |
| event | 995 | flat — see "Content that doesn't move cleanly" below, a paragraph *extracted from inside* `level`'s content, not a free-standing move |
| project | 234 | flat, `project show` only (lines 109–111) — see below, the rest of the `uedcli.toml` section is front matter, not this page |

## Content that doesn't move cleanly (findings from six rounds of independent spec review)

Seven pieces of content don't have a single obvious destination, because they're embedded inside a
*different* family's prose block in today's file rather than living in their own section. Resolved
explicitly here so no implementer has to re-derive it. Every figure below is recomputed directly
against `git show 91e4bbf:docs/usage.md` (subject to the baseline-pin caveat at the top of this
document).

- **`uedcli.toml` project config** (lines 62–112, 3,530 bytes) is a *concept* (how projects/games
  are configured), not a command — it stays in `docs/README.md`'s front matter, same as today.
  **`project show`** (the CLI verb — lines 109–111, 234 bytes, a bolded block, not a parenthetical;
  the parenthetical at line 107 is a passing mention, not the verb's own text) is a *command* — it
  gets pulled out into its own tiny `docs/reference/project.md` leaf. Same underlying section, two
  different destinations for two different kinds of content; not a duplication.
- **`event graph`** (lines 366–380, exactly 995 bytes) is embedded inside "Level lint & trigger
  wiring," directly after `level doctor`'s prose, with no heading separating them — that whole
  block is what today counts toward `level`'s 18,422-byte figure. Moving `event graph` out is a
  **paragraph-level extraction from the middle of `level`'s content**, not a same-shape move to a
  same-size neighbor like `cache`/`substrate` — flagging this explicitly so the implementer doesn't
  go looking for it near the file's tail and conclude it's missing.
- **The whole "Choosing a level" table** (lines 129–135, header + 5 rows: `create`, `import`,
  `reimport`, `list`, `status`) moves as a unit into `docs/reference/level/README.md`'s own index —
  the same way every other family README lists its full command set, not a partial one. This
  supersedes an earlier draft of this spec that tried to split the table (keep `create`/`list`/
  `status`, leave `import`/`reimport` behind) — that split was ambiguous about whether the
  `import`/`reimport` rows' 503 bytes counted toward `docs/README.md` or `level/README.md`, and it
  doesn't matter which: the whole table moves, cleanly, all 1,240 bytes (header, divider, and all
  five rows) out of front matter. The surrounding **concept prose** (lines 113–128, 841 bytes — what
  `UEDCLI_LEVEL` is, why there's no `level select` verb) is a different kind of content and stays in
  `docs/README.md`, same split as `uedcli.toml`/`project show` above.
- **`` `--tree KIND/NAME` ``** (lines 716–734, 1,399 bytes) sits inside brush's mutating-verb line
  range by accident of file position, but its own text says it rides `actor`, `brush`, `mover key`,
  and `level materialize`/`photo` alike — it's cross-cutting, not brush-specific. It goes in
  `docs/README.md`, next to the level-selection front matter, not under `brush/`.
- **The `# Mutating verbs` preamble** (lines 446–450, 220 bytes — "these transform the in-memory
  level and rewrite the T3D trunk; committing is your own `git`; each also accepts `--tree
  KIND/NAME`") is the same shape as `--tree` itself: cross-cutting prose sitting inside `actor`'s
  line range by accident of position, silently counted in `actor`'s raw 22,858 figure (already
  corrected to 22,638 above). Goes to `docs/README.md`, next to `--tree`.
- **The `# Generators — stateless T3D producers` preamble** (lines 735–747, 690 bytes — name
  allocation happens at `actor add`, not at generation time; `--base-name` is a stem; a generator
  like `brush spiral` can emit multiple actors) applies equally to `brush build`, `actor build`, and
  the CSG verbs — it's in **no** family's byte total today (it sits between `--tree`'s block and
  `brush build`'s own 748–928 range) and needs the same treatment: `docs/README.md`, as its own
  short front-matter paragraph.
- **The reverse direction: two `⚠` paragraphs inside today's `## Composability` front matter**
  (lines 49–60, exactly 863 bytes) are single-family `brush poly` reference content, not a
  cross-cutting convention — they explain that the per-face verbs print `BRUSH:idx` selectors, not
  actor names, and that `brush poly align` specifically hasn't been converted and still prints
  brush names. This is the only "doesn't move cleanly" item that moves *out* of front matter rather
  than into it: both paragraphs belong on `docs/reference/brush/poly.md` (the align caveat also
  applies to `docs/reference/brush/README.md`'s `poly`/`core` split, since it explains why
  `align`'s output can't feed a per-face verb directly).

**Front-matter total, with all of the above applied:** 9,303 (today's lines 1–138) − 1,240 (the
whole "Choosing a level" table, moves to `level/README.md`) − 234 (`project show`, moves to
`project.md`) − 863 (the two `brush poly` `⚠` paragraphs, move to `reference/brush/poly.md`) +
1,399 (`--tree`, moves in) + 220 (`# Mutating verbs` preamble, moves in) + 690 (`# Generators`
preamble, moves in) = **9,275 bytes** before either capability table is added. See the
`docs/README.md` budget below.

**Ten occurrences of six distinct intra-file `#anchor` links become cross-file references once
their targets move.** No `usage.md`-path grep finds any of these — they're bare `#fragment` forms.
The six distinct anchors, and where each one's *source* line (the line containing the link, not the
line it points at) ends up:

| Anchor | Occurrences (source lines) | Source lines end up in |
|---|---|---|
| `#documentation--read-the-docs-from-the-cli` | 21 | `docs/README.md` (front matter) |
| `#movers--animated-brush-actors-doors--lifts--gears` | 94 | `docs/README.md` (front matter) |
| `#level-import--read-an-existing-map-file` | 132 | `docs/reference/level/README.md` (the moved table) |
| `#level-reimport--fold-editor-changes-back-into-the-trunk` | 133 | `docs/reference/level/README.md` (the moved table) |
| `#projects-uedclitoml` | 363, 368, 991, 1024, 1355 (**five**) | four different reference pages (`level/doctor.md`, `event.md`, `mover.md`, `brush/intersect.md`) plus `stash.md` |
| `#brush-intersect--brush-deintersect--csg-merge-a-brush-set-into-one-brush` | 1363 (91e4bbf; **known-stale** — locate by the bullet text "**CSG-combining a stash** is not a stash verb," inside `## Stash`, not this line number) | `docs/usage/csg-combine-a-stash.md` |

**Five of the six anchors do not survive at all — they become plain file links, with no fragment.**
Under the leaf-title convention below, the reference leaf a link used to point at gets retitled to
its short verb-path form (`# level import`, not `# \`level import\` — read an existing map file`),
so its GitHub-slug changes and the old anchor text no longer matches anything on the page:
`#documentation--...` becomes a bare link to `reference/docs.md`; `#level-import--...` and
`#level-reimport--...` become bare links to `import.md`/`reimport.md` (from *inside*
`level/README.md`, so just the filename, no path prefix); `#brush-intersect--...` becomes a bare
link to `reference/brush/intersect.md` (or `README.md`, either resolves the same family). **The one
exception among the five: `#movers--...` (line 94) is a *definitional* reference** ("a mover — see
[Movers](#movers...)") — its correct target is `reference/mover.md`, where "what a mover is" stays
as reference content, **not** `docs/usage/mover-keyframes.md` or `door-mover-flow.md`, which only
cover the worked examples.

**Only `#projects-uedclitoml` survives as a real anchor** (five source occurrences, all pointing at
`docs/README.md#projects-uedclitoml`), because that content folds into `docs/README.md` as one
heading among several rather than becoming its own page — so **`docs/README.md` must keep the
heading `` ## Projects: `uedcli.toml` `` verbatim** (that exact text is what the GitHub-style
slugifier turns into that anchor); rewording it while folding in the front matter would silently
break five links that the dead-link lint would then catch, but only after the fact.

**A note on relative paths, since getting this wrong by hand is exactly the class of error this
spec has repeatedly needed correcting:** this document deliberately does **not** prescribe an exact
relative-path string (`../README.md` vs `../../README.md` vs `docs/README.md`) for any of the
rewrites above — links in `docs/` resolve relative to the *containing file*, and the five
`#projects-uedclitoml` sources alone land at two different depths (`reference/*.md` is one level
down from `docs/`, `reference/level/*.md` is two). Compute the correct relative path at the point of
editing, from the actual location of the file you're writing into — the dead-link lint
(`test_the_real_docs_tree_has_no_dead_links`) catches any that are wrong regardless, so this isn't
something that can ship silently broken.

## Workflow content → `docs/usage/`

Three pieces of content are genuinely cross-command and were miscounted into a single reference
family's byte total above (now corrected). All three get pulled **out** of `docs/reference/` into
`docs/usage/` — not restated in both places — and each vacated reference page keeps a "See also"
pointing at the workflow that demonstrates it. None of the three moves are truly verbatim: each
source location is either a bare code fence with no independent title, or a heading/bullet that
needs reframing to stand alone as its own page (see "Guide page shape" below) — this is authoring,
not a pure cut-and-paste, unlike the mechanical reference-tree moves elsewhere in this spec.

- **The mover keyframe-authoring worked example** (lines 965–982, 1,136 bytes) — the fenced
  `` ```bash `` block inside today's `# Movers` section: `brush build ... | actor add -`, then
  `mover key count/move/rotate/list/remove`. The surrounding prose (what a mover is, `NumKeys`
  semantics, `--mover-class`, each `mover key` sub-verb's own behavior) is legitimate single-family
  reference content and **stays** in `reference/mover.md` — only the worked multi-step example
  moves. → `docs/usage/mover-keyframes.md`, theme **Movers & animation**.
- **"The door-mover flow"** (the heading and its content, lines 1114–1126, 357 bytes) — today
  filed under the `brush intersect`/`brush deintersect` H1 by accident of position; it's a named,
  numbered workflow combining `actor find`/`show`, `brush deintersect`, `actor add`, and
  `mover key`. → `docs/usage/door-mover-flow.md`, theme **Movers & animation**. **Its page title is
  `# The door mover flow` — no hyphen** (see "Guide page shape" below for why).
- **"CSG-combining a stash"** (⚠ location known-stale in the 91e4bbf line numbers cited elsewhere in
  this spec — locate by the bullet text, not the line number, per the baseline-pin note — a bullet
  inside today's `## Stash` section: "**CSG-combining a stash** is not a stash verb: pipe it into
  the generator — ..."). The negative fact ("there is no `stash intersect`/CSG-combine verb") is
  itself something a reader of `reference/stash.md` would look for — it **stays** there, one
  sentence, as today. Only the worked technique (the actual `stash show | brush intersect |
  actor add` pipeline and its explanation) moves. → `docs/usage/csg-combine-a-stash.md`, theme
  **Building & shaping geometry**. This one has no leveldesign counterpart (verified: no
  `leveldesign/**/recipes/*.md` covers CSG-combining a stash) — it's the one piece of workflow
  content that's genuinely unhomed elsewhere.

**Guide page shape:** each page opens with an H1 naming the workflow, one framing sentence, the
worked commands, and a closing "Reference:" line linking every command it uses (e.g.
`door-mover-flow.md` → `reference/actor/find.md`, `reference/actor/show.md`,
`reference/brush/intersect.md`, `reference/actor/add.md`, `reference/mover.md`) so the guide never
needs to restate flag-level detail the reference page already owns.

`docs search` scores a title match 10× a body-line match, but it is a **literal substring** match —
`"door mover" in "door-mover"` is `False` (confirmed by running it against the real `search()`), so
a hyphenated title does **not** make the spaced query find the page; this was wrong in an earlier
draft of this spec, which claimed the opposite. **Rule: hyphens and slashes are not word separators
to `search()`.** Where a workflow's natural name has one (`door-mover-flow.md` as a filename is
fine — file names aren't searched), write the **H1 without it** (`# The door mover flow`) so the
literal spaced phrase a user is likely to type actually appears. This does trade one gap for
another — `docs search "door-mover"` (hyphenated) finds today's `usage.md` via its heading text,
and would find nothing post-split if the hyphenated spelling appears nowhere on the new page — so
each guide's framing sentence should include **both** spellings somewhere in the body (the H1
spaced, one body line carrying the hyphenated form), covering whichever way a user or agent happens
to type it. The same rule already matters for the reference-leaf title convention below; state it
once here as the general principle.

**Accepted overlap with `docs/leveldesign/` recipes.** Four existing leveldesign pages already
cover CLI-driven mover workflows more fully than the terse `docs/usage/` versions —
`docs/leveldesign/general/recipes/mover-door.md`, `docs/leveldesign/deusex/recipes/elevator.md`,
`docs/leveldesign/general/recipes/lift.md`, and `docs/leveldesign/deusex/recipes/deusex-door.md`
(the latter two also carry `uedcli` pipeline sections with `mover key` commands) — editor procedure,
trigger wiring, engine caveats, for a level-design audience. `docs/usage/mover-keyframes.md` and
`door-mover-flow.md` are not replacements for those four pages: they're the terse, CLI-only
version, for an agent that just needs the commands, not the craft judgment calls. Some duplication
between the two trees is accepted rather than eliminated, because they serve different readers —
this is a deliberate exception to "every fact lives at exactly one file," scoped to exactly this
overlap, not a general license to duplicate.

Both `docs/usage/mover-keyframes.md` and `door-mover-flow.md` link to all four leveldesign
counterparts in a closing "See also, for the full craft recipe:" line. Going the other direction,
each of the four leveldesign pages gains one added bullet linking back — under whatever trailing
section it already has (`mover-door.md` ends in `## Related`; the others' trailing sections vary —
check each file's own last heading and append there rather than assuming a shared section name
exists across all four).

**`docs/usage/README.md`'s themes** (section headers over the flat file list below it — no
subdirectories; three pages today doesn't warrant nesting, same principle already applied to
reference's tiny families):

1. **Composability / piping** — how verbs chain via stdin. Today's `## Composability` front-matter
   section (which stays conceptual prose in `docs/README.md`) already calls this the CLI's core
   philosophy; a natural seed for this theme, once written, is the three multi-verb pipe examples
   already in the file (`actor find --group cells | actor delete -`; `actor find --folder ... |
   actor bbox -`; `actor find --within-bbox ... | actor preview -` — genuinely two-verb pipelines,
   not single-verb examples, though small enough to stay inline on `reference/actor/find.md` for
   now rather than being pulled into their own page). No content moves here today; future page.
2. **Building & shaping geometry** — `csg-combine-a-stash.md` lives here today; generator-then-edit
   patterns are a natural future addition.
3. **Movers & animation** — `mover-keyframes.md` and `door-mover-flow.md` live here today, each
   cross-linked to their fuller `leveldesign/` counterparts.
4. **Level lifecycle** — create → populate → materialize → preview → hand-edit in UnrealEd →
   reimport, as one round-trip story. No content moves here today; future page.
5. **Discovery idioms** — "how do I find X" techniques applying `actor find`'s filters in
   combination. Not populated from `usage.md` today — a placeholder for genuinely multi-verb
   discovery recipes, if and when one is written.
6. **Sharing & reuse** — stash/prefab capture → promote → apply across levels. No content moves
   here today; future page.

### Worked example: `reference/actor/`

```
docs/reference/actor/
  README.md   topic "reference/actor"          — index: one row per command, links out
  find.md     topic "reference/actor/find"
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
  diagram.md   topic "reference/actor/diagram"  — the largest single leaf in the tree (see the
                                                    known-stale-size caveat above), a sibling leaf,
                                                    not folded into the CRUD pages
```

`README.md` example shape:

```markdown
# Actors

Query, mutate, and organize actors. See also [diagram](diagram.md) for rendering,
[brush](../brush/README.md) for per-surface geometry once an actor is a brush. For a worked
multi-command example, see [the door mover flow](../../usage/door-mover-flow.md).

| Command | Query/mutate | What it does |
|---|---|---|
| [`actor find`](find.md) | query | print matching actor names, one per line, for piping |
| [`actor show`](show.md) | query | print named actors' full canonical T3D blocks |
| [`actor add`](add.md) | mutate | write a T3D snippet into the trunk as new actors |
...

*query — model-side, instant, no editor; mutate — model-side, rewrite the trunk.*
```

Leaf example (`find.md`) is the real content moved verbatim from today's `usage.md` (Actors query
section + the `actor find` filter reference + its worked pipe examples — the three short,
multi-verb pipe one-liners noted under theme 1 above stay here as illustrative composition
examples; only the longer, named, multi-step workflows move to `docs/usage/`), with a trailing
"See also" pointing at sibling leaves (`folder.md`, `label.md`, `bbox.md`).

**Leaf title convention:** every single-verb leaf's H1 is its full verb path — `# actor find`, not
`# Find` and not the bare fallback `find`. For a leaf covering a small subgroup of verbs
(`actor/prop.md`, `actor/folder.md`, `actor/label.md`, `brush/core.md`), the H1 names the group
(`# actor prop`) and the **first body line lists every verb it covers** (`get / set / unset`), so a
query for any one of them still lands a title-adjacent hit for the shared prefix, which is most of
the value even without a per-verb title. `docs search` scores a title match 10× a body-line match
(`uedcli/userdocs.py`'s `search()`), so this convention is the highest-leverage lever *within the
four directory families* (`actor/`, `brush/`, `level/`, `class/`) for keeping the "verb exists, but
its two words never appear title-adjacent" bug from recurring there. It does **not** reach the
other 11 (flat-file) reference families — `music`, the board item's own motivating case, is one of
them; that family's fix is the explicit `set`/`unset`/`status`/`tags` block below, not this
convention. Between the two, every family is covered, by different mechanisms depending on its
shape. (Same hyphen/slash caveat as the guide pages above: a leaf title like `# level import` reads
fine, but if a verb's natural title would contain a hyphen, write the literal spaced form instead —
none of the actual leaf titles in this tree do, so this is a note for future verbs, not a fix
needed now.)

**Query vs. mutating verbs:** today's file separates these with top-level `# Query verbs` /
`# Mutating verbs` H1s. Splitting by family (not by query/mutate) means e.g. `brush/poly.md` draws
from both — that axis doesn't disappear, it just can't be a file boundary anymore. Each family's
`README.md` table carries a one-word marker per row instead (`query` / `mutate`), and a one-line
legend at the top of any family README that mixes both: "*query* — model-side, instant, no editor;
*mutate* — model-side, rewrite the trunk." This is metadata moving from a heading to a table
column, not content getting dropped.

### Worked example: `reference/brush/`

```
docs/reference/brush/
  README.md    topic "reference/brush"
  poly.md      (poly list/find/set/pan/rotate/scale/move/align)
  vertex.md    (vertex list/move)
  measure.md   (measure relation)
  build.md     (cube/cylinder/cone/sheet/staircase/spiral/extrude/revolve)
  intersect.md (intersect/deintersect — minus "the door-mover flow," which moves to docs/usage/)
  core.md      (clip/snap/replace/scale/apply-transform — small subgroup, the leftover
                 top-level brush verbs that don't belong to poly/vertex/measure/build)
```

`level/`'s exact leaf boundaries are the one thing left to implementation-time judgment: the
"Choosing a level" table's `create`/`import`/`reimport`/`list`/`status` rows all become index rows
in `level/README.md` (per "Content that doesn't move cleanly" above); `doctor`, `import`,
`reimport`, `materialize`, `photo` are each substantial enough (40–70 lines apiece) to stand alone
as full leaves, and are cheap to confirm with the text in hand.

## `docs/README.md` budget

This is the one page every lookup pays for, so unlike every other page it's explicitly exempted
from the "≤10,000 bytes → flat" framing (it was always going to be flat — there's nowhere else for
the top-level index to live). `docs/README.md` is not empty today — it's 2,015 bytes, and its
`## The composing pattern` section substantially restates what's moving in from `usage.md`'s
`## Composability` (both describe: no monolithic "make a room" verb, a generator feeds `actor add
-`, edits are model-side). **Merge these into one section when extending the file — don't append
`## Composability` alongside the existing one**, or the page duplicates itself on day one, against
this spec's own "every fact lives at exactly one file" goal. Budget: 9,275 bytes of new front
matter (measured above, including the `--tree`, `# Mutating verbs`, and `# Generators` preambles
and the whole "Choosing a level" table, and net of the two `brush poly` `⚠` paragraphs moving the
other way) + today's 2,015 bytes (net of whatever the composability merge removes — call it ~1,500
bytes surviving) + two capability tables (one per tree). Both tables
must use **terse rows** — one line per family/task, not the 200–380-byte rows today's "Choosing a
level" table uses — e.g.:

```markdown
## Usage guides

| Guide | Covers |
|---|---|
| [Door mover flow](usage/door-mover-flow.md) | turn existing door actors into a working mover via CSG deintersect |

## Reference

| Family | Covers |
|---|---|
| [`reference/actor/`](reference/actor/) | find/add/delete/move/rotate/prop/build, folders, labels |
| [`reference/actor/diagram.md`](reference/actor/diagram.md) | the brush/actor viewer |
```

The worked examples above already list two rows for `actor/` alone (the family index plus
`preview`); a realistic row count across all ~17 reference *entries* (15 families, with `actor` and
`brush` each contributing 2 rows for their split-out large sub-pages — the reference **tree** itself
is closer to 49 pages once every leaf is counted, but the capability table only needs one row per
entry point, not one per leaf) is **~17 rows**. The usage table starts at 3 rows (the three pages
identified above) and grows as the other themes get written. At ~90 bytes a row that's roughly
1,800 bytes today — landing `docs/README.md` around **12.5 KB (~3,100 tokens)**, still a
**~11× reduction** from today's ~35k-token `usage` lookup (the exact multiple depends on the file's
exact size at implementation time — see the baseline-pin note).

Because the split multiplies basename collisions within `reference/` (`build` exists under both
`actor/` and `brush/`; `list`/`show`/`search`/`classify` repeat across every catalog family —
`find_doc` deliberately refuses bare-basename resolution, so `docs show build` alone won't
resolve), both capability tables' links use full paths, and a one-line note near the top of
`docs/README.md` says so explicitly: topic keys are full paths (`reference/actor/diagram`, not
`diagram`).

## Content fixes folded into the move (not deferred)

- **`music classify`** gets its own explicit `set`/`unset`/`status`/`tags` block on
  `docs/reference/music.md`, mirroring `sound.md`'s, instead of "mirrors sound" prose — makes it
  literally matchable by `docs search`.
- **`prefab list`/`prefab drop`** get a plain, unbroken mention on `docs/reference/prefab.md`
  (today's `usage.md` interleaves `[--prefab-dir DIR]` between noun and verb, breaking substring
  search).

**Convention going forward** (so this class of bug doesn't reappear on the next new verb, given
this spec explicitly declines to build a completeness lint): every synopsis line is written
noun-verb-adjacent — optional flags go *after* the verb, never between the noun and the verb. **One
real exception:** `--prefab-dir` is a parent-parser flag (`uedcli prefab --prefab-dir DIR list`,
not `prefab list --prefab-dir DIR` — the latter errors), so `prefab.md`'s synopsis keeps the
accurate `--prefab-dir`-first form and relies on the plain unbroken mention above for
searchability, not on this convention. (There's an open, undecided board item,
`prefab-dir-flag-position`, about whether that flag position should change — this spec doesn't
touch it either way.)

## Cross-linking with `docs/leveldesign/`

Each new reference leaf/family page gets a short "See also" into the relevant `leveldesign/`
page(s) where one exists (e.g. `reference/brush/README.md` →
`leveldesign/general/geometry-and-bsp.md`). Existing `leveldesign/` links that today point at the
whole `usage.md` get repointed — two specifically: `docs/leveldesign/deusex/recipes/deusex-door.md`
and `docs/leveldesign/general/geometry-and-bsp.md` both link to `usage.md` today and need to land on
the specific reference family/leaf page they actually mean (or the matching `docs/usage/` guide
where the leveldesign page is really describing a workflow rather than one command) — often landing
on a much smaller, more precise target than before either way.

## Migration mechanics

1. Create `docs/reference/` per the layout above and move the reference-bound content out of
   `docs/usage.md`, applying the two content fixes from "Content fixes folded into the move" as
   part of this same step — the `music classify` `set`/`unset`/`status`/`tags` block on
   `reference/music.md`, and the `prefab list`/`drop` plain-mention fix on `reference/prefab.md`
   (with the `--prefab-dir` carve-out below) — since both pages are created here, not later. Apply
   the noun-verb-adjacent convention to every new synopsis line written in this step, not deferred
   to a later pass. Budget this as **authoring, not a byte-preserving cut, for five of the
   families**, not just three: `sound`+`music`, `stash`+`prefab`, and `class`'s shared intros/fences
   were already flagged in the family table above, and `actor` and `brush` are the same shape —
   both open with a shared multi-row command table feeding several different destination leaves,
   and neither has a single `###` sub-heading to split along. The other ten families' content is a
   genuine cut with little to no rewriting. **Every new page's first
   non-blank line must be its `# ` H1** — `userdocs.py`'s `_split_title()` takes the first `# ` line
   anywhere in the file, *including inside a fenced code block*, so a page whose source content
   opens with a bash comment (`mover-keyframes.md`'s source, for instance, is entirely one fenced
   block whose first lines are `# 1. build the base mover ...`) would otherwise get served under a
   silently wrong title — no test catches this today, and it's the one failure mode in this plan
   that produces a wrong result with a green suite. This applies to every new page, not just the
   directory-family leaves the title convention names elsewhere in this spec — **including the 11
   flat reference families and the workflow guides, whose H1 text isn't specified anywhere else in
   this document.** Rule: a flat family page's H1 is the bare family noun as the CLI's own subcommand
   names it (`# mover`, `# texture`, `# music`, `# stash`, `# docs`, `# event`, `# project`, `#
   cache`, `# substrate`) — never today's descriptive heading (`# mover.md`'s source heading is
   currently `# Movers — animated brush actors (doors / lifts / gears)`; drop everything after the
   noun). This is also what the "five of six anchors don't survive as fragments" claim above
   depends on for `#documentation--...` (→ `reference/docs.md`) and `#movers--...` (→
   `reference/mover.md`) — without a retitled H1, the old anchor might coincidentally still resolve.
   The two workflow guides not already given an explicit title elsewhere in this spec: `# The mover
   keyframe workflow` for `mover-keyframes.md`, `# CSG combining a stash` for
   `csg-combine-a-stash.md` (both following the same no-hyphen rule as `door-mover-flow.md`'s `# The
   door mover flow`). This is all safe to
   do incrementally — `docs/usage.md` still exists and still serves topic `usage`, so `docs show
   usage` and `docs list` both keep working throughout. **`bin/test` will go red partway through
   this step**, the moment any reference page that used to hold one end of an intra-file anchor
   gets moved — `test_the_real_docs_tree_has_no_dead_links` checks same-file anchors too, so this
   is expected, not a sign anything broke; it clears once step 5 rewires the anchors below. Step 8
   is the real green gate, not this step.
2. **Do this in one atomic change, in this order — (a1), (b), (c), (a2) — so neither collision
   hazard below ever actually opens:**
   (a1) create the three workflow *task* pages — `docs/usage/mover-keyframes.md`,
   `docs/usage/door-mover-flow.md`, `docs/usage/csg-combine-a-stash.md` — extracting their content
   from `docs/usage.md`. None of these three fold to topic key `usage` (they're
   `usage/mover-keyframes`, `usage/door-mover-flow`, `usage/csg-combine-a-stash`), so creating them
   has no collision with anything — they can and must happen **before** `docs/usage.md` is deleted,
   since it's their only source;
   (b) extend `docs/README.md` with the front matter — the four pieces that actually land there
   (the `uedcli.toml` concept prose and the level-selection concept prose, which stay; the
   `--tree`, `# Mutating verbs`, and `# Generators` preambles, which move in) plus both capability
   tables, merging the incoming `## Composability` into the existing `## The composing pattern`
   rather than duplicating it, and updating the page's own "There are two [docs]:" enumeration and
   its two links off `docs/usage.md` (apply the budget and row-format above) — **`event graph` and
   `project show` do NOT go here**, they're reference-bound and already moved out in step 1;
   (c) `git rm docs/usage.md` — by now its front matter is captured in (b) and its three workflow
   extracts are captured in (a1), so nothing is lost;
   (a2) **only now** create `docs/usage/README.md` (the theme index — no verb synopses live here,
   those content fixes are step 1's job, above). This step must come after (c): `docs/usage/README.md`
   folds to the same topic key (`usage`) `docs/usage.md` still owns until (c) runs, so creating it
   any earlier trips `load_docs()`'s duplicate-topic-key hard error on every `docs` invocation.
3. Add the leveldesign cross-links, both directions: a "See also" from each new reference/usage
   page into the relevant `leveldesign/` page (per "Cross-linking with `docs/leveldesign/`" above),
   the four mover-recipe backlinks (per "Accepted overlap" above — `mover-door.md`, `elevator.md`,
   `lift.md`, and `deusex-door.md` all four already carry their own `uedcli`-pipeline sections with
   `mover key` commands, not just the latter two — add the backlink under whatever trailing section
   each file already has, which varies: `## Related` on two of them, `## See also` on the other
   two), and repoint `deusex-door.md`'s and `geometry-and-bsp.md`'s existing links off `usage.md`
   onto their real targets.
4. Fix three stale references to the old file, all discovered by re-reading the test file rather
   than assumed: the docstring on the `_heading_slugs()` helper in
   `uedcli/tests/test_docs_command.py` (around line 458 — a helper function, not a test) that
   explains anchor slugs as "matching the anchors already written into `usage.md` by hand";
   `uedcli/userdocs.py`'s own module docstring (line 4), which names `docs/usage.md` as *the* CLI
   reference; and `test_the_real_tree_serves_the_deepest_folded_index`'s docstring (around line
   667), which opens "the **seventh** folded README index in the shipped tree" — true today (7
   folded READMEs), false once this split adds `usage/` plus four `reference/<family>/` READMEs
   (12). **Do not touch** `test_docs_command.py`'s synthetic-fixture uses of the literal string
   `"usage.md"` — its two `_write(..., "usage.md", ...)` calls building fake `tmp_path` trees
   (around lines 53 and 95) are arbitrary fixture filenames, unrelated to the real file, and
   correct as they stand; the other nearby line numbers sometimes cited for this (78, 99, 123, 203)
   are actually assertions on the derived topic key `"usage"` or an unrelated traversal-rejection
   case, not more instances of the same pattern — leave all of them alone too.
5. Grep the whole repo for references to the old path/anchors (`usage.md`, and the ten intra-file
   `#anchor` forms named above) and repoint every one that's a **live, resolving reference** — same
   discipline as the `docs/superpowers` move earlier today. Beyond the categories already named:
   - **Exclude `dev/docs/board/**`, `dev/docs/superpowers/{specs,plans}/**`, and
     `dev/docs/spikes/**`** — all three are historical/durable-evidence prose (`dev/docs/rules/
     documentation.md` itself classifies `spikes/` this way, same as the board) that merely *names*
     `docs/usage.md` as a past or future edit target, not a resolvable link. Rewriting any of them
     falsifies the record; leave them. (Re-verify the hit counts against HEAD if useful for
     scoping the sweep, rather than trusting a specific number cited here — this list has already
     drifted once between review rounds.)
   - **Specific live references outside `docs/` that a category-only sweep can silently miss** —
     name these explicitly so they're not the ones that slip through: `README.md` (the repo's own
     front door, two links), `dev/docs/README.md` (a doc-map table row plus a second mention),
     `dev/docs/prefabs.md`, `dev/docs/architecture.md` (three mentions, one citing a specific
     section by heading), `dev/docs/rationale/config.md`, `uedcli/apply.py` (a code comment), and
     `dev/scripts/setup-game-preview.sh` (one user-visible `echo` string a real user reads at a
     terminal, plus a second, internal shell comment).
   - **`dev/docs/direction/documentation.md` has one live reference** (its `Refs:` line). Per
     `CLAUDE.md`, nothing under `dev/docs/direction/` gets written without the owner's explicit yes
     — flag this one for a quick confirm rather than repointing it as part of the mechanical sweep.
   - **Four references are standing rules, not links, and need a rewrite, not a path swap — but
     they're not all the same sentence shape, so one rewrite string doesn't fit all four:**
     `CLAUDE.md`'s Documentation section has two ("Keep the user-facing docs current... update
     `docs/usage.md`," and separately "documenting how a uedcli tool behaves (verbs, flags, output
     in `docs/usage.md`)") and `dev/docs/rules/reviewer-brief.md` has one ("Behaviour changes must
     land in the user docs in the same change — `docs/usage.md`...") — these three are genuinely
     interchangeable, rewrite to "the matching `docs/reference/<family>` page (or `docs/usage/` if
     the change is workflow-shaped)." **`dev/docs/rules/documentation.md`'s one hit is a different
     sentence** ("The user-facing surface is `docs/usage.md` (the CLI reference: verbs, flags,
     output) and `docs/leveldesign/`") — it needs its own replacement, something like "The
     user-facing surface is `docs/reference/` (per-command CLI reference), `docs/usage/` (task
     guides), and `docs/leveldesign/`," not the generic "matching page" phrasing above. A literal
     path substitution on any of the four would leave the *shape* of the obligation wrong (there's
     no longer one file to update) even though the sentence would parse. Treat any other hit inside
     `CLAUDE.md` or `dev/docs/rules/**` the same way — this is the category, not an exhaustive list.
6. Run `uedcli/tests/test_docs_command.py::test_the_real_docs_tree_has_no_dead_links` — it walks
   the whole served set and will catch anything missed in step 5 *within* `docs/`, structurally,
   with no new test code needed. It cannot see anything outside `docs/` (`README.md`, `CLAUDE.md`,
   `dev/docs/**`, shell scripts, `.py` docstrings/comments) — step 5 is the only guard for those;
   treat it as such, not as a "step 6 will catch it" backstop.
7. Move the four board items this spec resolves to `done/`
   (`docs-search-cannot-find-music-classify-or`, `usage-md-is-a-single-2001-line-topic-key-with`,
   `leveldesign-and-usage-md-are-barely-cross-linked`, `docs-readme-md-under-enumerates-uedcli`),
   each noting this spec, and file the deferred argparse→markdown generator as a new board item
   (per Non-goals above).
8. Full suite (`bin/test`) green before merge — this is the real gate; the tree is expected to be
   test-red through most of steps 1–6, per the note in step 1.

## What this resolves

Board items `docs-search-cannot-find-music-classify-or`,
`usage-md-is-a-single-2001-line-topic-key-with`, `leveldesign-and-usage-md-are-barely-cross-linked`,
`docs-readme-md-under-enumerates-uedcli` — moved to `done/` in migration step 7.

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
- **One tree, with the family README doubling as a task-oriented guide** (the design's first
  revision, after round 2 of review) — reuses the existing directory structure with no new
  namespace, but conflates two things with genuinely different registers (dry reference vs. loose,
  multi-command guide) under one topic-key prefix, and doesn't give a genuinely cross-family
  workflow (spanning e.g. `stash` + `brush` + `actor`) an unambiguous home. Superseded by the
  explicit two-tree split once the owner clarified the intent.
- **Splitting the "Choosing a level" table** (keep `create`/`list`/`status` in `docs/README.md`,
  leave `import`/`reimport` behind) — an earlier draft of this section; ambiguous about which total
  the `import`/`reimport` rows' bytes counted toward, and inconsistent with every other family
  README listing its complete command set. Superseded by moving the whole table into
  `level/README.md` as a unit, once a review round flagged the ambiguity.

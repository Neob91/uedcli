# Board and process health

**Date:** 2026-10-03 · **Status:** research only — no decisions taken, nothing changed.
**Question:** What state is uedcli's work-tracking and documentation process actually in, measured
rather than impressionistic?

## Summary

- The board holds **1,016 items**: 450 in `done/`, 566 open. **421 of the 566 open items (74%) are
  still in `inbox/`** — untriaged.
- **206 of those inbox items have been there at least 68 days**, i.e. since before the earliest
  unsquashed commit. Triage is not keeping up with capture; intake has outrun it ~3:1.
- **~75 unanswered blocking questions** sit across **47 open items**. 39 of the 41 `to-spec/` items
  have at least one. The spec stage is where the project is actually blocked.
- `to-build/` — the "ready now" queue — holds **7 entries**, one of which is a group directory with
  **46 sub-items** (`native-materialize`). So the real build queue is ~52 items, not 7.
- The board **violates its own machine-enforced schema**: 52 items carry a `kind` outside the
  permitted vocabulary and 10 a `priority` outside it. A static replica of
  `old/uedcli/tests/test_board.py` reports these; the existing board item for a red suite blames a
  *different*, since-fixed cause, so the vocabulary drift appears unrecorded.
- The repo carries **179,203 lines of Markdown against 67,242 lines of Python product code — 2.7
  lines of prose per line of shipped code.** 86,630 of those lines are the board itself.
- One rule checked and found genuinely upheld: **every one of the 662 CLI flags has real `help=`
  text**, zero exceptions.

## What we have today

The board is `old/dev/docs/board/`: one directory per work item, the stage *is* the directory, an
item advances with one `git mv`. Structure, vocabularies and slug references are enforced by
`old/uedcli/tests/test_board.py`. `bin/board` is a bash reader over the same pinned TOML subset.

## Findings

### Stage distribution

| Stage | Items | with `spec.md` | with `plan.md` |
|---|---|---|---|
| `inbox/` | 421 | 20 | 7 |
| `to-spec/` | 41 | 41 | 0 |
| `to-spike/` | 6 | 0 | 0 |
| `to-plan/` | 10 | 8 | 4 |
| `to-build/` | 7 (+46 in the `native-materialize` group) | 5 | 4 |
| `someday/` | 33 | 0 | 0 |
| `stale/` | 4 | 2 | 0 |
| `done/` | 450 | 47 | 27 |
| **total** | **1,016** | | |

`to-spike/` holding zero specs contradicts the board README's rule that "an item reaches `to-spike/`
only when its spec flags a live unknown" — either the spec folded back and was deleted (the
documented behaviour: specs are ephemeral) or the rule is not being followed. Cannot tell from the
tree alone.

### Priority distribution

| Stage | p1 | p2 | p3 | p? | out-of-vocabulary |
|---|---|---|---|---|---|
| `inbox/` | 42 | 159 | 182 | 34 | 4 (`p0`×1, `p4`×3) |
| `to-spec/` | 0 | 23 | 15 | 3 | 0 |
| `to-spike/` | 0 | 4 | 2 | 0 | 0 |
| `to-plan/` | 1 | 6 | 0 | 3 | 0 |
| `to-build/` | 3 | 1 | 0 | 2 | 1 (none set) |
| `someday/` | 1 | 2 | 15 | 13 | 2 (`someday`) |
| `stale/` | 2 | 0 | 1 | 1 | 0 |
| `done/` | 114 | 142 | 76 | 114 | 4 (`p0`) |

42 `p1` items sitting in `inbox/` is the headline: the highest priority band is 10% of the
untriaged pool. Either those are mis-prioritised or triage is not pulling by priority.

### Age: the inbox is a backlog, not a queue

Ages are derived from the git add-date of each item's `overview.md` at its **pre-`old/`-move path**
(`dev/docs/board/...`). The `old/` move was squashed into one commit, so add-dates at the current
paths are all 2026-10-02 and useless. History starts at an "Initial" commit on 2026-07-25, so 68
days is a **floor**, not a measurement — anything reading 68d is "at least 68 days".

| Days in `inbox/` | Items |
|---|---|
| 0–7 | 14 |
| 8–14 | 17 |
| 15–30 | 114 |
| 31–60 | 69 |
| ≥61 (incl. the 68d floor) | 206 |
| undated | 1 |

Median age of a live `inbox/` item is 60 days. For comparison, `to-build/` items median 28 days —
once an item gets through triage it moves comparatively fast. The bottleneck is intake, not
delivery.

Commit cadence for context: 1,249 commits between 2026-07-25 and 2026-10-02, ≈18/day. Item
creations per week, by first-seen date (W31 is inflated by the squash floor):

| Week | Items created |
|---|---|
| 2026-W31 | 582 (squash floor — not a real week) |
| 2026-W32 | 46 |
| 2026-W34 | 9 |
| 2026-W35 | 89 |
| 2026-W36 | 133 |
| 2026-W37 | 64 |
| 2026-W38 | 117 |
| 2026-W39 | 32 |
| 2026-W40 | 8 |

Sustained intake is roughly 60–130 items/week while `done/` has accumulated 450 items total. The
arithmetic does not close.

### Blocking questions are the real bottleneck

A `questions/<q>.md` file is one blocking question against the item it sits in. Across non-`done`
items:

| Stage | Items with questions | Questions |
|---|---|---|
| `inbox/` | 7 | 10 |
| `to-spec/` | 32 | 52 |
| `to-spike/` | 1 | 1 |
| `to-plan/` | 4 | 4 |
| `to-build/` | 1 | 2 |
| `stale/` | 1 | 1 |
| **total** | **46** | **~70** |

`to-spec/` is where the project waits: 32 of 41 items blocked on a question. The ones with three
each are `actor-folder-list-actor-label-list`, `extract-uedcli-into-its-own-standalone-git-repo`,
`level-build-paths-only-a-quality-escalation-knob`, `level-delete-rename-clone`. The rewrite item
itself has one open (`web-refactor-sequencing`).

This is a direct consequence of the process design: `old/CLAUDE.md` requires every decision that is
the owner's to go through a question rather than an agent's judgement, down to config key names and
field names. That rule is working as specified — the queue it produces is the cost.

### The board breaks its own enforced schema

`old/uedcli/tests/test_board.py` pins (lines 49–50):

```
PRIORITIES = {"p1", "p2", "p3", "p?"}
KINDS = {"implement", "chore", "debug", "docs", "owner-question", "unknown"}
```

A static replica of `test_frontmatter` and `test_item_shape` over the live tree, using the group-dir
recursion `_items()` performs, reports:

| Check | Violations |
|---|---|
| `priority` out of vocabulary | 10 (`p0`×5, `p4`×3, `someday`×2) |
| `kind` out of vocabulary | 52 |
| unknown frontmatter key | 2 (both a `status` key, both in `done/`) |
| stray subdirectory in an item | 2 (both named `harness`) |
| extra files beside `overview.md`/`spec.md`/`plan.md` | 25 |
| frontmatter outside the pinned TOML subset | 0 |
| dangling `depends-on` slug | 0 |

Out-of-vocabulary kinds in use: `investigate` (21), `bug` (13), `finding` (9), `feature` (6),
`simplify` (1), `docfix` (1), `cleanup` (1).

Note what the drift means, not just that it exists: `bug` and `investigate` are the two most common,
and the permitted vocabulary has `debug` and `unknown` covering roughly that ground. Agents reached
for a more natural word. That is a vocabulary-design signal as much as a compliance failure.

There is an existing board item, `bin-test-red-on-master-board-schema-tests` (p1, in the
`native-materialize` group), recording `35 failed, 13086 passed` on 2026-09-02 — but it attributes
the failures to the `to-build/native-materialize/` grouping being one level deeper than the tests
expected. `_items()` has since learned the grouped layout (its docstring names the ruling), so that
cause is addressed. **The vocabulary and item-shape violations above are a separate cause and do not
appear to be recorded anywhere.**

Caveat: this is a static replica, not a pytest run. Running the real suite needs the venv bootstrap
(`python3.12` plus Docker for the native extension), which was not available here. The vocabularies
were read from the current test source, and the violating files were inspected individually
(`inbox/trunk-texture-refs-strip-group-which-is` carries `priority = "p0"`, `kind = "bug"`;
`inbox/uscript-bare-function-call-name-treated-as` carries `priority = "p4"`,
`kind = "investigate"`). Confidence is high that the test fails; the exact failure count is not
pinned.

### Documentation mass

| Tree | Files | Lines |
|---|---|---|
| `old/docs/` (user-facing) | 125 | 18,504 |
| `old/dev/docs/` excluding `board/` | 304 | 74,069 |
| `old/dev/docs/board/` | 1,266 | 86,630 |
| **total Markdown** | **1,695** | **179,203** |
| `old/dev/docs/spikes/` | 161 directories | (within the 74,069) |

Against 67,242 lines of Python product code, that is **2.66 lines of Markdown per line of shipped
code**, and the board alone outweighs the product code by 1.29×.

Two readings, both defensible. One: the project's real artefact is a reverse-engineering knowledge
base about an undocumented 1998 engine, and 161 spikes plus the `unrealed/` tree are that artefact —
prose is the product. Two: 86,630 lines of board is unmaintainable at this intake rate, and the
existing item `thin-the-board-entries-to-one-liners-where` (in `to-spec/`, with an open question)
already suspects it.

### A rule that holds

Walking every one of the 154 argparse nodes and checking each optional action for `help=` text:
**zero flags across all 662 are missing it**. The `old/CLAUDE.md` rule that "every command, flag and
argument needs a real `help=`" is upheld without exception. Worth recording alongside the drift —
the machine-checkable rules that have a test behind them held, and the one that drifted is the one
whose test is currently red.

## Options

On the inbox backlog:

| Option | Pros | Cons |
|---|---|---|
| Leave it; treat `inbox/` as an archive and triage only new items | zero cost; the board README already says `inbox/` is a pool, not a queue | 42 `p1` items stay invisible; old findings get re-discovered and re-filed |
| Bulk-sweep the ≥61-day items to `someday/` or delete | restores `inbox/` as a working signal | 206 items is a large judgement call, much of it the owner's |
| Add an age field or a periodic age report to `bin/board` | makes the backlog visible without deciding anything | more tooling, no decisions made |
| Reduce intake: raise the bar for filing | treats the cause | the capture habit is what produced the knowledge base; narrowing it loses findings |

On the schema drift: either widen the vocabularies to what agents actually reach for (`bug`,
`investigate` at minimum), or fix the 62 items and keep the vocabulary. The first is one edit, the
second is 62.

## Proposal (owner's call — not decided)

1. **File the schema drift as a board item** — it is a concrete, reproducible red-suite cause that
   the existing item does not cover. The board is agent-operated, so this needs no permission; it
   was not done as part of this research because the task was read-only.
2. **Widen `KINDS` to include `bug` and `investigate`** rather than rewriting 34 items. `bug` vs
   `debug` and `investigate` vs `unknown` are distinctions agents keep making; the vocabulary lost
   the argument 34 times.
3. **Decide `p0` deliberately.** Five items use it, four of them in `done/`, so it has been used as
   "drop everything" in practice. Either add it to `PRIORITIES` or rename those five.
4. **Report the inbox age distribution from `bin/board`** so the backlog is visible in the tool
   rather than only in an ad-hoc script. No triage decisions implied.
5. **Treat the ~70 open questions as the project's critical path**, not the `to-build/` queue. 32
   blocked `to-spec/` items is more throughput loss than anything in the build queue.

## Open questions / what to verify next

- Does `bin/test` actually fail today on `test_board.py`? One run settles it; needs the venv.
- Why does `to-spike/` hold zero `spec.md` files when the README says a spike is entered from a
  spec? Folded-and-deleted, or rule not followed?
- Are the 25 extra files inside item directories (harness scripts, differently-named specs) a
  violation the tests catch, or does `test_item_shape` only check directories? It only checks
  directories in the version read — so those 25 are tolerated, which may itself be the bug.
- How many of the 450 `done/` items were trimmed to a one-line reference as the README requires? 47
  still carry a `spec.md` and 27 a `plan.md`, which the "specs are ephemeral, deleted once the work
  lands" rule says should be gone.
- What is the actual median time from `inbox/` to `done/`? Needs per-item rename tracking through
  history, which the squash makes expensive but not impossible (`git log --follow` per item).

## Sources

Everything measured in this worktree on 2026-10-03:

- Item/stage/priority/kind/question counts: direct walk of `old/dev/docs/board/`, TOML frontmatter
  parsed with stdlib `tomllib`, including the group-directory recursion that
  `old/uedcli/tests/test_board.py::_items` performs.
- Schema checks: static replica of `test_frontmatter` and `test_item_shape`, vocabularies read from
  `old/uedcli/tests/test_board.py` lines 49–50.
- Ages: `git log --diff-filter=A --name-only` over the pre-move path `dev/docs/board`, taking the
  oldest add per slug. Floor at 2026-07-25 because history before the "Initial" commit is squashed.
- Doc line counts: `find`/`wc -l` over `old/docs`, `old/dev/docs` (with and without `board/`).
- Flag/help audit: `uedcli.cli.main.build_parser()` walked directly, checking `action.help` on every
  optional action of all 154 nodes.
- The 13,086-passed figure and the 2026-09-02 red suite: board item
  `bin-test-red-on-master-board-schema-tests`.

Not verified: that `bin/test` is red today (static replica only, see caveat above); the "at least 68
days" ages are floors, not true ages.

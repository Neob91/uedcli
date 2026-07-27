# The board (`dev/docs/board/`)

The work-state cluster for uedcli. **Each work item is a directory**, and the stage it is in **is
the directory it sits in**. An item advances with one `git mv`.

```
board/<stage>/<item-slug>/
  overview.md          REQUIRED — TOML frontmatter, a title, then the detail
  spec.md  plan.md     optional
  questions/<q>.md     optional — one BLOCKING question each
```

Why directories rather than one file per stage: several agent sessions share this repo, and a
single `inbox.md` meant every session's write collided on one file (35% of commits touched it) while
every read pulled in 4,000 lines to get one item. Two agents now touch two paths.

## The stages

| Directory | Holds | Next action |
|--------------|--------------------------------------------------|---|
| `inbox/` | un-triaged capture; anything flagged for the owner | triage → `git mv` |
| `to-spec/` | needs a spec | write `spec.md` in the item |
| `to-spike/` | needs a live/offline investigation first | run a spike → `dev/docs/spikes/` |
| `to-plan/` | has a reviewed spec | write `plan.md` in the item |
| `to-build/` | reviewed plan, ready now | implement it |
| `someday/` | parked; not surfaced in normal triage | `git mv` to `inbox/` when picked up |
| `stale/` | judged stale, **retained not deleted** | none — revisit |
| `done/` | recently finished, or finished with remnants | none — reference tail |

A stage holds item directories and a `.gitkeep`, nothing else — so `ls to-build/` **is** the queue.
`uedcli/tests/test_board.py` enforces that, and everything else below.

## `overview.md`

```markdown
+++
priority = "p1"                       # p1 p2 p3 p?   — p? = not yet prioritised
kind = "implement"                    # implement chore debug docs owner-question unknown
summary = "One line. What this is."
depends-on = ["other-item-slug"]      # optional — SLUGS, never paths
spikes = ["dev/docs/spikes/…/"]       # optional — repo-root-relative paths
+++

# Title

The detail.
```

**TOML, in a pinned subset**: single-line basic strings, one array per line, no comments. `tomllib`
is stdlib, and `bin/board` reads the same subset in bash — an agreement test runs both over every
item and requires identical results.

**The stage is the path, so `kind` does not restate it.** `[spec]`/`[spike]`/`[plan]` are retired as
tags: every issue gets a plan anyway. `kind` is what the path cannot say.

## Referencing an item — by SLUG, never by path

An item's path contains its stage, and the stage changes. So a code comment, a durable doc, a spike
or another item's `depends-on` all name the **slug**:

```
# see board item `level-import`
```

A slug is permanent and unique across the whole board; it is never renamed. `test_board.py` checks
every such reference resolves, which is what makes this safer than the paths it replaced — a stale
path citation rots silently, a stale slug reddens the suite.

## Questions block an item

A file under `questions/` is **a blocker**, not a discussion log: the thing that must be answered
before the item can be planned or built. An item with any question file **may not sit in `to-plan/`
or `to-build/`** — it goes back to `to-spec/`.

The owner answers by writing into the file's empty `## Answer` section. An agent then folds the
decision into its durable home (`direction/` for the owner's decisions, `rationale/` for an agent's),
updates the spec, and **deletes the question file — deleting it, not answering it, is what unblocks
the item**, so the durable write cannot be skipped. The commit that folds an answer out also deletes
the file; if you find it already gone, another session did it.

## `bin/board`

```
bin/board questions            open questions, by item
bin/board answered             answered, not-yet-folded — the agent's queue
bin/board ls [stage] [--json]  items by priority; --json for scripts
bin/board show <slug>          resolve a slug to its current path
bin/board new <stage> <title>  create an item with a valid stub
```

**Log a review finding with `bin/board new inbox '<title>'`**, and **run `bin/board answered` at
session start** — an answer nobody reads is the failure mode this whole shape exists to prevent.

## Goals (carried from the old `todo.md` header)

- **Guiding goal:** expose *all* UnrealEd functionality as text (LLM-drivable verbs), so an agent
  can do anything a human can in the editor without touching the GUI.
- **Portability goal (eventually):** keep uedcli usable for *other UnrealEngine games*, not just
  Deus Ex. Avoid baking DeusEx-specific assumptions into the core (class names, packages,
  substrate); pick helper classes/packages per-substrate rather than hardcoding. (Example: the
  `CAMERA ALIGN` rotation helper needs a benign point actor — `Light` works on the stripped DeusEx
  substrate where `Keypoint` crashes and `Note`/`Info` don't import; stock Unreal would use the
  engine-level `Keypoint`/`Note`.)

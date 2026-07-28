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

Four conventions the suite cannot check, because none of them is machine-decidable:

- **`inbox/` is the pre-pipeline pool AND the head of stream**, not a queue. Everything lands here
  first: ideas, gaps, bugs, chores, anything flagged for the owner (a provisional call, an
  assumption, a risk, a deviation from spec or plan, or work deliberately not done), and their own
  open questions. **There is no separate `flagged`/`to-resolve` lane** — the owner resolves their own
  items by deleting them or triaging them forward, recording any real choice in the owning
  [`../direction/`](../direction/README.md) topic.
- **A `chore` or `debug` item is one-shot**: it is filed straight into `to-build/` with no spec or
  plan.
- **An item reaches `to-spike/` only when its spec flags a live unknown**, and the spike's findings
  fold back into that same spec.
- **When an item is fully finished, `git mv` it to `done/` and trim it to a short reference line** —
  never leave a ticked `[x]` behind. If something was deferred mid-implementation, file a separate
  inbox item for it rather than letting the original quietly cover both the done part and the
  deferred part.

A stage holds item directories and a `.gitkeep`, nothing else — so `ls to-build/` **is** the queue.
`uedcli/tests/test_board.py` enforces that, and every *structural* rule below: the frontmatter
subset, the `kind`/`priority` vocabularies, and that every slug citation resolves.

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
# see board item `level-import-native-editor-less-dx-unr-t3d`
```

A slug is permanent and unique across the whole board; it is never renamed. `test_board.py` checks
every such reference resolves, which is what makes this safer than the paths it replaced — a stale
path citation rots silently, a stale slug reddens the suite.

## Questions

A file under `questions/` is **a blocker**, not a discussion log: the thing that must be answered
before the item can be planned or built.

**The item does not move.** A question raised against an item is filed in that item's own
`questions/` directory and the item stays in whatever stage it is in. It is not bounced to the
inbox and not sent back to `to-spec/` — the work already done stays where it is, and
`bin/board questions` is how a blocked item is found.

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

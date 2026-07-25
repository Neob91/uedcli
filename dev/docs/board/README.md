# The board (`dev/docs/board/`)

The work-state cluster for uedctl. Work flows through **stages**; most stage files are **queues**
named for the *next action* an item needs (`to-<verb>.md`). An item lives in one place at a time and
advances by moving its line to the next file. When an item is fully done, **delete it** (don't leave
a ticked entry); `done.md` keeps only a short tail of recently-finished + partially-done work.

## The flow

```
   inbox.md   (raw, un-triaged capture — the pre-pipeline pool + head of the stream)
"noticed it; not sorted yet" — ideas, gaps, bugs, chores, AI flags for Andrzej, his own open questions
        │ triage → route to the queue for its next action
        │  └───────────────▶ someday.md  (parked nice-to-have; NOT surfaced in normal triage;
        │                                  pulled back to inbox.md when picked up) ─┐
        ▼                                                                           │
        ◀───────────────────────────────────────────────────────────────────────────┘
   to-spec.md  ──────────────┐   some items need a live unknown investigated first
"needs a spec / design"       │
        │                     ▼
        │               to-spike.md
        │          "needs a live/offline investigation"
        │                     │   (findings fold back into the spec)
        ▼                     │
   to-plan.md  ◀──────────────┘
"has a spec, needs a plan"
        │
        ▼   (plan written + reviewed)
   to-build.md   ◀── THE BUILD QUEUE / source of truth for what to build next
"reviewed plan, ready to implement now"
        │
        ▼
   (delete when done → done.md keeps a short tail)

   ▲ a question raised mid-pipeline bounces the item back to inbox.md until it's answered
```

`inbox.md` is the **head of the stream AND the pre-pipeline capture pool** — not a stage (hence no
`to-` prefix). Everything lands here first: feature ideas, capability gaps, bugs, chores, anything the
**AI flags for Andrzej** (a provisional call, assumption, risk, or deviation), and **his own open
questions**. Triage moves each entry out to the queue for its next action; a question raised
mid-pipeline bounces back to `inbox.md` until answered. Spike is a **side-loop, not a stage**: per the
uedctl `CLAUDE.md` flow a spike happens when a spec flags a live unknown, and its findings fold back
into that spec (`to-spike.md` also holds standalone investigations not tied to one spec).

## The files

| File | Holds | Next action | Who edits |
|---|---|---|---|
| **`inbox.md`** | raw, un-triaged capture (ideas/gaps/bugs/chores) + AI flags for Andrzej + his own open questions | triage → route to a queue (he deletes/decides his own) | AI + human |
| **`to-spec.md`** | items that need a spec/design written | write a spec (`dev/docs/specs/`) | AI + human |
| **`to-spike.md`** | open questions blocking a design | run a spike (`dev/docs/spikes/`) | AI + human |
| **`to-plan.md`** | specced work awaiting a plan | write a plan (`dev/docs/plans/`) | AI + human |
| **`to-build.md`** | reviewed plans, on-deck — **the build queue / source of truth** | implement it | AI + human |
| **`someday.md`** | parked nice-to-have / someday — deferred, not in normal triage | pull back to `inbox.md` when picked up | AI + human |
| **`done.md`** | recently-completed + partially-done (with deferred remnants) | — (reference) | AI + human |

> **Transitional:** the general `[implement]`/`[chore]`/`[debug]` backlog still lives in `to-spec.md`
> (Active vs Deferred) from before `inbox.md` existed. It should migrate to `inbox.md` (raw pool) /
> `to-build.md` (chores + reviewed plans), leaving `to-spec.md` holding only genuine `[spec]` items.

## Conventions

- **Untriaged → `inbox.md`.** When in doubt where something goes, drop it in `inbox.md` as a
  one-liner; triage it forward later. Triage **moves** it out (one home per item).
- **Bracket tag = roughly the queue.** `[spec]`→`to-spec`, `[spike]`→`to-spike`, `[plan]`→`to-plan`;
  a reviewed plan or a stage-less `[chore]`/`[debug]` → `to-build`. (`[chore]`/`[debug]` skip
  spec/plan; a `[debug]` that's really an investigation can sit in `to-spike.md`.) Anything not yet
  routed sits in `inbox.md`. A transitional `[a→b]` sits in the target (`b`) queue.
- **Priority is orthogonal to stage.** `pN` tags (`p1`/`p2`/`p3`) ride the item line. The backlog
  (in `inbox.md`, and `to-spec.md` until the migration above completes) keeps an `## Active` vs
  `## Deferred (someday)` split.
- **One home per item.** Don't duplicate an item across files. Work with a reviewed plan lives in
  `to-build.md`; a few backlog entries cross-note "(also in to-build.md #N)" so on-deck
  vs backlog is visible, but `to-build.md` is authoritative for those.
- **Every new spec carries a board item that references it.** When a spec lands in `dev/docs/specs/`,
  it gets a matching board entry (normally in `to-plan.md` — a spec's next action is a plan; or its
  current queue) that links the spec path, so no spec is orphaned from the work-state. The spec
  back-links its board item in turn.
- **Human-attention items live in `inbox.md` too.** Anything the AI would flag for Andrzej (a
  provisional call, assumption, risk, deviation, or a question only he can answer) is just an inbox
  entry — there is no separate human-owned lane. He resolves them by deleting or triaging them forward.

## Goals (carried from the old `todo.md` header)

- **Guiding goal:** expose *all* UnrealEd functionality as text (LLM-drivable verbs), so an agent
  can do anything a human can in the editor without touching the GUI.
- **Portability goal (eventually):** keep uedctl usable for *other UnrealEngine games*, not just
  Deus Ex. Avoid baking DeusEx-specific assumptions into the core (class names, packages,
  substrate); pick helper classes/packages per-substrate rather than hardcoding. (Example: the
  `CAMERA ALIGN` rotation helper needs a benign point actor — `Light` works on the stripped DeusEx
  substrate where `Keypoint` crashes and `Note`/`Info` don't import; stock Unreal would use the
  engine-level `Keypoint`/`Note`.)

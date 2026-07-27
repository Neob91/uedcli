# Docs restructure: `direction/` + `rationale/`, no ledger — Implementation Plan

> **For agentic workers:** implement task-by-task; each task ends green + committed. Steps use
> checkbox (`- [ ]`) syntax. This is a docs change, so "green" means the task's stated verification
> passes — plus `bin/test` from **Task 4** onward, where code comments start being retargeted
> (`uedcli/dispatch.py:3177` and `uedcli/movers.py:24` cite `direction.md` "No silent half-answers",
> a `conventions`-topic citation, so `.py` files are in scope from the first Part B group).

**Goal:** Retire the append-only decisions ledger. Replace `dev/docs/decisions.md` (8,985 lines,
227 entries) and `dev/docs/direction.md` (392 lines, derived and drifting) with two
**revised-in-place** per-topic trees, and move three rule sections out of the always-loaded
`CLAUDE.md`.

**Architecture:** Two trees split by **who decided**. `direction/<topic>.md` holds the owner's
decisions — product intent *and* process rulings — and **may never be written without their explicit
yes**. `rationale/<topic>.md` holds engineering decisions an agent made, keyed by module, and agents
maintain it freely. Both revised in place: no supersession, no dated history, git keeps the past.
Every entry in both trees carries `Rejected` and `Refs`.

**Tech stack:** Markdown, plus one new Python checker (Task 3). The only behaviour-neutral code
edits are retargeted comments in `uedcli/*.py`, `bin/_venv.sh`, `pyproject.toml`.

**Spec:** [`spec.md`](spec.md).

**Build split:** a gate after each of Tasks 3, 4, 5, 6, 7, 8, 9, 10. Tasks 1–2 are batched into
Task 3's gate (permitted by `CLAUDE.md` "Review gates" — batch small changes into one round).

**Worktree:** the default stands — a feature is built in its own worktree and squash-merged, one
commit per feature. **An exception is the owner's call, made live in the session; it is not a
standing rule and `process.md` must NOT record one.** This restructure has already landed
incrementally on the checked-out branch, which is a fact about what happened, not a precedent.

**Conventions reminder:** commit only touched files by explicit pathspec (never `git add .`/`-a`);
one short imperative subject; no AI attribution; never rewrite history. Markdown tables pad every
column except the last.

---

## Ordering constraints (why this sequence and no other)

1. **Part 0 before everything.** It carries the confirmation rule, which governs the migration
   itself, and the ledger freeze. Writing a `direction/` topic before the rule exists is the exact
   thing the rule prohibits.
2. **Freeze before inventory.** Every count is a measurement-at-a-sha. **The spec's numbers have
   already drifted** — `decisions.md` citers 171 → **173**, `direction.md` 45 → **46** — so Task 2
   re-measures and its numbers govern.
3. **Part A before Part B's citations.** Part A creates `rules/*.md`, which some retargets point at.
4. **The `@` swap comes LAST in Part B, not in Part A.** Swapping `@dev/docs/direction.md` for the
   index while zero topics exist would leave every session without the compiled target for the
   longest stretch of the migration — 13 topics, each blocking on a human confirmation. The line
   saving is explicitly *not* the goal (spec §0), so it does not buy the degraded window.
5. **Both old files deleted last**, only after all 13 topics are confirmed and the owner signs the
   `dropped` list — never partially, so the target never lacks a home.

### Concurrency — TWO worktrees exist, and one is NOT merged

| Worktree | State |
|-------------------------------|---
| `brush-profile-generators` | content merged at `6900e34`; no hazard |
| **`profile-generator-fixes`** | **6 commits, unmerged**, branched at `6900e34` |

It touches `dev/docs/board/inbox/` (−82 lines), `architecture.md`, `board/done/`,
`docs/leveldesign/*`, `docs/usage.md`, and `uedcli/{cli,dispatch,emit,model,builders}.py` plus two
test files. **Every one is also edited by Tasks 8–10**, and `uedcli/builders.py` carries
`decisions.md` citations at lines 25, 28, 504, 578 — so it is squarely in Task 8's scope.

- It introduces **no** new `decisions.md`/`direction.md` citations and does not touch
  `direction.md`, so the delete/modify hazard does not fire.
- **Merge it before Task 8**, or treat those five `uedcli/*.py` files and `board/inbox/` as manual-merge
  points.
- **Do NOT retire the `board/inbox/` concurrency item at Task 10** until this is actually true.

---

## Task 1: Part 0 — the rule, the two READMEs, the freeze

- [ ] Add a `### Direction docs — NEVER revise without confirmation` section to `CLAUDE.md`,
      immediately before `### Documentation`. Text is quoted verbatim in the spec §2. It must say
      this is a **convention only** — no hook, the trailer is an audit marker — and must name
      `andrzej.md` and `2026-06-20-open-questions-for-andrzej.md` as untouchable.
- [ ] In "After every change", add the `direction/` carve-out to the *"no doc may be left stale"*
      bullet. Without it the resident rules simultaneously order and forbid the edit.
- [ ] In "The dev docs split by role", replace the `direction.md` and `decisions.md` bullets with
      `direction/<topic>.md` and `rationale/<topic>.md`, both revised-in-place.
- [ ] In Documentation, rewrite *"the decision itself goes in the durable, append-only
      `dev/docs/decisions.md`"* → route to the two trees; state there is no ledger.
- [ ] **Rewrite the pruning rule** in the same section. It permits removing only *wholly superseded*
      entries and spike-"gate" notes; Task 7's `dropped` disposition is a third kind and is
      **unauthorized until this lands**.
- [ ] Create `dev/docs/direction/README.md` — short model statement + a 13-row index, each row
      carrying migration state. No topic content; no `@` import.
- [ ] Create `dev/docs/rationale/README.md` — model, the mandated `Why / Rejected / Refs` shape, and
      the history signpost (`git log --follow -- dev/docs/decisions.md`).
- [ ] Add a `> **FROZEN — DO NOT APPEND**` banner to the top of `dev/docs/decisions.md`.

**Verify — mechanical, one per checkbox:**
```sh
grep -q 'NEVER revise without confirmation' CLAUDE.md
grep -q 'andrzej.md' CLAUDE.md
grep -q 'There is NO decisions ledger' CLAUDE.md   # the routing rule was rewritten
grep -c 'wholly.*supersed' CLAUDE.md               # -> 0  (pruning rule gone)
grep -q 'FROZEN' dev/docs/decisions.md             # plain ASCII: the banner has an em-dash
test -f dev/docs/direction/README.md && test -f dev/docs/rationale/README.md
grep -rnE '@[A-Za-z0-9._/-]+\.md' dev/docs/direction/README.md   # -> empty
wc -l dev/docs/direction/README.md         # -> <= 30
```

> **Two checks that look obvious are wrong, and cost a build cycle to discover.** `grep -c
> 'append-only' CLAUDE.md -> 0` fails on the *correct* result, because the sentence abolishing the
> ledger contains the words "append-only". And matching the freeze banner on `FROZEN — DO NOT
> APPEND` trips over the em-dash through a shell. Check the routing sentence and the bare word.
> The README budget is **30**, not 25: 13 topic rows plus a header, separator and per-topic state
> cannot fit in 25 lines, and the budget was set before the table had state.

**Note:** `CLAUDE.md` grows here (671 → ~715). Task 3 reduces it. Do not stop between the two.

**Commit:** `Add the direction/ confirmation rule and freeze the decisions ledger`

---

## Task 2: Re-measure everything Parts C–E depend on

Record in `dev/docs/rationale/MIGRATION.md` under `## Inventory at <sha>`:

- [ ] Spec §5's commands (line counts, citer counts, entry count, `Rejected` count, spikes count,
      section sizes).
- [ ] The `CLAUDE.md "<moved section>"` code sites — spec says 4; confirm no fifth.
- [ ] The `unrealed/*.md` **evidence** sites — spec says 7; **it is 6** (`package-format.md:65,88,184`,
      `rendering.md:127`, `quirks.md:262,443`).
- [ ] **Bare dated refs.** Definition, so the builder does not invent one: a file matching
      `rg -n '\(?[Dd]ecisions?\b[^)]{0,40}[0-9]{4}-[0-9]{2}-[0-9]{2}'` that contains **no** literal
      `decisions.md`. Record the file list, not just a count.
- [ ] `specs/`+`plans/` citer counts and directory sizes — `plans/` holds **24** files.
- [ ] **Files referenced from `board/to-build/` in ANY form** — markdown link *or* backticked path.
      **It is 12, not 11**: item 11 cites board item `two-uedcli-docs-decisions-of-yours-are` as a backticked path,
      and that file carries a live markdown link to `dev/docs/decisions.md` that would dangle. This is an
      **exemption boundary**, so a wrong number means files are checked or skipped incorrectly.

**Verify:** `MIGRATION.md` has an `## Inventory at <sha>` section with a number for every row.
**The measured numbers govern from here, not the spec's.**

**Commit:** `Record the docs-restructure inventory` *(batched into Task 3's gate)*

---

## Task 3: Part A — move three rule sections, and build the checker

- [ ] **Write the link checker first — nothing else in this plan verifies anything without it.**
      There is none in the repo today (`bin/` holds only `test`, `uedcli`, `_venv.sh`), so R3's
      "citations dangle or silently rot" mitigation is currently prose. Add a committed pytest
      (`uedcli/tests/test_doc_links.py`) that walks tracked `.md`/`.py`/`.sh`/`.toml` and fails on:
      a markdown link to a missing path; a `path#anchor` whose anchor is absent; a prose citation of
      a file that does not exist. Encode the `specs/`+`plans/` exemption **and** its 12-file
      carve-out. Every later task's verification calls this.
- [ ] Create `dev/docs/rules/spikes.md` (29 body lines), `tests.md` (21), `background-work.md` (21)
      — **verbatim except the position-relative fixes below**.
- [ ] Create `dev/docs/rules/README.md` indexing the three.
- [ ] **Sweep the moved 74 lines for position-relative language**: "above", "below", "this file",
      "two levels up", bold/italic section names, and doc-relative paths (`CLAUDE.md:393` cites
      `unrealed/quirks.md "Stability"`). All become false one directory deeper.
- [ ] **Retitle `### UnrealEd navigation — docs are READ-ON-DEMAND` → `### Read-on-demand docs —
      the router`**, and fold the three new router lines into its bullet list. The section's current
      heading and preamble are about UnrealEd behaviour only, so an agent looking for "how do I run
      tests" has no reason to read it — and Part A's whole safety argument is that the router must
      fire reliably.
- [ ] **Do NOT swap the `@` import here** — it moves to the end of Task 6 (ordering constraint 4).
- [ ] Fix `dev/docs/dev-runtime.md` (still documents the Docker `uedcli-dev` image and
      `bin/_dev-run.sh`, retired 2026-07-14), **and** `dev/docs/README.md`'s description of it
      ("uedcli-in-Docker, docker-out-of-docker + identity path-mapping"), which is equally stale.
- [ ] **`dev/docs/README.md`: add the `rules/` row now**, and rewrite the Context-loading paragraph
      — it says "only `direction.md` is auto-loaded", which stays true until Task 6 but must name
      `rules/` as read-on-demand from here. Leaving it for Task 10 would let it sit false across six
      gates, against "no doc may be left stale".

**`worktrees.md` does NOT move.** Its router line cannot carry the `git diff --cached --quiet` check
before `git merge --squash` (a data-loss trap) or "ask before `git branch -D`".

**Verify:** the new pytest passes and *fails* when pointed at a deliberately broken link (test the
test); position-relative sweep clean across `CLAUDE.md` and `dev/docs/rules/*.md`;
`wc -l CLAUDE.md` ≈ 644; `bin/test` passes.

**Commit:** `Move the spike, test and background rules to dev/docs/rules/` **→ gate (covers 1–3).**

---

## Tasks 4–6: Part B — 13 `direction/` topics, each confirmed

### The section → topic map (all 16 sections claimed, exactly once)

| `direction.md` section | → topic |
|-------------------------------------------------|---
| `:1-22` **preamble** (lane table + maintenance rule) | `process.md` |
| `:23` Scope: a generic UnrealEngine-1 tool | `scope.md` |
| `:31` Projects, substrates, and the global CLI | `projects-and-config.md` |
| `:87` The T3D trunk is the source of truth | `trunk-and-editor.md` |
| `:114` The trunk: a git-committed T3D tree | `trunk-and-editor.md` |
| `:139` Terminology | `terminology.md` |
| `:160` Folders: hierarchical actor organization | `organization.md` |
| `:174` Labels: flat, multi-valued classification | `organization.md` |
| `:191` Materializing the map file | `materialize.md` |
| `:247` Lighting, BSP and runtime state are build output | `materialize.md` |
| `:224` Safety: never irretrievably clobber | `safety.md` |
| `:263` Container isolation / substrate split | `containers.md` |
| `:272` Generator pattern | `generators.md` |
| `:301` One package-format core | `packages.md` |
| `:319` The asset catalog | `asset-catalog.md` |
| `:348` No back-compat cruft | `conventions.md` |
| `:365` Explicit, discoverable, model-side | `conventions.md` |

Line numbers are as of `618dff9`; **match on heading text**, not position.

**Groups, one gate each.** Task 4: `scope`, `terminology`, `conventions`, `process`.
Task 5: `trunk-and-editor`, `organization`, `materialize`, `safety`, `generators`.
Task 6: `projects-and-config`, `containers`, `packages`, `asset-catalog`.

### Per topic — this loop is the task, and none of it is optional

- [ ] Draft *What we want* from that topic's section(s) per the map.
- [ ] Sweep `decisions.md` for that topic's still-relevant **`Rejected`** alternatives, **and any
      live decision `direction.md` never reconciled** — criterion: any entry postdating the newest
      one `direction.md` reconciles. Re-derive; do not use a hard-coded list.
- [ ] Collect `Refs`. **A Ref whose target does not exist is DROPPED, or replaced by the code/spike
      site that does exist — never carried forward unresolved.** Most ledger `Refs:` lines point at
      ephemeral specs that were deleted when their work landed (e.g. `decisions.md:276`, `:542`,
      `:809`). A `direction/` doc is written once, on the owner's yes, so a dangling Ref baked in here
      costs another confirmation cycle to remove.
- [ ] **Put the full proposed text to the owner and wait for an explicit yes.** Not a summary — the
      wording that will land.
- [ ] On their yes, in ONE commit: write `direction/<topic>.md`; delete its section(s) from
      `direction.md`; flip its `direction/README.md` row; retarget that topic's citations; **and
      append a `direction/<topic>.md` disposition row to `MIGRATION.md` for every ledger entry
      consumed.**
- [ ] Commit trailer: `Confirmed: <topic>`.

**`process.md` additionally carries this restructure's own rulings** — the who-decided axis,
`direction/`-only scope, revise-in-place, no hook, deleting the ledger, **and that this work ran
outside a feature worktree and why**. Otherwise they survive nowhere.

**At the END of Task 6, once all 13 topics exist:**

- [ ] Swap `@dev/docs/direction.md` → `@dev/docs/direction/README.md` in `CLAUDE.md`.
- [ ] Verify `grep -rnE '@[A-Za-z0-9._/-]+\.md' CLAUDE.md dev/docs/direction/README.md` returns
      exactly one line.

**Verify per group:** each landed topic has `What we want` + `Rejected` + `Refs`; its README row is
flipped; `wc -l dev/docs/direction/README.md` ≤ 30; `git log --grep='Confirmed'` shows one
commit per topic; every consumed entry has a `MIGRATION.md` row; the link checker passes.

**Coverage gate at Task 6, mechanical:** `grep -c '^## ' dev/docs/direction.md` → **0** (every topic
commit deleted its section), and the preamble's lane model is present in `process.md`.

---

## Task 7: Part C — `rationale/` and the rest of the disposition table

- [ ] For every remaining `^## \d{4}-` entry (Tasks 4–6 filed theirs), add a `MIGRATION.md` row:
      `<date> <title> -> direction/<t>.md | rationale/<t>.md | superseded-dead | dropped`.
- [ ] `dropped` **and** `superseded-dead` each need a named reason; `superseded-dead` must name the
      superseding entry.
- [ ] Fold `rationale`-dispositioned entries into `dev/docs/rationale/<topic>.md` keyed by
      module/subsystem, in the mandated `Why / Rejected / Refs` shape. Same dangling-Ref rule as
      Part B. The ledger holds **83 `**Rejected:**` blocks**; losing them is the failure this tree
      exists to prevent.
- [ ] Put the `dropped` list to the owner for sign-off.

**Verify:** no `^## \d{4}-` entry lacks a `MIGRATION.md` row; every `rationale/*.md` entry has all
three parts; link checker and `bin/test` pass.

**Commit:** `Populate dev/docs/rationale/ and record every ledger entry's disposition` **→ gate.**

---

## Task 8: Part D — citation migration

Use **Task 2's** numbers, not the spec's. **Merge `profile-generator-fixes` first**, or treat its
five `uedcli/*.py` files and `board/inbox/` as manual-merge points.

- [ ] `decisions.md` / `direction.md` by name — retarget per each entry's disposition row.
- [ ] The 4 `CLAUDE.md "<moved section>"` code sites → `rules/<file>.md`.
- [ ] Bare dated refs (Task 2's file list) → topic path + `#anchor`.
- [ ] The 6 `unrealed/*.md` evidence sites → the `spikes/` file, **never** a mutable doc. Where the
      cited entry's own Ref is a deleted spec, there is no spike to point at — drop the pointer and
      keep the claim, or cite the code that demonstrates it.
- [ ] The 31 `spikes/` files → retarget. Durable evidence, not ephemeral.
- [ ] `specs/`+`plans/` exempt, **except the 12 referenced from `board/to-build/`**.
- [ ] Two board sites cite sections that now **stay resident** — they need *editing*, not
      retargeting. Cite them **by item title, not line range** (`board/inbox/` is 2,786 lines and the
      in-flight branch deletes 82): the `[debug]` item about the repo layout and
      `.claude/settings.json`, and `board/README.md`'s "a spike happens when a spec flags a live
      unknown".

**Verify:** link checker clean; `bin/test` passes.

**Commit:** `Retarget decisions.md and direction.md citations to the topic trees` **→ gate.**

---

## Task 9: Parts E + F — forced rule text and three false statements

**Tasks 1 and 3 shift every line in `CLAUDE.md`, and the four hardest sites straddle line breaks —
so these need MULTILINE patterns. A plain `grep -F` returns 0 on two of them:**

```sh
rg -U 'decision\s+2026-07-24 21:58'              CLAUDE.md   # spans :427-428
rg -U 'architecture,\s+direction, decisions'     CLAUDE.md   # spans :492-493
grep -n 'decisions, architecture, etc\.'         CLAUDE.md   # single line
grep -n 'spikes/decisions/each other'            CLAUDE.md   # single line
```

Plus every `decisions.md`/`direction.md` mention a plain grep does find.

- [ ] **Remove both router rows** — the `decisions.md` row, and the non-`@` `direction.md` row Task 3
      kept for un-migrated topics (all topics are migrated by now). Both files still *exist* until
      Task 10, un-routed; that is intended, and the owner's Task-10 sign-off reads the ledger directly.
- [ ] NOT-trivial list: drop the two deleted docs; add `direction/*`, `rationale/*`, `rules/*`.
- [ ] Sweep the **≥12 internal cross-references**, both directions. Do not key on `see **X**` — that
      misses six of them.
- [ ] **F1** — `CLAUDE.md` claims `.claude/worktrees/` is gitignored; it is not. Add
      `.claude/worktrees/` to `.gitignore`. **the owner's call** — log to `board/inbox/` if he
      declines.
- [ ] **F2** — rewrite the repo-layout paragraph: toplevel is `/home/neob91/Documents/Dev/uedcli`,
      no `Tools/`, `_scratch/` at that root. Same false label in `dev/docs/README.md`.
- [ ] **F3** — the `.claude/settings.json` claim references a file that does not exist. **the owner
      chooses:** create it, or delete the sentence and accept `EnterWorktree` branching from
      `origin/<default>`. Behavioural, not wording.

**Verify:** `grep -c 'decisions\.md\|direction\.md' CLAUDE.md` → **0**; `git check-ignore
.claude/worktrees` exits 0 if F1 was taken; link checker and `bin/test` pass.

**Commit:** `Reconcile the rule text and fix three false CLAUDE.md statements` **→ gate.**

---

## Task 10: Delete the old docs and close out

- [ ] **the owner's explicit confirmation** that both files may go — confirming 13 topic docs is not
      the same as confirming nothing else in 227 entries was worth keeping.
- [ ] `git rm dev/docs/direction.md dev/docs/decisions.md`.
- [ ] Record the removal sha in `rationale/README.md`'s history signpost.
- [ ] `dev/docs/README.md` — drop the two doomed rows; add `direction/` and `rationale/`; fix the
      "A gap between `direction.md` and `architecture.md`" paragraph, the "See `direction.md` + the
      board" line, and the `Tools/uedcli/CLAUDE.md` label. (`rules/` row and Context-loading were
      done at Task 3.)
- [ ] Retire the resolved `board/inbox/` items **by title, not line range** — the `@`-gate item
      Task 6 overrides, the `[debug]` item Task 9 fixes. **Not** the concurrency item unless the
      second worktree has actually merged.
- [ ] **Delete this plan's entry from `board/to-build/`** (added when the plan gate closed).
- [ ] **Add the short `board/done/` tail entry** — `CLAUDE.md` "TODOs".
- [ ] Delete this plan and the spec.

**Verify:** link checker clean; `bin/test` passes; `docs/` still references nothing under
`dev/docs/`; `board/to-build/` has no docs-restructure entry.

**Commit:** `Delete the decisions ledger and direction.md; the topic trees replace them` **→ gate.**

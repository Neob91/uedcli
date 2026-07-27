# Plan — board to one directory per work item

Spec: [`../specs/2026-07-27-board-per-item-directories.md`](spec.md).
The spec fixes the batch order (§4.2) and the rules; this plan adds only what it does not: the slice
boundaries, the inventory format, and each slice's done-when.

**Owner ruling 2.15 — base branch, committed batches, no worktree.** Every slice is its own commit
on `master`.

---

## S0 — scaffold (before any batch)

1. Eight stage directories, each with `.gitkeep`.
2. `bin/board` (spec §3.9) — bash, no venv, five subcommands.
3. `uedcli/tests/test_board.py` **assertions 3–9 only**. 1–2 (whole-board shape) land in S8, because
   every intermediate batch has stage directories *and* leftover `.md` files.
4. `uedcli/tests/test_board_script.py` — including the bash↔`tomllib` agreement test.
5. `CLAUDE.md`: route logged findings through `bin/board new`; tell agents to run
   `bin/board answered`. **Both before the first batch**, per §4.2 — a session that must log a
   finding needs a sanctioned path from the moment the board starts changing.

**Done when** `bin/test` is green with an empty board tree and `bin/board new inbox 'x'` produces an
item that passes assertions 3–9.

## The inventory (first act of every batch)

One `inventory.tsv` per batch, committed under `_scratch/board-migration/` (gitignored) and
summarised in the commit message:

```
line<TAB>class<TAB>slug<TAB>note
```

`class` ∈ `item | detail | heading | blockquote | nav`. Written before any directory is created and
read back by the conversion, so the classification is reviewable and re-runnable rather than
implicit in a script. Spec §3.11 requires it because "one bullet = one item" is false.

## S1–S7 — one stage per commit, smallest first

`to-spike` (3) → `to-build` (7) → `to-plan` (8) → `someday` (27) → `to-spec` (55) → `done` (94) →
`inbox` (293).

Each slice: inventory → create item directories (frontmatter per §3.4, authored slug and summary per
§3.3 and §4 rule 2) → move any owning `spec.md`/`plan.md` in → re-base that file's relative links
(§4 rule 5) → repoint intra-board references to slugs (§3.10) → delete the source `.md` → commit.

Slice-specific work:

- **S2 `to-build`** also deletes `_on_deck()` and reshapes `_EPHEMERAL` (§4.1), in this commit, and
  records the before/after list of link-checked ephemeral files. Applies §2.13 to
  `unified-asset-catalog` and `actor-preview-faces`.
- **S3 `to-plan`** applies §2.13 to `poly-surface-verbs`, using rule 6's attribution rule — the third
  parked question affects step 1, which is **done**, so it does not demote this item.
- **S7 `inbox`** is preceded by its own commit repointing `CLAUDE.md` away from `board/inbox/`. It is the
  contended file: 35% of recent commits touch it, and §2.15 accepts that a concurrent session's
  uncommitted edits are lost.

**Done when** each slice: the source file is gone, `bin/test` is green, and every item in it has an
authored slug and summary.

## S8 — close-out

1. `dev/docs/specs/` and `dev/docs/plans/` removed (empty).
2. `test_board.py` assertions 1–2 added.
3. Citation sweep — both censuses in §4.1, including the repo-root `README.md`.
4. Docs: `board/README.md` rewritten, `dev/docs/README.md`, `CLAUDE.md`'s remaining passages,
   `architecture.md`, `unrealed/*`, `rationale/*`, `reviews/*`, the spikes, the Python/shell/Rust
   sources.
5. `dev/docs/rationale/board.md` (spec §6).
6. `decisions.md`'s two markdown links and `rationale/MIGRATION.md`'s exempted or repointed.
7. Suite runtime measured before/after.
8. **The stale list proposed to the owner in bulk** (§2.7) — last, as ruled.

## Risks

- **S7 is the dangerous one.** Largest, most contended, and the only slice where another session's
  work can be silently lost. Announce it, and keep it to a single commit.
- **~490 authored summaries** are the bulk of the hand-labour and the thing `bin/board ls` depends
  on. If a slice's summaries are rushed, triage stays as bad as it is now.
- **A batch that reddens the suite blocks every other session.** Each slice ends green or is
  reverted.

# Document the day-to-day git-trunk level-editing loop — spec (DRAFT)

Status: draft for owner review. This is a doc-only chore whose output is USER-FACING (`docs/`), so
adding it needs the owner's yes. Nothing is written until the two `questions/` are answered.

## Goal

Write one short how-to for the current loop a user follows to edit a level with uedcli:

    work on a git feature branch
      → edit the T3D trunk model-side (`actor …` / `brush …` / `poly …`)
      → `level photo` to eyeball
      → `level materialize --out <map>` to build the artifact
      → `git commit` / merge into trunk

Git is the history + merge engine; the per-actor `.t3d` trunk files merge natively. The pieces are
decided (the trunk is a git-committed T3D tree, map files are build artifacts) and the individual
verbs are documented; the GAP is that the loop is not written down as one narrative.

Scope note: this is the LEVEL-EDITING loop for a uedcli USER — NOT the process for building uedcli
itself (feature worktrees, squash-merge), which is developer-only and lives in
`dev/docs/rules/worktrees.md`. A user doc must never point at the developer tree.

## Current state

- The loop's PHILOSOPHY is already stated at the top of `docs/usage.md`: "The source of truth is a
  git-tracked T3D tree on disk … `git` is the history and merge engine … The editor / headless game
  is reached only for `level materialize` and `level photo --game`" (`docs/usage.md:7-13`), and
  the composability rules (`:23-60`).
- The verbs exist and are documented individually: model-side mutators (`usage.md:394+`),
  `level photo` / `actor diagram` (`usage.md:1033+`), `level materialize` (referenced as the build
  step, inverse of `level import`, `usage.md:132`), `level create` / `level status`
  (`usage.md:129-134`).
- What is MISSING is a single "here is the daily loop end to end" walk-through tying them together.
  No `docs/workflow.md` exists; `docs/` is `usage.md` + `leveldesign/` (`find docs -type f`).
- Doc rules that bind: `docs/` is user-facing and must never reference `dev/docs/`
  (`dev/docs/rules/documentation.md:30-33`); keep it succinct (`CLAUDE.md` "Keep it short and
  plain"); NEW user-facing craft/best-practice content needs owner approval, but documenting how
  uedcli tools behave does not (`dev/docs/rules/documentation.md:24-28`, `CLAUDE.md`
  "Documentation").

## Design — proposed doc home and outline

### Home (proposed — see `questions/doc-home.md`)

A new top-level user doc, **`docs/workflow.md`**, cross-linked from `docs/usage.md`'s intro and from
`docs/README.md`. Rationale: the loop spans query + mutate + photo + materialize + git — bigger
than any one `usage.md` section, and `usage.md` is organised as a per-verb reference, not a
narrative. A standalone page is the thing a user looks for under "how do I actually work".

Alternatives: a "Workflow" section inside `docs/usage.md` (keeps one file, but buries the narrative
in a reference); or under `docs/leveldesign/general/` (that tree is craft, not tool-loop). The home
is an owner decision.

### Proposed outline (content to be written only after approval)

1. **The model** — the trunk is a git-tracked T3D tree (`maps/<level>/`); map files are build
   artifacts you regenerate, not edit. (Restates `usage.md:7-13` in loop terms.)
2. **Start** — pick/scaffold a level (`level create`), `export UEDCLI_LEVEL=<name>`, branch in git.
3. **Edit model-side** — the `find | mutate -` loop over `actor` / `brush` / `poly`; instant, no
   editor. Point at the verb reference in `usage.md`, do not restate every verb.
4. **Eyeball** — `level photo` (and `actor diagram`) to see the change without a full build.
5. **Build the artifact** — `level materialize --out <map>` to produce the compiled map; when to
   build (before commit / on a milestone) vs. rely on preview.
6. **Commit & merge** — `git commit` the trunk; how per-actor `.t3d` files merge natively; git is
   history + merge engine. Whether the built map is committed or is a throwaday artifact.
7. **Pitfalls** — stale `$UEDCLI_LEVEL`, forgetting to re-materialize, editing a build artifact by
   hand.

Exact wording is proposed for the owner in the approval question, not written here.

## Edge cases & errors

Doc-only; none. The one risk is drift: any claim in the doc must match current CLI behavior
(`dev/docs/rules/documentation.md` "keep user-facing docs current"), and the doc must contain no
`dev/docs/` references.

## Tests

`tests/test_doc_links.py` checks `docs/` for dead links and forbidden developer-tree references; a
new `docs/workflow.md` is covered by it. `tests/test_docs_command.py` covers `docs list|show|search`
over the tree. No new test logic needed beyond those passing on the added file.

## Open questions (owner)

1. `questions/doc-home.md` — new `docs/workflow.md` (recommended) vs. a section in `usage.md` vs.
   `leveldesign/general/`.
2. `questions/approval-to-add-user-doc.md` — approval to add this user-facing doc at all, and
   whether it counts as tool-behavior (no craft approval) or craft/best-practice (approval + review
   of the human-scale claims).

Note on board mechanics: this item is `kind = "chore"` but sits in `to-spec/`. A chore is normally
one-shot into `to-build/` (`board/README.md`), but the user-doc approval gate makes it a real
decision that must clear first — hence a spec. That is flagged, not resolved here.

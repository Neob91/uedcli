+++
priority = "p3"
kind = "docs"
summary = "board/README.md still says every issue gets a plan, contradicting chore/debug going straight to to-build"
+++

# board/README.md still says every issue gets a plan, contradicting chore/debug going straight to to-build

`dev/docs/board/README.md` "`overview.md`" says:

> **The stage is the path, so `kind` does not restate it.** `[spec]`/`[spike]`/`[plan]` are
> retired as tags: **every issue gets a plan anyway.** `kind` is what the path cannot say.

`CLAUDE.md` "The board" says the opposite for two of the six `kind` values:

> A `chore` or `debug` item is one-shot: it is filed straight into `to-build/` with no plan, and
> therefore gets no plan review round.

That is not a cosmetic disagreement — **`CLAUDE.md` "Review gates" relies on the distinction** to
decide whether the plan review round fires at all. A reader who takes `board/README.md` at face
value would run a plan round on every chore.

The same sentence in `CLAUDE.md` was corrected during the 2026-07-27 de-bloat restructure (the
"every issue gets a plan anyway" parenthetical was dropped there), so the contradiction now
lives only in `board/README.md`, which that pass did not touch.

**Fix:** reword `board/README.md` so the retirement of the bracket tags is justified by the path
carrying the stage — which is the real reason — rather than by every issue getting a plan. E.g.
"…are retired as tags: the path already says which stage an item is in. `kind` is what the path
cannot say." Both docs are agent-maintained, so no owner ruling is needed.

Surfaced by the review round on the `CLAUDE.md` restructure.

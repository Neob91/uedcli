+++
priority = "p1"
kind = "chore"
summary = "113 tracked files still cite inbox.md, to-build.md and friends; the migration's citation sweep never ran."
+++

# Sweep the files still citing deleted board paths

The migration's own done-when says *"No tracked file except `decisions.md` and
`2026-06-20-open-questions-for-andrzej.md` references a deleted board path, checked with both
census commands."* Neither census is empty. Both must be run — the first cannot see bare filenames:

```
git grep -l -E 'board/(inbox|to-spec|to-spike|to-plan|to-build|someday|done)\.md|board/HANDOFF-' \
    -- . ':!dev/docs/board/*'                                          # 76 files
git grep -lE '(^|[^/])`?(inbox|to-spec|to-spike|to-plan|to-build|someday|done)\.md' \
    -- . ':!dev/docs/board/*'                                          # 57 more
```

Union: **113 files** — plus **104 references inside 62 board items themselves**, each of which is a
dangling pointer today. Notable: the repo-root `README.md` describes the whole flow by dead
filename; `dev/docs/README.md:37` has a label saying `inbox.md` over a target of `board/inbox/`;
`uedcli/cli.py:383` puts `dev/docs/board/to-spec.md` in a **user-visible** `help=` string;
`architecture.md` has 9; three `.rs` files have 4, and `.rs` is invisible to the link checker.

**Stale rules in `CLAUDE.md`, which is worse than a stale path** because agents act on it: the
bounce-to-inbox rule at the `inbox/` bullet contradicts `board/README.md`'s bounce-to-`to-spec/`
(owner decision 2.13); three sentences still treat `[spike]`/`[chore]`/`[debug]` as routing tags and
name `to-build.md`; and the `bin/board` section still says the board "is migrating … both shapes
exist".

**`board/README.md`'s own worked example does not resolve** — it writes the reference form with the slug `level-import`
but the real slug is `level-import-native-editor-less-dx-unr-t3d`. The test cannot catch it because
that file is on the exemption list for documenting the form.

Nothing in the suite catches a stale *prose* citation of a board path, so none of this reddens
`bin/test` — it rots silently until someone follows a dead pointer.
